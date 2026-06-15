"""Approval workflow endpoints: approve, reject, get approvals, tasks."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.api_gateway.auth import get_claims
from shared.db import q, q1

router = APIRouter(tags=["approval"])


class ApproveIn(BaseModel):
    notes: str = ""

class RejectIn(BaseModel):
    reason: str

class ApprovalOut(BaseModel):
    id: str; case_id: str; decision: str; actor: str
    notes: str; decided_at: str


def _get_case(case_id: str, tenant_id: str):
    row = q1("SELECT id, state FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid",
             (case_id, tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return row


def _try_write_approval_decision(tenant_id: str, case_id: str, actor_sub: str,
                                  decision: str, rationale: str, now: datetime) -> Optional[str]:
    """Write to approval_decisions only if a decision_proposals row exists for this case.
    Returns the new approval_decisions.id or None if no proposal found."""
    try:
        proposal = q1("""
            SELECT id FROM decision_proposals
            WHERE case_id=%s::uuid AND tenant_id=%s::uuid
            ORDER BY created_at DESC LIMIT 1
        """, (case_id, tenant_id))
        if not proposal:
            return None

        deadline = now + timedelta(hours=24)
        req = q1("""
            INSERT INTO approval_requests
                (id, tenant_id, proposal_id, approval_level, status,
                 approver_1_sub, requested_at, deadline_at)
            VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'SINGLE', 'PENDING', %s, %s, %s)
            RETURNING id
        """, (tenant_id, str(proposal["id"]), actor_sub, now, deadline))
        if not req:
            return None

        dec = q1("""
            INSERT INTO approval_decisions
                (id, tenant_id, approval_request_id, actor_sub, decision, rationale, decided_at)
            VALUES (gen_random_uuid(), %s::uuid, %s::uuid, %s, %s, %s, %s)
            RETURNING id
        """, (tenant_id, str(req["id"]), actor_sub, decision, rationale, now))
        return str(dec["id"]) if dec else None
    except Exception:
        return None


@router.post("/cases/{case_id}/approve", response_model=ApprovalOut, status_code=201)
def approve_case(case_id: str, body: ApproveIn, claims=Depends(get_claims)):
    case = _get_case(case_id, claims.tenant_id)
    if case["state"] not in ("APPROVAL_PENDING", "FINDING_GENERATED"):
        raise HTTPException(status_code=422,
                            detail=f"Case status '{case['state']}' cannot be approved")

    now = datetime.now(timezone.utc)

    approval_id = _try_write_approval_decision(
        claims.tenant_id, case_id, claims.sub, "APPROVE", body.notes or "Approved", now
    )

    q1("UPDATE cases SET state='EXECUTION_READY' WHERE id=%s::uuid AND tenant_id=%s::uuid",
       (case_id, claims.tenant_id))

    event = q1("""
        INSERT INTO case_events
            (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
        VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'case.approved',
                %s, 'EXECUTION_READY', %s, %s::jsonb, %s)
        RETURNING id, occurred_at
    """, (claims.tenant_id, case_id, case["state"], claims.sub,
          json.dumps({"notes": body.notes}), now))

    return {"id": approval_id or str(event["id"]), "case_id": case_id, "decision": "APPROVED",
            "actor": claims.sub, "notes": body.notes,
            "decided_at": event["occurred_at"].isoformat()}


@router.post("/cases/{case_id}/reject", response_model=ApprovalOut, status_code=201)
def reject_case(case_id: str, body: RejectIn, claims=Depends(get_claims)):
    case = _get_case(case_id, claims.tenant_id)
    if case["state"] not in ("APPROVAL_PENDING", "FINDING_GENERATED", "EXECUTION_READY"):
        raise HTTPException(status_code=422,
                            detail=f"Case status '{case['state']}' cannot be rejected")

    now = datetime.now(timezone.utc)

    approval_id = _try_write_approval_decision(
        claims.tenant_id, case_id, claims.sub, "REJECT", body.reason, now
    )

    q1("UPDATE cases SET state='ABORTED' WHERE id=%s::uuid AND tenant_id=%s::uuid",
       (case_id, claims.tenant_id))

    event = q1("""
        INSERT INTO case_events
            (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
        VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'case.rejected',
                %s, 'ABORTED', %s, %s::jsonb, %s)
        RETURNING id, occurred_at
    """, (claims.tenant_id, case_id, case["state"], claims.sub,
          json.dumps({"reason": body.reason}), now))

    return {"id": approval_id or str(event["id"]), "case_id": case_id, "decision": "REJECTED",
            "actor": claims.sub, "notes": body.reason,
            "decided_at": event["occurred_at"].isoformat()}


@router.get("/approvals/{approval_id}", response_model=ApprovalOut)
def get_approval(approval_id: str, claims=Depends(get_claims)):
    # Try approval_decisions (joined through approval_requests → decision_proposals for case_id)
    row = q1("""
        SELECT ad.id, dp.case_id, ad.decision, ad.actor_sub, ad.rationale, ad.decided_at
        FROM approval_decisions ad
        JOIN approval_requests ar ON ar.id = ad.approval_request_id
        JOIN decision_proposals dp ON dp.id = ar.proposal_id
        WHERE ad.id=%s::uuid AND ad.tenant_id=%s::uuid
    """, (approval_id, claims.tenant_id))
    if row:
        label = "APPROVED" if row["decision"] == "APPROVE" else row["decision"]
        return {"id": str(row["id"]), "case_id": str(row["case_id"]),
                "decision": label, "actor": row["actor_sub"],
                "notes": row["rationale"] or "",
                "decided_at": row["decided_at"].isoformat()}

    # Fall back: look in case_events (written by approve/reject endpoints)
    event = q1("""
        SELECT id, case_id, actor_sub, event_type, payload, occurred_at
        FROM case_events WHERE id=%s::uuid AND tenant_id=%s::uuid
          AND event_type IN ('case.approved', 'case.rejected')
    """, (approval_id, claims.tenant_id))
    if not event:
        raise HTTPException(status_code=404, detail="Approval not found")
    payload = event.get("payload") or {}
    return {"id": str(event["id"]), "case_id": str(event["case_id"]),
            "decision": "APPROVED" if event["event_type"] == "case.approved" else "REJECTED",
            "actor": event["actor_sub"],
            "notes": payload.get("notes", "") or payload.get("reason", ""),
            "decided_at": event["occurred_at"].isoformat()}


@router.get("/cases/{case_id}/approvals")
def list_case_approvals(case_id: str, claims=Depends(get_claims)):
    _get_case(case_id, claims.tenant_id)
    rows = q("""
        SELECT id, case_id, actor_sub, event_type, payload, occurred_at
        FROM case_events
        WHERE case_id=%s::uuid AND tenant_id=%s::uuid
          AND event_type IN ('case.approved', 'case.rejected')
        ORDER BY occurred_at DESC
    """, (case_id, claims.tenant_id))
    result = []
    for r in rows:
        payload = r.get("payload") or {}
        result.append({
            "id": str(r["id"]), "case_id": str(r["case_id"]),
            "decision": "APPROVED" if r["event_type"] == "case.approved" else "REJECTED",
            "actor": r["actor_sub"],
            "notes": payload.get("notes", "") or payload.get("reason", ""),
            "decided_at": r["occurred_at"].isoformat(),
        })
    return result


# ── Case Tasks (proxied from approval_tasks) ───────────────────────────────────

@router.get("/cases/{case_id}/tasks")
def list_case_tasks(case_id: str, claims=Depends(get_claims)):
    _get_case(case_id, claims.tenant_id)
    rows = q("""
        SELECT at.id, at.proposer_sub, at.actor_sub, at.status, at.actioned_at, at.created_at
        FROM approval_tasks at
        WHERE at.tenant_id=%s::uuid
          AND at.proposal_id IN (
              SELECT id FROM decision_proposals WHERE case_id=%s::uuid
          )
        ORDER BY at.created_at
    """, (claims.tenant_id, case_id))
    return [{"id": str(r["id"]), "case_id": case_id,
             "task_type": "APPROVAL",
             "assigned_to": r["actor_sub"] or r["proposer_sub"],
             "status": r["status"],
             "notes": None,
             "due_at": None,
             "completed_at": r["actioned_at"].isoformat() if r.get("actioned_at") else None,
             "created_at": r["created_at"].isoformat()} for r in rows]
