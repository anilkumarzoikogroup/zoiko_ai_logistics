"""Policy & governance endpoints: policy check, decisions, audit chain, overrides."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional
import uuid

from services.api_gateway.auth import get_claims
from middleware.opa.client import OPAUnavailableError, resolve_opa_client
from shared.db import q, q1

router = APIRouter(tags=["policy"])

_OPA_URL        = os.getenv("OPA_URL", "")
_ZOIKO_DEV_MODE = os.getenv("ZOIKO_DEV_MODE", "false").lower() == "true"
_opa            = resolve_opa_client(_OPA_URL, _ZOIKO_DEV_MODE)


# ── Policy Evaluation ──────────────────────────────────────────────────────────

class PolicyCheckIn(BaseModel):
    case_id:    Optional[str] = None
    action:     str
    resource:   str
    context:    Dict[str, Any] = {}


@router.post("/policy/check")
def policy_check(body: PolicyCheckIn, claims=Depends(get_claims)):
    """
    Evaluate a governance policy decision — stateless OPA delegation.
    Fails closed (503) if no real OPA is reachable and the service is not
    running in dev mode — never silently allows.
    """
    try:
        decision = _opa.check_freight_dispute({
            "tenant_id": claims.tenant_id, "actor": claims.sub,
            "action": body.action, "resource": body.resource,
            "context": body.context,
        })
    except OPAUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    decision_id = str(uuid.uuid4())

    return {"decision_id": decision_id, "decision": "ALLOW" if decision.allow else "DENY",
            "action": body.action, "resource": body.resource,
            "risk_class": "LOW",
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "note": "Stateless evaluation — not persisted to governance_decisions"}


@router.get("/policy/decisions/{decision_id}")
def get_policy_decision(decision_id: str, claims=Depends(get_claims)):
    """Look up a governance decision written by Phase 3 governance_svc."""
    row = q1("""
        SELECT gd.id, gd.tenant_id, dp.case_id,
               gd.outcome, gd.decided_at
        FROM governance_decisions gd
        JOIN decision_proposals dp ON dp.id = gd.proposal_id
        WHERE gd.id=%s::uuid AND gd.tenant_id=%s::uuid
    """, (decision_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Policy decision not found")
    return {"id": str(row["id"]), "tenant_id": str(row["tenant_id"]),
            "case_id": str(row["case_id"]) if row.get("case_id") else None,
            "outcome": row["outcome"],
            "decided_at": row["decided_at"].isoformat()}


# ── Audit Chain ────────────────────────────────────────────────────────────────

@router.get("/policy/audit-chain/{case_id}")
def get_audit_chain(case_id: str, claims=Depends(get_claims)):
    """Full audit trail for a case: events + governance decisions + tokens + ACRs."""
    case = q1("SELECT id, state, opened_at FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid",
              (case_id, claims.tenant_id))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    events = q("""
        SELECT event_type, actor_sub AS actor, payload, occurred_at
        FROM case_events
        WHERE case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY occurred_at
    """, (case_id, claims.tenant_id))

    # governance_decisions are linked via proposal_id → decision_proposals.case_id
    decisions = q("""
        SELECT gd.id, gd.outcome, gd.decided_at
        FROM governance_decisions gd
        JOIN decision_proposals dp ON dp.id = gd.proposal_id
        WHERE dp.case_id=%s::uuid AND gd.tenant_id=%s::uuid
        ORDER BY gd.decided_at
    """, (case_id, claims.tenant_id))

    tokens = q("""
        SELECT id, status, issued_at, expires_at
        FROM governance_tokens
        WHERE case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY issued_at
    """, (case_id, claims.tenant_id))

    acrs = q("""
        SELECT id, encode(merkle_root, 'hex') AS merkle_root_hex, certified_at
        FROM action_certification_records
        WHERE case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY certified_at
    """, (case_id, claims.tenant_id))

    # worm entries linked via acr_id → action_certification_records.case_id
    worm = q("""
        SELECT wi.id, wi.worm_bucket, wi.object_name,
               encode(wi.object_hash, 'hex') AS hash_hex, wi.indexed_at
        FROM audit_worm_index wi
        JOIN action_certification_records acr ON acr.id = wi.acr_id
        WHERE acr.case_id=%s::uuid
        ORDER BY wi.indexed_at
    """, (case_id,))

    return {
        "case_id": case_id,
        "case_status": case["state"],
        "opened_at": case["opened_at"].isoformat() if case.get("opened_at") else None,
        "events": [{"type": e["event_type"], "actor": e["actor"],
                    "at": e["occurred_at"].isoformat()} for e in events],
        "governance_decisions": [{"id": str(d["id"]), "outcome": d["outcome"],
                                   "at": d["decided_at"].isoformat()} for d in decisions],
        "tokens": [{"id": str(t["id"]), "status": t["status"],
                    "issued_at": t["issued_at"].isoformat() if t.get("issued_at") else None,
                    "expires_at": t["expires_at"].isoformat() if t.get("expires_at") else None}
                   for t in tokens],
        "acrs": [{"id": str(a["id"]), "merkle_root": a["merkle_root_hex"],
                  "at": a["certified_at"].isoformat()} for a in acrs],
        "worm_entries": [{"bucket": w["worm_bucket"], "object": w["object_name"],
                          "hash": w["hash_hex"],
                          "indexed_at": w["indexed_at"].isoformat()} for w in worm],
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
            (id, tenant_id, case_id, override_type, original_decision,
             override_decision, reason, actor, approved_by)
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
        rows = q("""
            SELECT id, case_id, override_type, original_decision, override_decision,
                   reason, actor, occurred_at
            FROM override_records
            WHERE tenant_id=%s::uuid AND case_id=%s::uuid
            ORDER BY occurred_at DESC
        """, (claims.tenant_id, case_id))
    else:
        rows = q("""
            SELECT id, case_id, override_type, original_decision, override_decision,
                   reason, actor, occurred_at
            FROM override_records
            WHERE tenant_id=%s::uuid
            ORDER BY occurred_at DESC LIMIT 50
        """, (claims.tenant_id,))
    return [{"id": str(r["id"]),
             "case_id": str(r["case_id"]) if r.get("case_id") else None,
             "override_type": r["override_type"],
             "original": r["original_decision"], "override": r["override_decision"],
             "reason": r["reason"], "actor": r["actor"],
             "occurred_at": r["occurred_at"].isoformat()} for r in rows]
