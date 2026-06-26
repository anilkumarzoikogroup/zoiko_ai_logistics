"""
SC-003 Case Orchestration — opens and transitions SHIPMENT_EXCEPTION cases.

State machine (spec-aligned §7.5 — same as SC-001/002):
  NEW → EVIDENCE_PENDING → FINDING_GENERATED → APPROVAL_PENDING
  → EXECUTION_READY → DISPATCHED → OUTCOME_RECORDED → CLOSED
  (any state) → ABORTED
"""
import json
import uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401

from services.case_orchestration.models import CaseResult


class ConflictError(Exception):
    pass


VALID_TRANSITIONS = {
    "NEW":               {"EVIDENCE_PENDING", "ABORTED"},
    "EVIDENCE_PENDING":  {"FINDING_GENERATED", "ABORTED"},
    "FINDING_GENERATED": {"APPROVAL_PENDING", "ABORTED"},
    "APPROVAL_PENDING":  {"EXECUTION_READY", "ABORTED"},
    "EXECUTION_READY":   {"DISPATCHED", "ABORTED"},
    "DISPATCHED":        {"OUTCOME_RECORDED"},
    "OUTCOME_RECORDED":  {"CLOSED"},
}


class CaseHandler:
    def __init__(self, db_url: str, kafka_broker):
        self.db_url = db_url
        self.broker = kafka_broker

    def open_case(
        self,
        tenant_id: str,
        shipment_reference: str,
        committed_eta: datetime,
        actual_delivery: datetime,
        sla_breach_hours: float,
        sla_penalty_amount: float,
        actor_sub: str = "system",
    ) -> CaseResult:
        tenant_id = str(tenant_id)
        now       = datetime.now(timezone.utc)
        case_id   = uuid.uuid4()

        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute("""
                INSERT INTO cases (
                    id, tenant_id, case_type, state, opened_at,
                    shipment_reference, committed_eta, actual_delivery,
                    sla_breach_hours, sla_penalty_amount
                )
                VALUES (%s, %s, 'SHIPMENT_EXCEPTION', 'NEW', %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, shipment_reference) WHERE sla_breach_hours IS NOT NULL
                DO NOTHING
                RETURNING id, state, opened_at
            """, (case_id, tenant_id, now, shipment_reference, committed_eta, actual_delivery, sla_breach_hours, sla_penalty_amount))
            row = cur.fetchone()

            if row is None:
                # Should not happen without ON CONFLICT — treat as new
                row = {"id": case_id, "state": "NEW", "opened_at": now}

            actual_case_id = row["id"] if isinstance(row, dict) else row[0]

            # Tag shipment events with this case_id
            cur.execute(
                "UPDATE shipment_events SET case_id=%s WHERE tenant_id=%s AND shipment_reference=%s AND case_id IS NULL",
                (actual_case_id, tenant_id, shipment_reference),
            )

            # Append CASE_OPENED event
            cur.execute("""
                INSERT INTO case_events
                    (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
                VALUES (%s, %s, %s, 'CASE_OPENED', NULL, 'NEW', %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id, actual_case_id, actor_sub,
                json.dumps({"case_type": "SHIPMENT_EXCEPTION", "shipment_reference": shipment_reference}),
                now,
            ))

            conn.commit()

            state     = row["state"]      if isinstance(row, dict) else "NEW"
            opened_at = row["opened_at"]  if isinstance(row, dict) else now

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return CaseResult(case_id=actual_case_id, state=state, opened_at=opened_at, is_new=True)

    def transition_state(
        self, tenant_id: str, case_id: str, to_state: str, actor_sub: str = "system"
    ) -> None:
        case_uuid = uuid.UUID(case_id)
        tenant_id = str(tenant_id)
        now       = datetime.now(timezone.utc)

        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT state FROM cases WHERE id=%s AND tenant_id=%s",
                (case_uuid, tenant_id),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Case {case_id} not found")

            from_state = row["state"] if isinstance(row, dict) else row[0]
            valid = VALID_TRANSITIONS.get(from_state, set())
            if to_state not in valid:
                raise ValueError(f"Transition {from_state}→{to_state} not allowed")

            cur.execute(
                "UPDATE cases SET state=%s WHERE id=%s AND tenant_id=%s",
                (to_state, case_uuid, tenant_id),
            )
            cur.execute("""
                INSERT INTO case_events
                    (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
                VALUES (%s, %s, %s, 'STATE_TRANSITION', %s, %s, %s, '{}'::jsonb, %s)
            """, (uuid.uuid4(), tenant_id, case_uuid, from_state, to_state, actor_sub, now))

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
