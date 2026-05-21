"""
Governance Service — SoD-enforced approval workflow.

create_task():
  - Creates an approval_task in PENDING state for a decision_proposal
  - proposer_sub is recorded; actor_sub is NULL until actioned

decide():
  - SoD check: actor_sub MUST differ from proposer_sub (OPA rule §3.2)
  - Auto-provisions a stub policy_bundle if none exists for this tenant
  - JCS canonicalize decision → SHA-256 → sign → INSERT governance_decisions
  - UPDATE approval_tasks status + actor_sub + actioned_at
  - Publish governance.decided to Kafka
"""
import hashlib, json, uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401 — registers UUID adapter

from shared.signer import sign
from zoiko_common.crypto.jcs import canonicalize

from services.governance_svc.models import ApprovalTaskResult, GovernanceDecisionResult


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
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO approval_tasks
                    (id, tenant_id, proposal_id, proposer_sub, status, created_at)
                VALUES (%s, %s, %s, %s, 'PENDING', %s)
            """, (task_id, tenant_id, uuid.UUID(proposal_id), proposer_sub, now))
            conn.commit()
        finally:
            conn.close()

        from kafka.producer import ZoikoProducer, KafkaMessage
        ZoikoProducer(self.broker).publish(KafkaMessage(
            topic     = "zoiko.case.updated",
            key       = str(task_id),
            payload   = {"task_id": str(task_id), "proposal_id": proposal_id},
            tenant_id = tenant_id,
        ))

        return ApprovalTaskResult(
            task_id      = task_id,
            proposal_id  = proposal_id,
            tenant_id    = tenant_id,
            proposer_sub = proposer_sub,
            status       = "PENDING",
            created_at   = now,
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
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Load the task to get proposer_sub and proposal_id
            cur.execute(
                "SELECT proposal_id, proposer_sub, status FROM approval_tasks "
                "WHERE id=%s AND tenant_id=%s",
                (uuid.UUID(task_id), tenant_id),
            )
            task = cur.fetchone()
            if not task:
                raise ValueError(f"Approval task {task_id} not found for tenant {tenant_id}")
            if task["status"] != "PENDING":
                raise ValueError(f"Task {task_id} is already {task['status']}")

            # SoD enforcement — actor must differ from proposer
            if actor_sub == task["proposer_sub"]:
                raise ValueError(
                    f"Separation of Duties violation: actor_sub '{actor_sub}' "
                    f"cannot be the same as proposer_sub '{task['proposer_sub']}'"
                )

            proposal_id = str(task["proposal_id"])

            # Ensure a policy bundle exists (dev stub auto-provision)
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
                cur.execute("""
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
            decision_hash  = hashlib.sha256(b"zoiko.governance.decision.v1:" + decision_bytes).digest()
            decision_sig, decision_kid = sign(self.tenant_slug, decision_hash)

            decision_id = uuid.uuid4()
            cur.execute("""
                INSERT INTO governance_decisions
                    (id, tenant_id, proposal_id, policy_bundle_id, outcome,
                     decision_hash, signature, kid, decided_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                decision_id, tenant_id, uuid.UUID(proposal_id), policy_bundle_id,
                outcome, decision_hash, decision_sig, decision_kid, now,
            ))

            # Update the approval task
            cur.execute("""
                UPDATE approval_tasks
                SET status=%s, actor_sub=%s, actioned_at=%s
                WHERE id=%s AND tenant_id=%s
            """, (outcome, actor_sub, now, uuid.UUID(task_id), tenant_id))

            # Case FSM transition: APPROVAL_PENDING → EXECUTION_READY or ABORTED
            # Find the case via proposal → finding → case_id
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
                    cur.execute(
                        "UPDATE cases SET state=%s WHERE id=%s AND tenant_id=%s",
                        (outcome, case_id, tenant_id),
                    )
                    # APPEND-ONLY case_event
                    cur.execute("""
                        INSERT INTO case_events
                            (id, tenant_id, case_id, event_type, from_state, to_state,
                             actor_sub, payload, occurred_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    """, (
                        uuid.uuid4(), tenant_id, case_id,
                        f"GOVERNANCE_{outcome}",
                        "APPROVAL_PENDING", outcome,
                        actor_sub,
                        json.dumps({"decision_id": str(decision_id), "proposal_id": proposal_id}),
                        now,
                    ))

            conn.commit()
        finally:
            conn.close()

        from kafka.producer import ZoikoProducer, KafkaMessage
        ZoikoProducer(self.broker).publish(KafkaMessage(
            topic     = "zoiko.governance.decision.issued",
            key       = str(decision_id),
            payload   = {
                "decision_id": str(decision_id),
                "proposal_id": proposal_id,
                "outcome":     outcome,
                "actor_sub":   actor_sub,
            },
            tenant_id = tenant_id,
        ))

        return GovernanceDecisionResult(
            decision_id   = decision_id,
            task_id       = task_id,
            proposal_id   = proposal_id,
            tenant_id     = tenant_id,
            outcome       = outcome,
            actor_sub     = actor_sub,
            decision_hash = decision_hash.hex(),
            decided_at    = now,
        )
