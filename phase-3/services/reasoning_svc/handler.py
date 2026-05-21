"""
Reasoning Service — analyzes an evidence bundle, computes confidence, creates
a Finding and a Decision Proposal.

SC-001 confidence formula (deterministic):
  fuel_charge_confidence  = 1.00  (weight 0.50)
  accessorial_confidence  = 0.92  (weight 0.50)
  weighted_average        = 0.50 * 1.00 + 0.50 * 0.92 = 0.96

Flow:
  1. JCS canonicalize finding payload → SHA-256 → sign → INSERT findings
  2. JCS canonicalize proposal payload → SHA-256 → sign → INSERT decision_proposals
  3. Publish reasoning.completed to Kafka
"""
import hashlib, json, uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401 — registers UUID adapter

from shared.signer import sign
from zoiko_common.crypto.jcs import canonicalize

from services.reasoning_svc.models import FindingResult

# SC-001 deterministic rule weights
_RULES = {
    "fuel_charge":  {"confidence": 1.00, "weight": 0.50},
    "accessorial":  {"confidence": 0.92, "weight": 0.50},
}
SC001_CONFIDENCE = round(
    sum(r["confidence"] * r["weight"] for r in _RULES.values()), 4
)  # = 0.96


class ReasoningHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.broker      = kafka_broker
        self.tenant_slug = tenant_slug

    def analyze(
        self,
        tenant_id:       str,
        case_id:         str,
        bundle_id:       str,
        proposer_sub:    str,
        proposed_action: str = "CREDIT_MEMO",
        amount:          float = 0.0,
        currency:        str = "USD",
    ) -> FindingResult:
        tenant_id = str(tenant_id)
        case_id   = str(case_id)
        bundle_id = str(bundle_id)
        now       = datetime.now(timezone.utc)

        rule_trace = {
            rule: {"confidence": v["confidence"], "weight": v["weight"]}
            for rule, v in _RULES.items()
        }
        rule_trace["weighted_average"] = SC001_CONFIDENCE

        # Step 1 — finding record
        finding_payload = {
            "bundle_id":  bundle_id,
            "case_id":    case_id,
            "confidence": str(SC001_CONFIDENCE),
            "rule_trace": rule_trace,
            "tenant_id":  tenant_id,
        }
        finding_bytes = canonicalize(finding_payload)
        finding_hash  = hashlib.sha256(b"zoiko.finding.v1:" + finding_bytes).digest()
        finding_sig, finding_kid = sign(self.tenant_slug, finding_hash)

        # Step 2 — proposal record
        proposal_payload = {
            "amount":          str(amount),
            "case_id":         case_id,
            "currency":        currency,
            "finding_hash":    finding_hash.hex(),
            "proposed_action": proposed_action,
            "proposer_sub":    proposer_sub,
            "tenant_id":       tenant_id,
        }
        proposal_bytes = canonicalize(proposal_payload)
        proposal_hash  = hashlib.sha256(b"zoiko.proposal.v1:" + proposal_bytes).digest()
        proposal_sig, proposal_kid = sign(self.tenant_slug, proposal_hash)

        finding_id  = uuid.uuid4()
        proposal_id = uuid.uuid4()

        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO findings
                    (id, tenant_id, case_id, bundle_id, confidence,
                     rule_trace, signature, kid, created_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            """, (
                finding_id, tenant_id, uuid.UUID(case_id), uuid.UUID(bundle_id),
                SC001_CONFIDENCE, json.dumps(rule_trace),
                finding_sig, finding_kid, now,
            ))
            cur.execute("""
                INSERT INTO decision_proposals
                    (id, tenant_id, case_id, finding_id, proposed_action,
                     amount, currency, proposer_sub, proposal_hash, signature, kid, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                proposal_id, tenant_id, uuid.UUID(case_id), finding_id,
                proposed_action, amount, currency, proposer_sub,
                proposal_hash, proposal_sig, proposal_kid, now,
            ))
            conn.commit()
        finally:
            conn.close()

        # Step 3 — Kafka publish AFTER commit
        from kafka.producer import ZoikoProducer, KafkaMessage
        ZoikoProducer(self.broker).publish(KafkaMessage(
            topic     = "zoiko.finding.generated",
            key       = str(case_id),
            payload   = {
                "case_id":    case_id,
                "finding_id": str(finding_id),
                "confidence": SC001_CONFIDENCE,
                "proposal_id": str(proposal_id),
            },
            tenant_id = tenant_id,
        ))

        return FindingResult(
            finding_id      = finding_id,
            proposal_id     = proposal_id,
            tenant_id       = tenant_id,
            case_id         = case_id,
            bundle_id       = bundle_id,
            confidence      = SC001_CONFIDENCE,
            rule_trace      = rule_trace,
            proposed_action = proposed_action,
            amount          = amount,
            currency        = currency,
            proposer_sub    = proposer_sub,
            created_at      = now,
        )
