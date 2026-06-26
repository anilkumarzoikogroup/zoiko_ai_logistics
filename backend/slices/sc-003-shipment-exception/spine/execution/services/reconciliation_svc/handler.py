"""
SC-003 Reconciliation — "Commitment Match" strategy.

Matches:  committed ETA  vs  actual_delivery  timestamp from carrier.
Writes:   reconciliations  +  case_outcomes  +  reconciliation_variances (if drift > threshold).
"""
import uuid
import hashlib
import json
from datetime import datetime, timezone

import paths  # noqa: F401

from shared.db import q, q1, DB_URL as _DEFAULT_DB_URL
from shared.signer import sign as _sign


_BREACH_TOLERANCE_HOURS = 0.25   # 15-min grace window before raising a variance


class ReconciliationHandler:

    def __init__(self, db_url: str | None = None, broker=None):
        self._db_url = db_url or _DEFAULT_DB_URL
        self._broker = broker

    # ── Public ────────────────────────────────────────────────────────────────

    def reconcile(
        self,
        tenant_id:   str,
        case_id:     str,
        envelope_id: str,
        actor_sub:   str,
    ) -> dict:
        """Run Commitment Match against the case's committed_eta / actual_delivery."""
        case_row = q1("""
            SELECT id::text, state, shipment_reference, carrier_id,
                   committed_eta, actual_delivery,
                   sla_breach_hours, sla_penalty_amount, currency
            FROM   cases
            WHERE  id=%s::uuid AND tenant_id=%s::uuid
        """, (case_id, tenant_id))

        if not case_row:
            return {"status": "ERROR", "detail": "Case not found"}

        committed_eta   = case_row["committed_eta"]
        actual_delivery = case_row["actual_delivery"]

        if committed_eta is None or actual_delivery is None:
            return {"status": "ERROR", "detail": "Missing committed_eta or actual_delivery on case"}

        # Ensure tz-aware
        if committed_eta.tzinfo is None:
            committed_eta = committed_eta.replace(tzinfo=timezone.utc)
        if actual_delivery.tzinfo is None:
            actual_delivery = actual_delivery.replace(tzinfo=timezone.utc)

        breach_hours   = max(0.0, (actual_delivery - committed_eta).total_seconds() / 3600)
        stored_hours   = float(case_row["sla_breach_hours"] or 0)
        delta_hours    = abs(breach_hours - stored_hours)
        match_status   = "MATCHED" if delta_hours <= _BREACH_TOLERANCE_HOURS else "VARIANCE"

        rec_id     = self._write_reconciliation(
            tenant_id, case_id, envelope_id, actor_sub,
            case_row, breach_hours, match_status,
        )
        outcome_id = self._write_outcome(tenant_id, case_id, rec_id, actor_sub, match_status)

        if match_status == "VARIANCE":
            self._write_variance(
                tenant_id, case_id, rec_id,
                stored_hours, breach_hours, delta_hours,
            )

        self._advance_case(tenant_id, case_id, actor_sub)
        self._publish_kafka(tenant_id, case_id, str(rec_id), match_status)

        return {
            "status":               match_status,
            "reconciliation_id":    str(rec_id),
            "outcome_id":           str(outcome_id),
            "case_id":              case_id,
            "shipment_reference":   case_row["shipment_reference"],
            "committed_eta":        committed_eta.isoformat(),
            "actual_delivery":      actual_delivery.isoformat(),
            "breach_hours_stored":  stored_hours,
            "breach_hours_computed": breach_hours,
            "delta_hours":          delta_hours,
            "reconciled_at":        datetime.now(timezone.utc).isoformat(),
        }

    def get_variances(self, tenant_id: str, case_id: str) -> list[dict]:
        rows = q("""
            SELECT id::text, expected_value, actual_value,
                   delta, variance_type, status, created_at
            FROM   variance_records
            WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
            ORDER BY created_at ASC
        """, (case_id, tenant_id))
        return [_serialize(r) for r in rows]

    def resolve_variance(
        self,
        tenant_id:   str,
        case_id:     str,
        variance_id: str,
        resolution:  str,   # "RESOLVED" | "WAIVED"
        actor_sub:   str,
        note:        str = "",
    ) -> dict:
        q("""
            UPDATE variance_records
            SET    status=%s, resolved_by=%s, resolved_at=NOW()
            WHERE  id=%s::uuid AND case_id=%s::uuid AND tenant_id=%s::uuid
        """, (resolution, actor_sub, variance_id, case_id, tenant_id))
        return {"status": resolution, "variance_id": variance_id}

    # ── DB writes ─────────────────────────────────────────────────────────────

    def _write_reconciliation(
        self, tenant_id, case_id, envelope_id, actor_sub,
        case_row, breach_hours: float, match_status: str,
    ) -> uuid.UUID:
        rec_id = uuid.uuid4()
        q("""
            INSERT INTO reconciliations
                (id, tenant_id, case_id, envelope_id, match_type,
                 match_status, matched_amount, currency, actor_sub,
                 metadata, created_at)
            VALUES (%s, %s::uuid, %s::uuid, %s::uuid,
                    'COMMITMENT_MATCH', %s,
                    %s, %s, %s,
                    %s::jsonb, NOW())
            ON CONFLICT DO NOTHING
        """, (
            rec_id, tenant_id, case_id, envelope_id,
            match_status,
            float(case_row["sla_penalty_amount"] or 0),
            case_row["currency"] or "INR",
            actor_sub,
            json.dumps({
                "shipment_reference": case_row["shipment_reference"],
                "breach_hours":       breach_hours,
            }),
        ))
        return rec_id

    def _write_outcome(
        self, tenant_id, case_id, rec_id, actor_sub, match_status,
    ) -> uuid.UUID:
        outcome_id   = uuid.uuid4()
        outcome_type = "SLA_CREDIT_ISSUED" if match_status == "MATCHED" else "SLA_CREDIT_VARIANCE"
        payload      = json.dumps({"case_id": case_id, "recon_id": str(rec_id), "outcome_type": outcome_type})
        outcome_hash = hashlib.sha256(b"zoiko.outcome.v1:" + payload.encode()).digest()
        sig_bytes, kid = _sign("default", outcome_hash)
        q("""
            INSERT INTO outcomes
                (id, tenant_id, case_id, recon_id,
                 outcome_type, outcome_hash, signature, kid, recorded_at)
            VALUES (%s, %s::uuid, %s::uuid, %s,
                    %s, %s, %s, %s, NOW())
            ON CONFLICT DO NOTHING
        """, (
            outcome_id, tenant_id, case_id, str(rec_id),
            outcome_type, outcome_hash, sig_bytes, kid,
        ))
        return outcome_id

    def _write_variance(
        self, tenant_id, case_id, rec_id,
        expected: float, actual: float, delta: float,
    ) -> None:
        q("""
            INSERT INTO variance_records
                (id, tenant_id, case_id,
                 expected_value, actual_value, delta,
                 variance_type, status, created_at)
            VALUES (gen_random_uuid(), %s::uuid, %s::uuid,
                    %s, %s, %s,
                    'BREACH_DELTA', 'OPEN', NOW())
        """, (
            tenant_id, case_id,
            round(expected, 4), round(actual, 4), round(delta, 4),
        ))

    def _advance_case(self, tenant_id: str, case_id: str, actor_sub: str) -> None:
        q("""
            UPDATE cases SET state='OUTCOME_RECORDED'
            WHERE  id=%s::uuid AND tenant_id=%s::uuid AND state='DISPATCHED'
        """, (case_id, tenant_id))
        q("""
            INSERT INTO case_events
                (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
            VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'STATE_TRANSITION',
                    'DISPATCHED', 'OUTCOME_RECORDED', %s,
                    '{"match_type":"COMMITMENT_MATCH"}'::jsonb, NOW())
        """, (tenant_id, case_id, actor_sub))

    def _publish_kafka(self, tenant_id: str, case_id: str, rec_id: str, status: str) -> None:
        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            prod = ZoikoProducer(self._broker)
            prod.publish(KafkaMessage(
                topic="zoiko.reconciliation.updated", key=case_id,
                payload={"case_id": case_id, "reconciliation_id": rec_id, "status": status},
                tenant_id=tenant_id,
            ))
        except Exception:
            pass


def _serialize(r: dict) -> dict:
    out = {}
    for k, v in r.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif hasattr(v, "hex"):
            out[k] = str(v)
        else:
            out[k] = v
    return out
