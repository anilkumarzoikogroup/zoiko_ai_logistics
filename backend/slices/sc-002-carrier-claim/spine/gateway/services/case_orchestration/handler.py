"""
Case Orchestration Service — opens a dispute case, manages the state machine,
and appends APPEND-ONLY case_events for every transition.

State machine (spec-aligned §7.5):
  NEW → EVIDENCE_PENDING → FINDING_GENERATED → APPROVAL_PENDING
  → EXECUTION_READY → DISPATCHED → OUTCOME_RECORDED → CLOSED
  (any state) → ABORTED
"""
import json, uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401 — registers UUID adapter

from services.case_orchestration.models import CaseResult

class ConflictError(Exception):
    """Raised on OCC stale-version mismatch (HTTP 409)."""


VALID_TRANSITIONS = {
    "NEW":               {"EVIDENCE_PENDING",  "ABORTED", "CLOSED_DUPLICATE"},
    "EVIDENCE_PENDING":  {"FINDING_GENERATED", "ABORTED"},
    "FINDING_GENERATED": {"APPROVAL_PENDING",  "ABORTED", "UNDER_REVIEW", "ACTION_PLAN_READY"},
    "APPROVAL_PENDING":  {"EXECUTION_READY",   "ABORTED", "READY_FOR_AUTHORIZATION"},
    "EXECUTION_READY":   {"DISPATCHED",        "ABORTED", "EXECUTING"},
    "DISPATCHED":        {"OUTCOME_RECORDED",  "AWAITING_EXTERNAL_RESPONSE"},
    "OUTCOME_RECORDED":  {"CLOSED",            "RECONCILING"},

    # Clarification 05 — case-candidate review and action-plan/authorization chain
    "UNDER_REVIEW":               {"ACTION_PLAN_READY", "CLOSED_REJECTED", "CLOSED_NO_ACTION"},
    "ACTION_PLAN_READY":          {"READY_FOR_AUTHORIZATION", "CLOSED_NO_ACTION"},
    "READY_FOR_AUTHORIZATION":    {"AUTHORIZED", "ABORTED"},
    "AUTHORIZED":                 {"EXECUTING", "ABORTED"},
    "EXECUTING":                  {"AWAITING_EXTERNAL_RESPONSE", "DISPATCHED", "ABORTED"},
    "AWAITING_EXTERNAL_RESPONSE": {"RECONCILING"},
    "RECONCILING":                {"CLOSED_RECOVERED", "CLOSED_UNRECOVERABLE"},
}

# ESCALATED / QUARANTINED are reachable from any non-terminal state (Clarification 05 §8)
ESCALATION_STATES = {"ESCALATED", "QUARANTINED"}


