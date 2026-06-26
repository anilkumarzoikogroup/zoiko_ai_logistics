"""
SC-003 Governance Service — SoD-enforced proposal and approval for SLA credits.

Policy: sla-penalty-policy@2026.05.01
Proposed action: ISSUE_SLA_CREDIT

SoD rule: proposer_sub ≠ approver_sub (same actor cannot both propose and approve).
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401
from zoiko_common.crypto.jcs import canonicalize
from shared.signer import sign

_POLICY_NAME    = "sla-penalty-policy"
_POLICY_VERSION = "2026.05.01"
POLICY_ID       = f"{_POLICY_NAME}@{_POLICY_VERSION}"


class GovernanceHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.broker      = kafka_broker
        self.tenant_slug = tenant_slug

    def propose(
        self,
        tenant_id: str,
        case_id: str,
        finding_id: str,
        amount: float,
        currency: str,
        actor_sub: str,
    ) -> dict:
        """Analyst proposes an SLA credit recovery. Returns the task record."""
        case_uuid   = uuid.UUID(case_id)
        finding_uuid = uuid.UUID(finding_id)
        now         = datetime.now(timezone.utc)

        proposal_dict = {
            "amount":          str(amount),
            "case_id":         case_id,
            "currency":        currency,
            "finding_id":      finding_id,
            "policy_id":       POLICY_ID,
            "proposed_action": "ISSUE_SLA_CREDIT",
            "proposer_sub":    actor_sub,
            "tenant_id":       tenant_id,
        }
        proposal_bytes = canonicalize(proposal_dict)
        proposal_hash  = hashlib.sha256(b"zoiko.proposal.v1:" + proposal_bytes).digest()
        p_sig, p_kid   = sign(self.tenant_slug, proposal_hash)

        task_id = uuid.uuid4()

        psycopg2.extras.register_uuid()
        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Upsert proposal
            cur.execute("""
                INSERT INTO decision_proposals
                    (id, tenant_id, case_id, finding_id, proposed_action, amount, currency,
                     proposer_sub, proposal_hash, signature, kid, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                uuid.uuid4(), tenant_id, case_uuid, finding_uuid,
                "ISSUE_SLA_CREDIT", amount, currency,
                actor_sub, proposal_hash, p_sig, p_kid, now,
            ))

            # Governance task
            cur.execute("""
                INSERT INTO governance_tasks
                    (id, tenant_id, case_id, task_type, status, proposer_sub,
                     proposal_payload, policy_version, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                RETURNING id, status, proposer_sub
            """, (
                task_id, tenant_id, case_uuid,
                "APPROVE_SLA_CREDIT", "PENDING_APPROVAL", actor_sub,
                json.dumps({
                    "amount": amount, "currency": currency,
                    "policy_id": POLICY_ID, "finding_id": finding_id,
                }),
                POLICY_ID, now,
            ))
            row = cur.fetchone()

            # Advance case to APPROVAL_PENDING
            cur.execute(
                "UPDATE cases SET state='APPROVAL_PENDING' WHERE id=%s AND tenant_id=%s AND state='FINDING_GENERATED'",
                (case_uuid, tenant_id),
            )
            cur.execute("""
                INSERT INTO case_events
                    (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
                VALUES (%s, %s, %s, 'PROPOSAL_CREATED', 'FINDING_GENERATED', 'APPROVAL_PENDING', %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id, case_uuid, actor_sub,
                json.dumps({"amount": amount, "currency": currency, "policy_id": POLICY_ID}),
                now,
            ))

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        task_row = row if isinstance(row, dict) else {"id": task_id, "status": "PENDING_APPROVAL", "proposer_sub": actor_sub}
        return {
            "task_id":      str(task_row.get("id", task_id)),
            "status":       task_row.get("status", "PENDING_APPROVAL"),
            "proposer_sub": task_row.get("proposer_sub", actor_sub),
            "policy_id":    POLICY_ID,
        }

    def decide(
        self,
        tenant_id: str,
        case_id: str,
        task_id: str,
        actor_sub: str,
        decision: str,       # "APPROVE" | "REJECT"
        note: str = "",
    ) -> dict:
        """Manager approves or rejects the SLA credit proposal. SoD enforced."""
        case_uuid = uuid.UUID(case_id)
        task_uuid = uuid.UUID(task_id)
        now       = datetime.now(timezone.utc)

        psycopg2.extras.register_uuid()
        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute(
                "SELECT proposer_sub, status FROM governance_tasks "
                "WHERE id=%s AND tenant_id=%s",
                (task_uuid, tenant_id),
            )
            task = cur.fetchone()
            if not task:
                raise ValueError(f"Governance task {task_id} not found")

            proposer_sub = task["proposer_sub"] if isinstance(task, dict) else task[0]
            current_status = task["status"]    if isinstance(task, dict) else task[1]

            if current_status != "PENDING_APPROVAL":
                raise ValueError(f"Task already {current_status}")

            # SoD: approver must not be the same person who proposed
            if actor_sub == proposer_sub:
                raise ValueError(
                    f"Separation of Duties violation: actor_sub '{actor_sub}' "
                    f"cannot be the same as proposer_sub '{proposer_sub}'"
                )

            decision_dict = {
                "case_id":    case_id,
                "decision":   decision,
                "actor_sub":  actor_sub,
                "note":       note,
                "policy_id":  POLICY_ID,
                "task_id":    task_id,
                "tenant_id":  tenant_id,
            }
            decision_bytes = canonicalize(decision_dict)
            decision_hash  = hashlib.sha256(b"zoiko.governance.decision.v1:" + decision_bytes).digest()
            d_sig, d_kid   = sign(self.tenant_slug, decision_hash)

            new_task_status = "APPROVED" if decision == "APPROVE" else "REJECTED"
            new_case_state  = "EXECUTION_READY" if decision == "APPROVE" else "ABORTED"

            cur.execute(
                "UPDATE governance_tasks SET status=%s, actor_sub=%s WHERE id=%s AND tenant_id=%s",
                (new_task_status, actor_sub, task_uuid, tenant_id),
            )

            decision_id = uuid.uuid4()
            cur.execute("""
                INSERT INTO governance_decisions
                    (id, tenant_id, case_id, task_id, decision, actor_sub,
                     decision_hash, signature, kid, policy_version, note, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                decision_id, tenant_id, case_uuid, task_uuid,
                decision, actor_sub, decision_hash, d_sig, d_kid,
                POLICY_ID, note, now,
            ))

            cur.execute(
                "UPDATE cases SET state=%s WHERE id=%s AND tenant_id=%s",
                (new_case_state, case_uuid, tenant_id),
            )
            cur.execute("""
                INSERT INTO case_events
                    (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
                VALUES (%s, %s, %s, 'DECISION_MADE', 'APPROVAL_PENDING', %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id, case_uuid, new_case_state, actor_sub,
                json.dumps({"decision": decision, "note": note, "policy_id": POLICY_ID}),
                now,
            ))

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return {
            "decision_id":   str(decision_id),
            "decision":      decision,
            "new_case_state": new_case_state,
            "policy_id":     POLICY_ID,
        }
