"""
SC-004 Case Orchestration — Domain 6.

Manages the SCORECARD_BREACH case FSM.

States: NEW → EVIDENCE_PENDING → FINDING_GENERATED → APPROVAL_PENDING
      → EXECUTION_READY → DISPATCHED → OUTCOME_RECORDED → CLOSED
      → ABORTED (from any state)
"""
import json
import uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401


class CaseOrchestrationHandler:
    def __init__(self, db_url: str):
        self.db_url = db_url

    def open_case(
        self,
        tenant_id:    str,
        scorecard_id: str,
        carrier_id:   str,
        actor_sub:    str = "system",
    ) -> dict:
        """Open a SCORECARD_BREACH case for a supplier breach. Returns case_id."""
        tenant_id    = str(tenant_id)
        scorecard_id = str(scorecard_id)
        now          = datetime.now(timezone.utc)
        case_id      = uuid.uuid4()

        psycopg2.extras.register_uuid()
        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO cases
                    (id, tenant_id, case_type, state, scorecard_period_id, opened_at)
                VALUES (%s, %s::uuid, 'SCORECARD_BREACH', 'EVIDENCE_PENDING', %s::uuid, %s)
                ON CONFLICT DO NOTHING
            """, (str(case_id), tenant_id, scorecard_id, now))

            cur.execute("""
                INSERT INTO case_events
                    (id, tenant_id, case_id, event_type, from_state, to_state,
                     actor_sub, payload, occurred_at)
                VALUES (gen_random_uuid(), %s::uuid, %s::uuid,
                        'CASE_OPENED', 'NEW', 'EVIDENCE_PENDING',
                        %s, %s::jsonb, %s)
            """, (
                tenant_id, str(case_id), actor_sub,
                json.dumps({"scorecard_period_id": scorecard_id, "carrier_id": carrier_id}),
                now,
            ))
            conn.commit()
        finally:
            conn.close()

        return {"case_id": str(case_id), "state": "EVIDENCE_PENDING"}

    def advance(
        self,
        tenant_id:  str,
        case_id:    str,
        from_state: str,
        to_state:   str,
        event_type: str,
        actor_sub:  str = "system",
        payload:    dict | None = None,
    ) -> dict:
        """Advance case FSM from one state to the next. Append-only event log."""
        now = datetime.now(timezone.utc)

        psycopg2.extras.register_uuid()
        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE cases SET state=%s WHERE id=%s::uuid AND tenant_id=%s::uuid AND state=%s",
                (to_state, case_id, tenant_id, from_state),
            )
            cur.execute("""
                INSERT INTO case_events
                    (id, tenant_id, case_id, event_type, from_state, to_state,
                     actor_sub, payload, occurred_at)
                VALUES (gen_random_uuid(), %s::uuid, %s::uuid,
                        %s, %s, %s, %s, %s::jsonb, %s)
            """, (
                tenant_id, case_id, event_type,
                from_state, to_state, actor_sub,
                json.dumps(payload or {}), now,
            ))
            conn.commit()
        finally:
            conn.close()

        return {"case_id": case_id, "state": to_state}

    def get_case(self, tenant_id: str, case_id: str) -> dict:
        psycopg2.extras.register_uuid()
        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT id, state, case_type, scorecard_period_id, opened_at "
                "FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid",
                (case_id, tenant_id),
            )
            row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            raise ValueError(f"Case {case_id} not found")
        return {
            "case_id":             str(row["id"]),
            "state":               row["state"],
            "case_type":           row["case_type"],
            "scorecard_period_id": str(row["scorecard_period_id"]) if row["scorecard_period_id"] else None,
            "opened_at":           row["opened_at"].isoformat(),
        }
