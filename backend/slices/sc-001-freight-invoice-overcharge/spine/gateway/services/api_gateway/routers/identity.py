"""Identity & Tenant extension routes: business units, approval groups, threshold profiles."""
from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from services.api_gateway.auth import get_claims
from shared.db import q, q1

router = APIRouter(tags=["identity"])


# ── Business Units ─────────────────────────────────────────────────────────────

class BusinessUnitIn(BaseModel):
    name:      str
    code:      str = ""
    parent_id: Optional[str] = None

class BusinessUnitOut(BaseModel):
    id: str; tenant_id: str; name: str; code: str
    parent_id: Optional[str]; created_at: str

@router.post("/business-units", response_model=BusinessUnitOut, status_code=201)
def create_business_unit(body: BusinessUnitIn, claims=Depends(get_claims)):
    row = q1("""
        INSERT INTO business_units (id, tenant_id, name, code, parent_id)
        VALUES (gen_random_uuid(), %s::uuid, %s, %s, %s::uuid)
        RETURNING id, tenant_id, name, code, parent_id, created_at
    """, (claims.tenant_id, body.name, body.code,
          body.parent_id if body.parent_id else None))
    return {**row, "id": str(row["id"]), "tenant_id": str(row["tenant_id"]),
            "parent_id": str(row["parent_id"]) if row["parent_id"] else None,
            "created_at": row["created_at"].isoformat()}

@router.get("/business-units", response_model=List[BusinessUnitOut])
def list_business_units(claims=Depends(get_claims)):
    rows = q("SELECT id, tenant_id, name, code, parent_id, created_at FROM business_units WHERE tenant_id=%s::uuid ORDER BY name", (claims.tenant_id,))
    return [{**r, "id": str(r["id"]), "tenant_id": str(r["tenant_id"]),
             "parent_id": str(r["parent_id"]) if r["parent_id"] else None,
             "created_at": r["created_at"].isoformat()} for r in rows]


# ── Approval Groups ────────────────────────────────────────────────────────────

class ApprovalGroupIn(BaseModel):
    name:          str
    description:   str = ""
    min_approvers: int = 1

class ApprovalGroupOut(BaseModel):
    id: str; tenant_id: str; name: str; description: str
    min_approvers: int; created_at: str

class AddMemberIn(BaseModel):
    user_id: str

@router.post("/approval-groups", response_model=ApprovalGroupOut, status_code=201)
def create_approval_group(body: ApprovalGroupIn, claims=Depends(get_claims)):
    row = q1("""
        INSERT INTO approval_groups (id, tenant_id, name, description, min_approvers)
        VALUES (gen_random_uuid(), %s::uuid, %s, %s, %s)
        RETURNING id, tenant_id, name, description, min_approvers, created_at
    """, (claims.tenant_id, body.name, body.description, body.min_approvers))
    return {**row, "id": str(row["id"]), "tenant_id": str(row["tenant_id"]),
            "created_at": row["created_at"].isoformat()}

@router.get("/approval-groups", response_model=List[ApprovalGroupOut])
def list_approval_groups(claims=Depends(get_claims)):
    rows = q("SELECT id, tenant_id, name, description, min_approvers, created_at FROM approval_groups WHERE tenant_id=%s::uuid ORDER BY name", (claims.tenant_id,))
    return [{**r, "id": str(r["id"]), "tenant_id": str(r["tenant_id"]),
             "created_at": r["created_at"].isoformat()} for r in rows]

@router.get("/approval-groups/{group_id}", response_model=ApprovalGroupOut)
def get_approval_group(group_id: str, claims=Depends(get_claims)):
    row = q1("SELECT id, tenant_id, name, description, min_approvers, created_at FROM approval_groups WHERE id=%s::uuid AND tenant_id=%s::uuid", (group_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Approval group not found")
    return {**row, "id": str(row["id"]), "tenant_id": str(row["tenant_id"]),
            "created_at": row["created_at"].isoformat()}

@router.post("/approval-groups/{group_id}/members", status_code=201)
def add_group_member(group_id: str, body: AddMemberIn, claims=Depends(get_claims)):
    group = q1("SELECT id FROM approval_groups WHERE id=%s::uuid AND tenant_id=%s::uuid", (group_id, claims.tenant_id))
    if not group:
        raise HTTPException(status_code=404, detail="Approval group not found")
    q1("""
        INSERT INTO approval_group_members (id, approval_group_id, user_id)
        VALUES (gen_random_uuid(), %s::uuid, %s::uuid)
        ON CONFLICT (approval_group_id, user_id) DO NOTHING
        RETURNING id
    """, (group_id, body.user_id))
    return {"message": "Member added"}

@router.delete("/approval-groups/{group_id}/members/{user_id}", status_code=200)
def remove_group_member(group_id: str, user_id: str, claims=Depends(get_claims)):
    q1("DELETE FROM approval_group_members WHERE approval_group_id=%s::uuid AND user_id=%s::uuid", (group_id, user_id))
    return {"message": "Member removed"}


# ── Threshold Profiles ─────────────────────────────────────────────────────────

class ThresholdProfileIn(BaseModel):
    name:                  str
    currency:              str = "USD"
    auto_approve_below:    float = 0.0
    require_approval_above: float = 1000.0
    escalate_above:        float = 10000.0
    approval_group_id:     Optional[str] = None

class ThresholdProfileOut(BaseModel):
    id: str; tenant_id: str; name: str; currency: str
    auto_approve_below: float; require_approval_above: float
    escalate_above: float; approval_group_id: Optional[str]; created_at: str

@router.post("/threshold-profiles", response_model=ThresholdProfileOut, status_code=201)
def create_threshold_profile(body: ThresholdProfileIn, claims=Depends(get_claims)):
    row = q1("""
        INSERT INTO threshold_profiles
            (id, tenant_id, name, currency, auto_approve_below, require_approval_above, escalate_above, approval_group_id)
        VALUES (gen_random_uuid(), %s::uuid, %s, %s, %s, %s, %s, %s::uuid)
        RETURNING id, tenant_id, name, currency, auto_approve_below, require_approval_above, escalate_above, approval_group_id, created_at
    """, (claims.tenant_id, body.name, body.currency,
          body.auto_approve_below, body.require_approval_above, body.escalate_above,
          body.approval_group_id if body.approval_group_id else None))
    return {**row, "id": str(row["id"]), "tenant_id": str(row["tenant_id"]),
            "approval_group_id": str(row["approval_group_id"]) if row["approval_group_id"] else None,
            "created_at": row["created_at"].isoformat(),
            "auto_approve_below": float(row["auto_approve_below"]),
            "require_approval_above": float(row["require_approval_above"]),
            "escalate_above": float(row["escalate_above"])}

@router.get("/threshold-profiles", response_model=List[ThresholdProfileOut])
def list_threshold_profiles(claims=Depends(get_claims)):
    rows = q("SELECT id, tenant_id, name, currency, auto_approve_below, require_approval_above, escalate_above, approval_group_id, created_at FROM threshold_profiles WHERE tenant_id=%s::uuid ORDER BY name", (claims.tenant_id,))
    return [{**r, "id": str(r["id"]), "tenant_id": str(r["tenant_id"]),
             "approval_group_id": str(r["approval_group_id"]) if r["approval_group_id"] else None,
             "created_at": r["created_at"].isoformat(),
             "auto_approve_below": float(r["auto_approve_below"]),
             "require_approval_above": float(r["require_approval_above"]),
             "escalate_above": float(r["escalate_above"])} for r in rows]
