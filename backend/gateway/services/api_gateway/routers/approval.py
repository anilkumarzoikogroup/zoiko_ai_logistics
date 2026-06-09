"""Approval workflow endpoints: approve, reject, get approvals, tasks."""
from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional

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
    row = q1("SELECT id, status FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid", (case_id, tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return row


@router.post("/cases/{case_id}/approve", response_model=ApprovalOut, status_code=201)
def approve_case(case_id: str, body: ApproveIn, claims=Depends(get_claims)):
    case = _get_case(case_id, claims.tenant_id)
    if case["status"] not in ("APPROVAL_PENDING", "FINDING_GENERATED"):
        raise HTTPException(status_code=422, detail=f"Case status '{case['status']}' cannot be approved")

    now = datetime.now(timezone.utc)

    # Record approval decision
    row = q1("""
        INSERT INTO approval_decisions (id, tenant_id, case_id, decision, decided_by, notes, decided_at)
        VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'APPROVED', %s, %s, %s)
        RETURNING id, case_id, decision, decided_by, notes, decided_at
    """, (claims.tenant_id, case_id, claims.sub, body.notes, now))

    # Advance case state
    q1("UPDATE cases SET status='EXECUTION_READY', updated_at=%s WHERE id=%s::uuid", (now, case_id))

    # Write timeline entry
    q1("""
        INSERT INTO case_timeline_entries (id, tenant_id, case_id, event_type, actor, summary)
        VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'case.approved', %s, %s)
    """, (claims.tenant_id, case_id, claims.sub, body.notes or "Approved"))

    return {"id": str(row["id"]), "case_id": case_id, "decision": "APPROVED",
            "actor": claims.sub, "notes": body.notes,
            "decided_at": row["decided_at"].isoformat()}


@router.post("/cases/{case_id}/reject", response_model=ApprovalOut, status_code=201)
def reject_case(case_id: str, body: RejectIn, claims=Depends(get_claims)):
    case = _get_case(case_id, claims.tenant_id)
    if case["status"] not in ("APPROVAL_PENDING", "FINDING_GENERATED", "EXECUTION_READY"):
        raise HTTPException(status_code=422, detail=f"Case status '{case['status']}' cannot be rejected")

    now = datetime.now(timezone.utc)

    row = q1("""
        INSERT INTO approval_decisions (id, tenant_id, case_id, decision, decided_by, notes, decided_at)
        VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'REJECTED', %s, %s, %s)
        RETURNING id, case_id, decision, decided_by, notes, decided_at
    """, (claims.tenant_id, case_id, claims.sub, body.reason, now))

    q1("UPDATE cases SET status='ABORTED', updated_at=%s WHERE id=%s::uuid", (now, case_id))

    q1("""
        INSERT INTO case_timeline_entries (id, tenant_id, case_id, event_type, actor, summary)
        VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'case.rejected', %s, %s)
    """, (claims.tenant_id, case_id, claims.sub, body.reason))

    return {"id": str(row["id"]), "case_id": case_id, "decision": "REJECTED",
            "actor": claims.sub, "notes": body.reason,
            "decided_at": row["decided_at"].isoformat()}


@router.get("/approvals/{approval_id}", response_model=ApprovalOut)
def get_approval(approval_id: str, claims=Depends(get_claims)):
    row = q1("""
        SELECT id, case_id, decision, decided_by, notes, decided_at
        FROM approval_decisions WHERE id=%s::uuid AND tenant_id=%s::uuid
    """, (approval_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Approval not found")
    return {"id": str(row["id"]), "case_id": str(row["case_id"]),
            "decision": row["decision"], "actor": row["decided_by"],
            "notes": row["notes"] or "", "decided_at": row["decided_at"].isoformat()}


@router.get("/cases/{case_id}/approvals")
def list_case_approvals(case_id: str, claims=Depends(get_claims)):
    _get_case(case_id, claims.tenant_id)
    rows = q("""
        SELECT id, case_id, decision, decided_by, notes, decided_at
        FROM approval_decisions WHERE case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY decided_at DESC
    """, (case_id, claims.tenant_id))
    return [{"id": str(r["id"]), "case_id": str(r["case_id"]),
             "decision": r["decision"], "actor": r["decided_by"],
             "notes": r["notes"] or "", "decided_at": r["decided_at"].isoformat()} for r in rows]


# ── Case Tasks ─────────────────────────────────────────────────────────────────

@router.get("/cases/{case_id}/tasks")
def list_case_tasks(case_id: str, claims=Depends(get_claims)):
    _get_case(case_id, claims.tenant_id)
    rows = q("""
        SELECT id, case_id, task_type, assigned_to, status, due_at, completed_at, notes, created_at
        FROM tasks WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY created_at
    """, (case_id, claims.tenant_id))
    return [{"id": str(r["id"]), "case_id": str(r["case_id"]),
             "task_type": r["task_type"], "assigned_to": r["assigned_to"],
             "status": r["status"], "notes": r["notes"],
             "due_at": r["due_at"].isoformat() if r.get("due_at") else None,
             "completed_at": r["completed_at"].isoformat() if r.get("completed_at") else None,
             "created_at": r["created_at"].isoformat()} for r in rows]
