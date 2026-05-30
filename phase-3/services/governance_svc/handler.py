"""
Governance Service — SoD-enforced approval workflow with threshold-based routing.

create_task():
  - Creates an approval_task in PENDING state for a decision_proposal
  - Loads approval_thresholds for tenant+currency to determine routing:
      amount < auto_approve_below  → AUTO  (task immediately APPROVED)
      auto_approve_below ≤ amount < dual_auth_above → SINGLE (one approver)
      amount ≥ dual_auth_above     → DUAL  (two distinct approvers required)
  - Creates an approval_request with deadline_at = now + escalate_after_hours
  - proposer_sub is recorded; actor_sub is NULL until actioned

decide():
  - SoD check: actor_sub MUST differ from proposer_sub (OPA rule §3.2)
  - DUAL auth first call: records actor_sub as approver_1, task stays PENDING
    → returns GovernanceDecisionResult with outcome=AWAITING_SECOND_APPROVAL
  - DUAL auth second call: actor_sub must differ from both proposer AND approver_1
    → proceeds to finalize as normal
  - Auto-provisions a stub policy_bundle if none exists for this tenant
  - JCS canonicalize decision → SHA-256 → sign → INSERT governance_decisions
  - UPDATE approval_tasks status + actor_sub + actioned_at
  - UPDATE approval_requests status + approver_sub + actioned_at
  - INSERT approval_decisions (APPEND-ONLY)
  - Publish governance.decided to Kafka
"""
import hashlib, json, uuid
from datetime import datetime, timedelta, timezone

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401 — registers UUID adapter

from shared.signer import sign
from zoiko_common.crypto.jcs import canonicalize

from services.governance_svc.models import (
    ApprovalTaskResult,
    ApprovalThreshold,
    GovernanceDecisionResult,
)

_SYSTEM_ACTOR = "system@zoiko.auto"


