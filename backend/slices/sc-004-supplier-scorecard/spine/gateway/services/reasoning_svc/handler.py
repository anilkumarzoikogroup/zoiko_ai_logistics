"""
SC-004 Reasoning Service — Domain 8.

Applies the SC-004 confidence rules to the scorecard evidence bundle and
produces a finding record with:
  - confidence: SC004_CONFIDENCE = 0.9640 (deterministic, never change)
  - finding_type: "aggregation"
  - proposed_action: "NOTIFY_FLAG"
  - rule_traces: breach_detected_rule + data_coverage_rule
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401

from shared.signer import sign
from zoiko_common.crypto.jcs import canonicalize
from services.reasoning_svc.rules import SC004_CONFIDENCE, compute_rule_traces


class ReasoningHandler:
    def __init__(self, db_url: str, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.tenant_slug = tenant_slug

    def produce_finding(
        self,
        tenant_id:       str,
        case_id:         str,
        bundle_id:       str,
        composite_score: float,
        threshold:       float,
        total_claims:    int,
        sla_cases:       int,
    ) -> dict:
        """
        Apply SC-004 confidence rules to the evidence bundle and write a finding.
        Returns finding_id, confidence, proposed_action, rule_traces.
        """
        tenant_id = str(tenant_id)
        case_id   = str(case_id)
        bundle_id = str(bundle_id)
        now       = datetime.now(timezone.utc)

        rule_traces = compute_rule_traces(composite_score, threshold, total_claims, sla_cases)

        finding_payload = {
            "bundle_id":       bundle_id,
            "case_id":         case_id,
            "composite_score": composite_score,
            "confidence":      SC004_CONFIDENCE,
            "finding_type":    "aggregation",
            "proposed_action": "NOTIFY_FLAG",
            "rule_traces":     rule_traces,
            "tenant_id":       tenant_id,
            "threshold":       threshold,
        }
        finding_bytes = canonicalize(finding_payload)
        finding_hash  = hashlib.sha256(b"zoiko.finding.v1:" + finding_bytes).digest()
        sig, kid      = sign(self.tenant_slug, finding_hash)

        finding_id = uuid.uuid4()

        psycopg2.extras.register_uuid()
        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO findings
                    (id, tenant_id, case_id, bundle_id,
                     finding_type, confidence, finding_hash,
                     rule_trace, signature, kid, created_at)
                VALUES (%s, %s::uuid, %s::uuid, %s::uuid,
                        %s, %s, %s, %s::jsonb, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                str(finding_id), tenant_id, case_id, bundle_id,
                "aggregation", SC004_CONFIDENCE, finding_hash,
                json.dumps(rule_traces), sig, kid, now,
            ))

            # Advance case from EVIDENCE_PENDING → FINDING_GENERATED
            cur.execute(
                "UPDATE cases SET state='FINDING_GENERATED' "
                "WHERE id=%s::uuid AND tenant_id=%s::uuid AND state='EVIDENCE_PENDING'",
                (case_id, tenant_id),
            )
            cur.execute("""
                INSERT INTO case_events
                    (id, tenant_id, case_id, event_type, from_state, to_state,
                     actor_sub, payload, occurred_at)
                VALUES (gen_random_uuid(), %s::uuid, %s::uuid,
                        'FINDING_GENERATED', 'EVIDENCE_PENDING', 'FINDING_GENERATED',
                        'system', %s::jsonb, %s)
            """, (
                tenant_id, case_id,
                json.dumps({"finding_id": str(finding_id), "confidence": SC004_CONFIDENCE}),
                now,
            ))
            conn.commit()
        finally:
            conn.close()

        return {
            "finding_id":      str(finding_id),
            "confidence":      SC004_CONFIDENCE,
            "finding_type":    "aggregation",
            "proposed_action": "NOTIFY_FLAG",
            "rule_traces":     rule_traces,
        }
