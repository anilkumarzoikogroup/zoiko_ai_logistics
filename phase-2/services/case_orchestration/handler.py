"""
Case Orchestration Service — opens a dispute case, manages the state machine,
and appends APPEND-ONLY case_events for every transition.

State machine:
  OPENED → EVIDENCE_GATHERING → UNDER_REVIEW → PENDING_APPROVAL
  → APPROVED → EXECUTED → RECONCILED → CLOSED
  (any state) → REJECTED
"""
import json, uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401 — registers UUID adapter

from services.case_orchestration.models import CaseResult

VALID_TRANSITIONS = {
    "OPENED":            {"EVIDENCE_GATHERING", "REJECTED"},
    "EVIDENCE_GATHERING":{"UNDER_REVIEW",       "REJECTED"},
    "UNDER_REVIEW":      {"PENDING_APPROVAL",   "REJECTED"},
    "PENDING_APPROVAL":  {"APPROVED",            "REJECTED"},
    "APPROVED":          {"EXECUTED",            "REJECTED"},
    "EXECUTED":          {"RECONCILED"},
    "RECONCILED":        {"CLOSED"},
}


class CaseHandler:
    def __init__(self, db_url: str, kafka_broker):
        self.db_url = db_url
        self.broker = kafka_broker

    def open_case(
        self,
        tenant_id: str,
        canonical_invoice_id: uuid.UUID,
        actor_sub: str = "system",
    ) -> CaseResult:
        tenant_id            = str(tenant_id)
        canonical_invoice_id = uuid.UUID(str(canonical_invoice_id))
        now                  = datetime.now(timezone.utc)

        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # UNIQUE (tenant_id, invoice_id) — idempotent
            case_id = uuid.uuid4()
            cur.execute("""
                INSERT INTO cases (id, tenant_id, invoice_id, state, opened_at)
                VALUES (%s, %s, %s, 'OPENED', %s)
                ON CONFLICT (tenant_id, invoice_id) DO NOTHING
                RETURNING id, state, opened_at
            """, (case_id, tenant_id, canonical_invoice_id, now))
            row = cur.fetchone()

            is_new = row is not None
            if not is_new:
                cur.execute(
                    "SELECT id, state, opened_at FROM cases WHERE tenant_id=%s AND invoice_id=%s",
                    (tenant_id, canonical_invoice_id),
                )
                row = cur.fetchone()
                case_id = row["id"]

            if is_new:
                # APPEND-ONLY: log the CASE_OPENED event
                cur.execute("""
                    INSERT INTO case_events
                        (id, tenant_id, case_id, event_type, from_state, to_state,
                         actor_sub, payload, occurred_at)
                    VALUES (%s, %s, %s, 'CASE_OPENED', NULL, 'OPENED', %s, %s::jsonb, %s)
                """, (
                    uuid.uuid4(), tenant_id, case_id,
                    actor_sub,
                    json.dumps({"invoice_id": str(canonical_invoice_id)}),
                    now,
                ))

            conn.commit()
        finally:
            conn.close()

        if is_new:
            # Publish case.opened
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self.broker).publish(KafkaMessage(
                topic     = "case.opened",
                key       = str(case_id),
                payload   = {
                    "case_id":    str(case_id),
                    "invoice_id": str(canonical_invoice_id),
                    "state":      "OPENED",
                },
                tenant_id = tenant_id,
            ))

        return CaseResult(
            case_id    = case_id,
            tenant_id  = tenant_id,
            invoice_id = canonical_invoice_id,
            state      = "OPENED" if is_new else row["state"],
            opened_at  = now if is_new else row["opened_at"],
            is_new     = is_new,
        )

    def transition_state(
        self,
        tenant_id: str,
        case_id: uuid.UUID,
        new_state: str,
        actor_sub: str,
        payload: dict = None,
    ) -> str:
        tenant_id = str(tenant_id)
        case_id   = uuid.UUID(str(case_id))
        conn      = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT state FROM cases WHERE id=%s AND tenant_id=%s",
                (case_id, tenant_id),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Case {case_id} not found for tenant {tenant_id}")

            current = row["state"]
            allowed = VALID_TRANSITIONS.get(current, set())
            if new_state not in allowed:
                raise ValueError(
                    f"Invalid transition: {current} → {new_state}. Allowed: {allowed}"
                )

            now = datetime.now(timezone.utc)
            cur.execute(
                "UPDATE cases SET state=%s WHERE id=%s AND tenant_id=%s",
                (new_state, case_id, tenant_id),
            )

            # APPEND-ONLY case_event
            cur.execute("""
                INSERT INTO case_events
                    (id, tenant_id, case_id, event_type, from_state, to_state,
                     actor_sub, payload, occurred_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id, case_id,
                f"TRANSITION_{new_state}",
                current, new_state,
                actor_sub,
                json.dumps(payload or {}),
                now,
            ))
            conn.commit()
        finally:
            conn.close()

        # Publish case.updated
        from kafka.producer import ZoikoProducer, KafkaMessage
        ZoikoProducer(self.broker).publish(KafkaMessage(
            topic     = "case.updated",
            key       = str(case_id),
            payload   = {"case_id": str(case_id), "from_state": current, "to_state": new_state},
            tenant_id = tenant_id,
        ))

        return new_state