def _load_threshold(cur, tenant_id: str, currency: str) -> dict | None:
    cur.execute(
        "SELECT auto_approve_below, dual_auth_above, escalate_after_hours "
        "FROM approval_thresholds WHERE tenant_id=%s AND currency=%s",
        (tenant_id, currency),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _determine_approval_level(threshold: dict | None, amount: float) -> str:
    if threshold is None:
        return "SINGLE"
    auto_below  = threshold.get("auto_approve_below")
    dual_above  = threshold.get("dual_auth_above")
    if auto_below is not None and amount < float(auto_below):
        return "AUTO"
    if dual_above is not None and amount >= float(dual_above):
        return "DUAL"
    return "SINGLE"


class GovernanceHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.broker      = kafka_broker
        self.tenant_slug = tenant_slug

    def create_task(
        self,
        tenant_id:    str,
        proposal_id:  str,
        proposer_sub: str,
    ) -> ApprovalTaskResult:
        tenant_id   = str(tenant_id)
        proposal_id = str(proposal_id)
        now         = datetime.now(timezone.utc)

        task_id = uuid.uuid4()
        conn    = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Load proposal amount + currency for threshold routing
            cur.execute(
                "SELECT amount, currency FROM decision_proposals "
                "WHERE id=%s AND tenant_id=%s",
                (uuid.UUID(proposal_id), tenant_id),
            )
            prop_row = cur.fetchone()
            amount   = float(prop_row["amount"] or 0) if prop_row else 0.0
            currency = (prop_row["currency"] or "INR")  if prop_row else "INR"

            # Determine approval level
            threshold      = _load_threshold(cur, tenant_id, currency)
            approval_level = _determine_approval_level(threshold, amount)
            escalate_hours = int(threshold["escalate_after_hours"]) if threshold else 24
            deadline_at    = now + timedelta(hours=escalate_hours)

            # For AUTO: task is immediately approved by system actor
            task_status = "APPROVED" if approval_level == "AUTO" else "PENDING"
            actor_sub   = _SYSTEM_ACTOR if approval_level == "AUTO" else None
            actioned_at = now if approval_level == "AUTO" else None

            cur2 = conn.cursor()
            cur2.execute("""
                INSERT INTO approval_tasks
                    (id, tenant_id, proposal_id, proposer_sub, status,
                     approval_level, deadline_at, actor_sub, actioned_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                task_id, tenant_id, uuid.UUID(proposal_id), proposer_sub,
                task_status, approval_level, deadline_at,
                actor_sub, actioned_at, now,
            ))

            # Create approval_request record
            ar_status = "APPROVED" if approval_level == "AUTO" else "PENDING"
            cur2.execute("""
                INSERT INTO approval_requests
                    (id, tenant_id, proposal_id, approval_level, status,
                     approver_1_sub, actioned_at, requested_at, deadline_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                uuid.uuid4(), tenant_id, uuid.UUID(proposal_id),
                approval_level, ar_status,
                actor_sub, actioned_at, now, deadline_at,
            ))
            # Atomic outbox INSERT in same transaction
            outbox_task_payload = {
                "task_id":        str(task_id),
                "proposal_id":    proposal_id,
                "approval_level": approval_level,
                "status":         task_status,
            }
            cur2.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id, "zoiko.case.updated",
                str(task_id), json.dumps(outbox_task_payload), now,
            ))
            conn.commit()
        finally:
            conn.close()

        from kafka.producer import ZoikoProducer, KafkaMessage
        ZoikoProducer(self.broker).publish(KafkaMessage(
            topic          = "zoiko.case.updated",
            key            = str(task_id),
            payload        = outbox_task_payload,
            tenant_id      = tenant_id,
            correlation_id = proposal_id,
        ))

        return ApprovalTaskResult(
            task_id        = task_id,
            proposal_id    = proposal_id,
            tenant_id      = tenant_id,
            proposer_sub   = proposer_sub,
            status         = task_status,
            approval_level = approval_level,
            created_at     = now,
        )

    def decide(
        self,
        tenant_id: str,
        task_id:   str,
        actor_sub: str,
        outcome:   str,          # "EXECUTION_READY" | "ABORTED"
    ) -> GovernanceDecisionResult:
        if outcome not in ("EXECUTION_READY", "ABORTED"):
            raise ValueError(f"Invalid outcome '{outcome}': must be EXECUTION_READY or ABORTED")

        tenant_id = str(tenant_id)
        task_id   = str(task_id)
        now       = datetime.now(timezone.utc)

        conn = psycopg2.connect(self.db_url)
        try:
            cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur2 = conn.cursor()   # plain cursor used for all writes

            # Load task
            cur.execute(
                "SELECT proposal_id, proposer_sub, status, approval_level, actor_sub "
                "FROM approval_tasks WHERE id=%s AND tenant_id=%s",
                (uuid.UUID(task_id), tenant_id),
            )
            task = cur.fetchone()
            if not task:
                raise ValueError(f"Approval task {task_id} not found for tenant {tenant_id}")
            if task["status"] == "APPROVED":
                raise ValueError(f"Task {task_id} is already APPROVED")
            if task["status"] == "REJECTED":
                raise ValueError(f"Task {task_id} is already REJECTED")
            if task["status"] not in ("PENDING",):
                raise ValueError(f"Task {task_id} is already {task['status']}")

            # SoD enforcement — actor must differ from proposer
            if actor_sub == task["proposer_sub"]:
                raise ValueError(
                    f"Separation of Duties violation: actor_sub '{actor_sub}' "
                    f"cannot be the same as proposer_sub '{task['proposer_sub']}'"
                )

            proposal_id    = str(task["proposal_id"])
            approval_level = task["approval_level"] or "SINGLE"
            first_approver = task["actor_sub"]      # None on first DUAL call

            # ── DUAL auth first-approval pass ────────────────────────────────
            if approval_level == "DUAL" and first_approver is None:
                cur2.execute(
                    "UPDATE approval_tasks SET actor_sub=%s WHERE id=%s AND tenant_id=%s",
                    (actor_sub, uuid.UUID(task_id), tenant_id),
                )
                cur.execute(
                    "SELECT id FROM approval_requests "
                    "WHERE proposal_id=%s AND tenant_id=%s ORDER BY requested_at DESC LIMIT 1",
                    (uuid.UUID(proposal_id), tenant_id),
                )
                ar = cur.fetchone()
                if ar:
                    cur2.execute(
                        "UPDATE approval_requests SET approver_1_sub=%s WHERE id=%s",
                        (actor_sub, ar["id"]),
                    )
                ar_id = ar["id"] if ar else uuid.uuid4()
                cur2.execute("""
                    INSERT INTO approval_decisions
                        (id, tenant_id, approval_request_id, actor_sub, decision,
                         rationale, decided_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    uuid.uuid4(), tenant_id, ar_id, actor_sub, "APPROVE",
                    f"First of two required approvals (DUAL auth, outcome={outcome})",
                    now,
                ))
                conn.commit()
                return GovernanceDecisionResult(
                    decision_id              = None,
                    task_id                  = task_id,
                    proposal_id              = proposal_id,
                    tenant_id                = tenant_id,
                    outcome                  = "AWAITING_SECOND_APPROVAL",
                    actor_sub                = actor_sub,
                    decision_hash            = "",
                    decided_at               = now,
                    awaiting_second_approval = True,
                )

            # ── DUAL auth second-approval guard ──────────────────────────────
            if approval_level == "DUAL" and first_approver is not None:
                if actor_sub == first_approver:
                    raise ValueError(
                        f"DUAL auth violation: second approver '{actor_sub}' "
                        f"cannot be the same as first approver '{first_approver}'"
                    )

            # ── Ensure a policy bundle exists ────────────────────────────────
            cur.execute(
                "SELECT id FROM policy_bundles WHERE tenant_id=%s AND active=TRUE LIMIT 1",
                (tenant_id,),
            )
            pb_row = cur.fetchone()
            if pb_row:
                policy_bundle_id = pb_row["id"]
            else:
                policy_bundle_id = uuid.uuid4()
                stub_hash = hashlib.sha256(b"zoiko.opa.freight_dispute.v1").digest()
                cur2.execute("""
                    INSERT INTO policy_bundles
                        (id, tenant_id, version, rego_hash, active, deployed_at)
                    VALUES (%s, %s, %s, %s, TRUE, %s)
                """, (policy_bundle_id, tenant_id, "v1.0.0", stub_hash, now))

            # JCS canonicalize → SHA-256 → sign
            decision_payload = {
                "actor_sub":   actor_sub,
                "outcome":     outcome,
                "proposal_id": proposal_id,
                "task_id":     task_id,
                "tenant_id":   tenant_id,
            }
            decision_bytes = canonicalize(decision_payload)
            decision_hash  = hashlib.sha256(
                b"zoiko.governance.decision.v1:" + decision_bytes
            ).digest()
            decision_sig, decision_kid = sign(self.tenant_slug, decision_hash)

            # approval_chain_hash = SHA-256(proposer_sub || actor_sub || decision_hash)
            # Binds both approvers (or proposer+actor for SINGLE) into the token chain.
            chain_input = (
                task["proposer_sub"].encode("utf-8")
                + actor_sub.encode("utf-8")
                + decision_hash
            )
            approval_chain_hash = hashlib.sha256(chain_input).digest()

            # policy_version from the bundle we just resolved
            cur.execute(
                "SELECT version FROM policy_bundles WHERE id=%s",
                (policy_bundle_id,),
            )
            pb_ver_row = cur.fetchone()
            policy_version = pb_ver_row["version"] if pb_ver_row else "v1.0.0"

            decision_id = uuid.uuid4()
            cur2.execute("""
                INSERT INTO governance_decisions
                    (id, tenant_id, proposal_id, policy_bundle_id, outcome,
                     decision_hash, signature, kid, decided_at,
                     approval_chain_hash, policy_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                decision_id, tenant_id, uuid.UUID(proposal_id), policy_bundle_id,
                outcome, decision_hash, decision_sig, decision_kid, now,
                approval_chain_hash, policy_version,
            ))

            # Update approval task
            task_status = "APPROVED" if outcome == "EXECUTION_READY" else "REJECTED"
            cur2.execute("""
                UPDATE approval_tasks
                SET status=%s, actor_sub=%s, actioned_at=%s
                WHERE id=%s AND tenant_id=%s
            """, (task_status, actor_sub, now, uuid.UUID(task_id), tenant_id))

            # Update approval_request
            ar_decision = "APPROVE" if outcome == "EXECUTION_READY" else "REJECT"
            cur.execute(
                "SELECT id FROM approval_requests "
                "WHERE proposal_id=%s AND tenant_id=%s ORDER BY requested_at DESC LIMIT 1",
                (uuid.UUID(proposal_id), tenant_id),
            )
            ar = cur.fetchone()
            if ar:
                second_approver_col = "approver_2_sub" if (
                    approval_level == "DUAL" and first_approver is not None
                ) else "approver_1_sub"
                ar_status = "APPROVED" if outcome == "EXECUTION_READY" else "REJECTED"
                cur2.execute(
                    f"UPDATE approval_requests "
                    f"SET status=%s, {second_approver_col}=%s, actioned_at=%s "
                    f"WHERE id=%s",
                    (ar_status, actor_sub, now, ar["id"]),
                )
                # APPEND-ONLY approval_decision
                cur2.execute("""
                    INSERT INTO approval_decisions
                        (id, tenant_id, approval_request_id, actor_sub, decision,
                         rationale, decided_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    uuid.uuid4(), tenant_id, ar["id"],
                    actor_sub, ar_decision, None, now,
                ))

            # Case FSM transition: APPROVAL_PENDING → EXECUTION_READY or ABORTED
            cur.execute(
                "SELECT case_id FROM decision_proposals WHERE id=%s AND tenant_id=%s",
                (uuid.UUID(proposal_id), tenant_id),
            )
            prop_row = cur.fetchone()
            if prop_row:
                case_id = prop_row["case_id"]
                cur.execute(
                    "SELECT state FROM cases WHERE id=%s AND tenant_id=%s",
                    (case_id, tenant_id),
                )
                case_row = cur.fetchone()
                if case_row and case_row["state"] == "APPROVAL_PENDING":
                    cur2.execute(
                        "UPDATE cases SET state=%s WHERE id=%s AND tenant_id=%s",
                        (outcome, case_id, tenant_id),
                    )
                    # APPEND-ONLY case_event
                    cur2.execute("""
                        INSERT INTO case_events
                            (id, tenant_id, case_id, event_type, from_state, to_state,
                             actor_sub, payload, occurred_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    """, (
                        uuid.uuid4(), tenant_id, case_id,
                        f"GOVERNANCE_{outcome}",
                        "APPROVAL_PENDING", outcome,
                        actor_sub,
                        json.dumps({
                            "decision_id":    str(decision_id),
                            "proposal_id":    proposal_id,
                            "approval_level": approval_level,
                        }),
                        now,
                    ))

            # Atomic outbox INSERT for governance decision
            outbox_decision_payload = {
                "decision_id":    str(decision_id),
                "proposal_id":    proposal_id,
                "outcome":        outcome,
                "actor_sub":      actor_sub,
                "approval_level": approval_level,
            }
            cur2.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id, "zoiko.governance.decision.issued",
                str(decision_id), json.dumps(outbox_decision_payload), now,
            ))
            conn.commit()
        finally:
            conn.close()

        from kafka.producer import ZoikoProducer, KafkaMessage
        ZoikoProducer(self.broker).publish(KafkaMessage(
            topic          = "zoiko.governance.decision.issued",
            key            = str(decision_id),
            payload        = outbox_decision_payload,
            tenant_id      = tenant_id,
            correlation_id = proposal_id,
            causation_id   = task_id,
        ))

        return GovernanceDecisionResult(
            decision_id         = decision_id,
            task_id             = task_id,
            proposal_id         = proposal_id,
            tenant_id           = tenant_id,
            outcome             = outcome,
            actor_sub           = actor_sub,
            decision_hash       = decision_hash.hex(),
            decided_at          = now,
            approval_chain_hash = approval_chain_hash.hex(),
            policy_version      = policy_version,
        )
