"""
SC-003 Reasoning Service — generates the AI finding for a shipment exception.

SC003_CONFIDENCE = 0.9520
  delivery_window_breach: confidence=1.00, weight=0.60
  sla_clause_applicable:  confidence=0.88, weight=0.40
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401
from zoiko_common.crypto.jcs import canonicalize
from shared.signer import sign

from services.reasoning_svc.rules import RULES, SC003_CONFIDENCE


class ReasoningHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.broker      = kafka_broker
        self.tenant_slug = tenant_slug

    def generate_finding(
        self,
        tenant_id: str,
        case_id: str,
        bundle_id: uuid.UUID,
        sla_breach_hours: float,
        sla_penalty_amount: float,
        currency: str,
        actor_sub: str = "system",
    ) -> uuid.UUID:
        """Generate a finding and proposal. Returns the finding_id."""
        now     = datetime.now(timezone.utc)
        case_uuid = uuid.UUID(case_id)

        rule_trace = {
            **RULES,
            "weighted_average": SC003_CONFIDENCE,
            "sla_breach_hours": sla_breach_hours,
        }
        finding_payload = {
            "bundle_id":   str(bundle_id),
            "case_id":     case_id,
            "confidence":  str(SC003_CONFIDENCE),
            "rule_trace":  rule_trace,
            "tenant_id":   tenant_id,
        }
        finding_bytes = canonicalize(finding_payload)
        finding_hash  = hashlib.sha256(b"zoiko.finding.v1:" + finding_bytes).digest()
        f_sig, f_kid  = sign(self.tenant_slug, finding_hash)
        finding_id    = uuid.uuid4()

        prop_payload = {
            "amount":          str(sla_penalty_amount),
            "case_id":         case_id,
            "currency":        currency,
            "finding_hash":    finding_hash.hex(),
            "proposed_action": "ISSUE_SLA_CREDIT",
            "proposer_sub":    actor_sub,
            "tenant_id":       tenant_id,
        }
        prop_bytes = canonicalize(prop_payload)
        prop_hash  = hashlib.sha256(b"zoiko.proposal.v1:" + prop_bytes).digest()
        p_sig, p_kid = sign(self.tenant_slug, prop_hash)

        psycopg2.extras.register_uuid()
        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO findings
                    (id, tenant_id, case_id, bundle_id, confidence, rule_trace, finding_hash,
                     signature, kid, created_at, ai_confidence, risk_level, ai_reasoning)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, NULL, NULL, NULL)
            """, (
                finding_id, tenant_id, case_uuid, bundle_id,
                SC003_CONFIDENCE, json.dumps(rule_trace),
                finding_hash, f_sig, f_kid, now,
            ))

            cur.execute("""
                INSERT INTO decision_proposals
                    (id, tenant_id, case_id, finding_id, proposed_action, amount, currency,
                     proposer_sub, proposal_hash, signature, kid, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                uuid.uuid4(), tenant_id, case_uuid, finding_id,
                "ISSUE_SLA_CREDIT", sla_penalty_amount, currency,
                actor_sub, prop_hash, p_sig, p_kid, now,
            ))

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return finding_id
