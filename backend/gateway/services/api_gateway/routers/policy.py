"""Policy & governance endpoints: policy check, decisions, audit chain, overrides."""
from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from services.api_gateway.auth import get_claims
from shared.db import q, q1

router = APIRouter(tags=["policy"])


# ── Policy Evaluation ──────────────────────────────────────────────────────────

class PolicyCheckIn(BaseModel):
    case_id:    Optional[str] = None
    action:     str
    resource:   str
    context:    Dict[str, Any] = {}

@router.post("/policy/check")
def policy_check(body: PolicyCheckIn, claims=Depends(get_claims)):
    """Evaluate a governance policy decision for an action + resource pair."""
    # Delegate to OPA MockClient (same pattern as auth middleware)
    from phase1.middleware.opa.client import MockOPAClient  # type: ignore
    client = MockOPAClient()
    allowed = client.check(
        input_data={"tenant_id": claims.tenant_id, "actor": claims.sub,
                    "action": body.action, "resource": body.resource,
                    "context": body.context}
    )
    decision = "ALLOW" if allowed else "DENY"

    row = q1("""
        INSERT INTO governance_decisions
            (id, tenant_id, case_id, decision_type, reason, risk_class, expires_at, created_at)
        VALUES (gen_random_uuid(), %s::uuid, %s::uuid, %s, %s, 'LOW', NOW() + INTERVAL '15 minutes', NOW())
        RETURNING id, decision_type, risk_class, created_at
    """, (claims.tenant_id,
          body.case_id if body.case_id else None,
          decision,
          f"Policy check for {body.action} on {body.resource}"))

    return {"decision_id": str(row["id"]), "decision": decision,
            "action": body.action, "resource": body.resource,
            "risk_class": row["risk_class"],
            "evaluated_at": row["created_at"].isoformat()}


@router.get("/policy/decisions/{decision_id}")
def get_policy_decision(decision_id: str, claims=Depends(get_claims)):
    row = q1("""
        SELECT id, tenant_id, case_id, decision_type, reason, risk_class, expires_at, created_at
        FROM governance_decisions WHERE id=%s::uuid AND tenant_id=%s::uuid
    """, (decision_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Policy decision not found")
    return {"id": str(row["id"]), "tenant_id": str(row["tenant_id"]),
            "case_id": str(row["case_id"]) if row.get("case_id") else None,
            "decision_type": row["decision_type"], "reason": row["reason"],
            "risk_class": row["risk_class"],
            "expires_at": row["expires_at"].isoformat() if row.get("expires_at") else None,
            "created_at": row["created_at"].isoformat()}


# ── Audit Chain ────────────────────────────────────────────────────────────────

@router.get("/policy/audit-chain/{case_id}")
def get_audit_chain(case_id: str, claims=Depends(get_claims)):
    """Full audit trail for a case: events + governance decisions + token + ACR."""
    case = q1("SELECT id, status, opened_at FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid", (case_id, claims.tenant_id))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    events = q("SELECT event_type, actor, payload, occurred_at FROM case_events WHERE case_id=%s::uuid ORDER BY occurred_at", (case_id,))
    decisions = q("SELECT id, decision_type, reason, risk_class, created_at FROM governance_decisions WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY created_at", (case_id, claims.tenant_id))
    tokens = q("SELECT id, status, issued_at, expires_at FROM governance_tokens WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY issued_at", (case_id, claims.tenant_id))
    acrs = q("SELECT id, acr_hash, merkle_root, created_at FROM action_certification_records WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY created_at", (case_id, claims.tenant_id))
    worm = q("SELECT artifact_type, artifact_hash, locked_at FROM audit_worm_index WHERE case_id=%s::uuid ORDER BY locked_at", (case_id,))

    return {
        "case_id": case_id,
        "case_status": case["status"],
        "opened_at": case["opened_at"].isoformat() if case.get("opened_at") else None,
        "events": [{"type": e["event_type"], "actor": e["actor"],
                    "at": e["occurred_at"].isoformat()} for e in events],
        "governance_decisions": [{"id": str(d["id"]), "decision": d["decision_type"],
                                   "risk_class": d["risk_class"],
                                   "at": d["created_at"].isoformat()} for d in decisions],
        "tokens": [{"id": str(t["id"]), "status": t["status"],
                    "issued_at": t["issued_at"].isoformat() if t.get("issued_at") else None,
                    "expires_at": t["expires_at"].isoformat() if t.get("expires_at") else None} for t in tokens],
        "acrs": [{"id": str(a["id"]), "acr_hash": a["acr_hash"],
                  "at": a["created_at"].isoformat()} for a in acrs],
        "worm_entries": [{"type": w["artifact_type"], "hash": w["artifact_hash"],
                          "locked_at": w["locked_at"].isoformat()} for w in worm],
    }


# ── Override Records ───────────────────────────────────────────────────────────

class OverrideIn(BaseModel):
    case_id:           Optional[str] = None
    override_type:     str = "MANUAL"
    original_decision: str
    override_decision: str
    reason:            str
    approved_by:       str = ""

@router.post("/policy/overrides", status_code=201)
def log_override(body: OverrideIn, claims=Depends(get_claims)):
    row = q1("""
        INSERT INTO override_records
            (id, tenant_id, case_id, override_type, original_decision, override_decision, reason, actor, approved_by)
        VALUES (gen_random_uuid(), %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s)
        RETURNING id, occurred_at
    """, (claims.tenant_id,
          body.case_id if body.case_id else None,
          body.override_type, body.original_decision, body.override_decision,
          body.reason, claims.sub, body.approved_by))
    return {"id": str(row["id"]), "case_id": body.case_id,
            "actor": claims.sub, "occurred_at": row["occurred_at"].isoformat()}

@router.get("/policy/overrides")
def list_overrides(case_id: Optional[str] = None, claims=Depends(get_claims)):
    if case_id:
        rows = q("SELECT id, case_id, override_type, original_decision, override_decision, reason, actor, occurred_at FROM override_records WHERE tenant_id=%s::uuid AND case_id=%s::uuid ORDER BY occurred_at DESC", (claims.tenant_id, case_id))
    else:
        rows = q("SELECT id, case_id, override_type, original_decision, override_decision, reason, actor, occurred_at FROM override_records WHERE tenant_id=%s::uuid ORDER BY occurred_at DESC LIMIT 50", (claims.tenant_id,))
    return [{"id": str(r["id"]),
             "case_id": str(r["case_id"]) if r.get("case_id") else None,
             "override_type": r["override_type"],
             "original": r["original_decision"], "override": r["override_decision"],
             "reason": r["reason"], "actor": r["actor"],
             "occurred_at": r["occurred_at"].isoformat()} for r in rows]
