"""Evidence bundles, case timeline, and document endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from services.api_gateway.auth import get_claims
from shared.db import q, q1

router = APIRouter(tags=["evidence"])


# ── Evidence Bundles ───────────────────────────────────────────────────────────

class EvidenceBundleIn(BaseModel):
    case_id: str
    notes:   str = ""

@router.post("/evidence/bundles", status_code=201)
def create_evidence_bundle(body: EvidenceBundleIn, claims=Depends(get_claims)):
    case = q1("SELECT id FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid", (body.case_id, claims.tenant_id))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    placeholder = bytes(32)
    row = q1("""
        INSERT INTO evidence_bundles (id, tenant_id, case_id, bundle_hash, signature, kid, completeness_status)
        VALUES (gen_random_uuid(), %s::uuid, %s::uuid, %s, %s, %s, 'INCOMPLETE')
        RETURNING id, tenant_id, case_id, completeness_status, created_at
    """, (claims.tenant_id, body.case_id, placeholder, placeholder, "dev-placeholder"))
    return {"id": str(row["id"]), "tenant_id": str(row["tenant_id"]),
            "case_id": str(row["case_id"]), "completeness_status": row["completeness_status"],
            "created_at": row["created_at"].isoformat()}

@router.get("/cases/{case_id}/evidence")
def get_case_evidence(case_id: str, claims=Depends(get_claims)):
    case = q1("SELECT id FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid", (case_id, claims.tenant_id))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    bundles = q("""
        SELECT eb.id, eb.case_id, eb.completeness_status, eb.created_at,
               COUNT(ei.id) AS item_count
        FROM evidence_bundles eb
        LEFT JOIN evidence_items ei ON ei.bundle_id = eb.id
        WHERE eb.case_id=%s::uuid AND eb.tenant_id=%s::uuid
        GROUP BY eb.id ORDER BY eb.created_at DESC
    """, (case_id, claims.tenant_id))
    return {"case_id": case_id, "bundles": [
        {"id": str(b["id"]), "case_id": str(b["case_id"]),
         "completeness_status": b["completeness_status"],
         "item_count": b["item_count"],
         "created_at": b["created_at"].isoformat()} for b in bundles
    ]}

@router.get("/evidence/bundles/{bundle_id}")
def get_evidence_bundle(bundle_id: str, claims=Depends(get_claims)):
    row = q1("""
        SELECT eb.id, eb.tenant_id, eb.case_id, eb.completeness_status, eb.created_at
        FROM evidence_bundles eb WHERE eb.id=%s::uuid AND eb.tenant_id=%s::uuid
    """, (bundle_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Evidence bundle not found")
    items = q("""
        SELECT id, bundle_id, item_type, item_hash, added_at
        FROM evidence_items WHERE bundle_id=%s::uuid ORDER BY added_at
    """, (bundle_id,))
    return {
        "id": str(row["id"]), "tenant_id": str(row["tenant_id"]),
        "case_id": str(row["case_id"]),
        "completeness_status": row["completeness_status"],
        "created_at": row["created_at"].isoformat(),
        "items": [{"id": str(i["id"]), "item_type": i["item_type"],
                   "item_hash": i["item_hash"].hex(),
                   "added_at": i["added_at"].isoformat()} for i in items],
    }


# ── Case Timeline ──────────────────────────────────────────────────────────────

@router.get("/cases/{case_id}/timeline")
def get_case_timeline(case_id: str, claims=Depends(get_claims)):
    case = q1("SELECT id, state FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid", (case_id, claims.tenant_id))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Combine case_events (append-only) + case_timeline_entries
    events = q("""
        SELECT 'event' AS source, id, event_type, actor_sub AS actor, payload::text AS summary, occurred_at
        FROM case_events WHERE case_id=%s::uuid AND tenant_id=%s::uuid
        UNION ALL
        SELECT 'timeline' AS source, id, event_type, actor, summary, occurred_at
        FROM case_timeline_entries WHERE case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY occurred_at ASC
    """, (case_id, claims.tenant_id, case_id, claims.tenant_id))
    return {"case_id": case_id, "status": case["state"], "entries": [
        {"source": e["source"], "id": str(e["id"]),
         "event_type": e["event_type"], "actor": e["actor"],
         "summary": e["summary"] or "",
         "occurred_at": e["occurred_at"].isoformat()} for e in events
    ]}


# ── Request More Evidence ──────────────────────────────────────────────────────

class RequestEvidenceIn(BaseModel):
    reason:      str
    assigned_to: str = ""

@router.post("/cases/{case_id}/request-more-evidence", status_code=201)
def request_more_evidence(case_id: str, body: RequestEvidenceIn, claims=Depends(get_claims)):
    case = q1("SELECT id FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid", (case_id, claims.tenant_id))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    task = q1("""
        INSERT INTO tasks (id, tenant_id, case_id, task_type, assigned_to, status, notes)
        VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'GATHER_EVIDENCE', %s, 'PENDING', %s)
        RETURNING id, case_id, task_type, assigned_to, status, created_at
    """, (claims.tenant_id, case_id, body.assigned_to, body.reason))
    # Log to timeline
    q1("""
        INSERT INTO case_timeline_entries (id, tenant_id, case_id, event_type, actor, summary)
        VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'evidence.requested', %s, %s)
    """, (claims.tenant_id, case_id, claims.sub, body.reason))
    return {"task_id": str(task["id"]), "case_id": case_id,
            "task_type": "GATHER_EVIDENCE", "status": "PENDING",
            "assigned_to": body.assigned_to,
            "created_at": task["created_at"].isoformat()}
