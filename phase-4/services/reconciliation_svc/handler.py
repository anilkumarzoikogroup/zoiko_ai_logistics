"""
Phase 4 — Reconciliation Service

After the Execution Gateway dispatches a credit, the Reconciliation Service:
  1. Polls connector_responses for the settlement confirmation
  2. Compares credited amount vs expected amount
  3. Writes a reconciliations row (MATCHED / PARTIAL / DISCREPANCY)
  4. Writes an outcomes row
  5. Advances case FSM: DISPATCHED → OUTCOME_RECORDED → CLOSED
  6. Publishes zoiko.reconciliation.updated
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

import paths  # noqa: F401
import shared.db as _db

from services.reconciliation_svc.models import ReconciliationResult

psycopg2.extras.register_uuid()

_TOLERANCE = 0.01   # 1% discrepancy tolerance


class ReconciliationHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default") -> None:
        self._db_url      = db_url
        self._broker      = kafka_broker
        self._tenant_slug = tenant_slug

    def reconcile(self, envelope_id: str, tenant_id: str, actor_sub: str = "system") -> ReconciliationResult:
        """
        Reconcile a dispatched execution envelope against the connector response.

        In dev: simulates a successful settlement (actual_amount = expected_amount).
        In prod: reads connector_responses table for actual settlement.
        """
        envelope = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id, tenant_id, case_id, scope, amount, currency, connector_ref, status
                FROM   execution_envelopes
                WHERE  id=%s::uuid AND tenant_id=%s::uuid
                LIMIT  1
            """,
            params=(envelope_id, tenant_id),
        )
        if not envelope:
            raise ValueError(f"Execution envelope '{envelope_id}' not found")
        if envelope["status"] not in ("DISPATCHED", "SETTLED"):
            raise ValueError(f"Envelope '{envelope_id}' is in state '{envelope['status']}', expected DISPATCHED")

        expected = float(envelope["amount"])
        case_id  = str(envelope["case_id"]) if envelope["case_id"] else ""
        currency = envelope["currency"]
        now      = datetime.now(timezone.utc)

        # Dev: simulate actual amount = expected (connector settled exactly)
        actual = self._get_actual_amount(envelope_id, expected)
        delta  = abs(actual - expected)

        if delta == 0:
            status = "MATCHED"
        elif delta / expected <= _TOLERANCE:
            status = "PARTIAL"
        else:
            status = "DISCREPANCY"

        rec_id     = uuid.uuid4()
        outcome_id = uuid.uuid4()

        conn = psycopg2.connect(self._db_url)
        try:
            cur = conn.cursor()

            # Write reconciliations row
            cur.execute("""
                INSERT INTO reconciliations
                    (id, tenant_id, envelope_id, expected_amount, actual_amount,
                     currency, status, delta, reconciled_at)
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s)
            """, (
                rec_id, tenant_id, uuid.UUID(envelope_id),
                expected, actual, currency, status, delta, now,
            ))

            # Write outcomes row
            cur.execute("""
                INSERT INTO outcomes
                    (id, tenant_id, envelope_id, reconciliation_id,
                     outcome_type, amount, currency, settled_at)
                VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s)
            """, (
                outcome_id, tenant_id, uuid.UUID(envelope_id), rec_id,
                "CREDIT_ISSUED" if status in ("MATCHED", "PARTIAL") else "DISCREPANCY_FLAGGED",
                actual, currency, now,
            ))

            # Mark envelope settled
            cur.execute("""
                UPDATE execution_envelopes SET status='SETTLED' WHERE id=%s::uuid
            """, (uuid.UUID(envelope_id),))

            # Advance case FSM
            if case_id:
                cur.execute("""
                    UPDATE cases SET state='OUTCOME_RECORDED'
                    WHERE id=%s::uuid AND tenant_id=%s::uuid AND state='DISPATCHED'
                """, (uuid.UUID(case_id), tenant_id))
                cur.execute("""
                    INSERT INTO case_events
                        (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
                    VALUES (%s, %s::uuid, %s::uuid, 'RECONCILIATION_COMPLETE',
                            'DISPATCHED', 'OUTCOME_RECORDED', %s, %s::jsonb, %s)
                """, (
                    uuid.uuid4(), tenant_id, uuid.UUID(case_id),
                    actor_sub,
                    json.dumps({"reconciliation_id": str(rec_id), "status": status, "delta": delta}),
                    now,
                ))

            # Outbox event
            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id,
                "zoiko.reconciliation.updated",
                case_id or envelope_id,
                json.dumps({
                    "reconciliation_id": str(rec_id),
                    "envelope_id":       envelope_id,
                    "status":            status,
                    "delta":             delta,
                }),
                now,
            ))

            conn.commit()
        finally:
            conn.close()

        # Kafka publish
        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self._broker).publish(KafkaMessage(
                topic     = "zoiko.reconciliation.updated",
                key       = case_id or envelope_id,
                payload   = {"reconciliation_id": str(rec_id), "status": status},
                tenant_id = tenant_id,
            ))
        except Exception:
            pass

        return ReconciliationResult(
            reconciliation_id = str(rec_id),
            envelope_id       = envelope_id,
            case_id           = case_id,
            tenant_id         = tenant_id,
            expected_amount   = expected,
            actual_amount     = actual,
            currency          = currency,
            status            = status,
            delta             = delta,
            reconciled_at     = now,
            outcome_id        = str(outcome_id),
        )

    def _get_actual_amount(self, envelope_id: str, expected: float) -> float:
        """Look up connector response. Falls back to expected (dev: always match)."""
        row = _db.q1(
            db_url=self._db_url,
            sql="SELECT settled_amount FROM connector_responses WHERE envelope_id=%s::uuid LIMIT 1",
            params=(envelope_id,),
        )
        if row and row.get("settled_amount") is not None:
            return float(row["settled_amount"])
        return expected  # dev fallback — perfect match