class CaseHandler:
    def __init__(self, db_url: str, kafka_broker):
        self.db_url = db_url
        self.broker = kafka_broker

    def open_case(
        self,
        tenant_id: str,
        claim_id: uuid.UUID,
        actor_sub: str = "system",
    ) -> CaseResult:
        """Open a case against a carrier claim."""
        tenant_id = str(tenant_id)
        case_type = "CARRIER_CLAIM"
        claim_id  = uuid.UUID(str(claim_id))
        now       = datetime.now(timezone.utc)

        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # UNIQUE per subject (tenant_id, claim_id) — idempotent
            case_id = uuid.uuid4()
            cur.execute("""
                INSERT INTO cases (id, tenant_id, claim_id, case_type, state, opened_at)
                VALUES (%s, %s, %s, %s, 'NEW', %s)
                ON CONFLICT (tenant_id, claim_id) WHERE claim_id IS NOT NULL DO NOTHING
                RETURNING id, state, opened_at
            """, (case_id, tenant_id, claim_id, case_type, now))
            row = cur.fetchone()

            is_new = row is not None
            if not is_new:
                cur.execute(
                    "SELECT id, state, opened_at FROM cases WHERE tenant_id=%s AND claim_id=%s",
                    (tenant_id, claim_id),
                )
                row = cur.fetchone()
                case_id = row["id"]

            if is_new:
                # APPEND-ONLY: log the CASE_OPENED event
                event_payload = {"claim_id": str(claim_id)}
                cur.execute("""
                    INSERT INTO case_events
                        (id, tenant_id, case_id, event_type, from_state, to_state,
                         actor_sub, payload, occurred_at)
                    VALUES (%s, %s, %s, 'CASE_OPENED', NULL, 'NEW', %s, %s::jsonb, %s)
                """, (
                    uuid.uuid4(), tenant_id, case_id,
                    actor_sub,
                    json.dumps(event_payload),
                    now,
                ))

            conn.commit()
        finally:
            conn.close()

        if is_new:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self.broker).publish(KafkaMessage(
                topic     = "zoiko.case.opened",
                key       = str(case_id),
                payload   = {
                    "case_id":   str(case_id),
                    "claim_id":  str(claim_id),
                    "case_type": case_type,
                    "state":     "NEW",
                },
                tenant_id = tenant_id,
            ))

        return CaseResult(
            case_id    = case_id,
            tenant_id  = tenant_id,
            state      = "NEW" if is_new else row["state"],
            opened_at  = now if is_new else row["opened_at"],
            is_new     = is_new,
            case_type  = case_type,
            claim_id   = claim_id,
        )

    def transition_state(
        self,
        tenant_id: str,
        case_id: uuid.UUID,
        new_state: str,
        actor_sub: str,
        payload: dict = None,
        expected_version: int = None,
    ) -> str:
        """
        Advance the FSM to new_state.

        If expected_version is provided (OCC / T-016):
          - 409 ConflictError is raised if cases.version != expected_version.
          - version is incremented atomically in the same UPDATE.

        If expected_version is None (legacy / internal callers):
          - No version check is performed (backward-compatible).
        """
        tenant_id = str(tenant_id)
        case_id   = uuid.UUID(str(case_id))
        conn      = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT state, version FROM cases WHERE id=%s AND tenant_id=%s",
                (case_id, tenant_id),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Case {case_id} not found for tenant {tenant_id}")

            current = row["state"]
            allowed = VALID_TRANSITIONS.get(current, set())

            # Clarification 05 §8 — ESCALATED/QUARANTINED reachable from any
            # non-terminal state (terminal = CLOSED* or ABORTED)
            is_terminal = current == "ABORTED" or current.startswith("CLOSED")
            if new_state in ESCALATION_STATES and not is_terminal:
                allowed = allowed | ESCALATION_STATES

            if new_state not in allowed:
                # T-014: invalid FSM transition → emit security event then 422
                try:
                    from kafka.producer import ZoikoProducer, KafkaMessage
                    ZoikoProducer(self.broker).publish(KafkaMessage(
                        topic     = "zoiko.security.event-detected.v1",
                        key       = str(case_id),
                        payload   = {
                            "event_type":   "INVALID_FSM_TRANSITION",
                            "case_id":      str(case_id),
                            "from_state":   current,
                            "to_state":     new_state,
                            "actor_sub":    actor_sub,
                            "allowed":      sorted(allowed),
                        },
                        tenant_id = tenant_id,
                    ))
                except Exception:
                    pass
                raise ValueError(
                    f"Invalid transition: {current} → {new_state}. Allowed: {sorted(allowed)}"
                )

            # OCC check (T-016)
            if expected_version is not None:
                actual_version = row.get("version", 1)
                if actual_version != expected_version:
                    raise ConflictError(
                        f"Stale version: expected {expected_version}, got {actual_version}. "
                        "Reload the case and retry."
                    )

            now = datetime.now(timezone.utc)
            if expected_version is not None:
                cur.execute(
                    "UPDATE cases SET state=%s, version=version+1 WHERE id=%s AND tenant_id=%s AND version=%s",
                    (new_state, case_id, tenant_id, expected_version),
                )
                if cur.rowcount == 0:
                    raise ConflictError("Concurrent modification detected — retry with latest version")
            else:
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

        from kafka.producer import ZoikoProducer, KafkaMessage
        ZoikoProducer(self.broker).publish(KafkaMessage(
            topic     = "zoiko.case.updated",
            key       = str(case_id),
            payload   = {"case_id": str(case_id), "from_state": current, "to_state": new_state},
            tenant_id = tenant_id,
        ))

        return new_state
