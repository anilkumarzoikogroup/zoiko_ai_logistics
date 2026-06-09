"""Reports & Audit: recovery report, compliance report, ACR detail."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from services.api_gateway.auth import get_claims
from shared.db import q, q1

router = APIRouter(tags=["reports"])


@router.get("/reports/recovery")
def report_recovery(claims=Depends(get_claims)):
    """Recovery report — totals by carrier, monthly breakdown."""
    by_carrier = q("""
        SELECT ci.carrier_id,
               COUNT(c.id)             AS case_count,
               SUM(o.amount)           AS total_recovered,
               AVG(o.amount)           AS avg_recovered,
               SUM(vr.variance_amount) AS total_overcharge
        FROM cases c
        JOIN canonical_invoices ci ON ci.id = c.invoice_id
        LEFT JOIN outcomes o ON o.case_id = c.id AND o.outcome_status = 'SETTLED'
        LEFT JOIN variance_records vr ON vr.case_id = c.id
        WHERE c.tenant_id=%s::uuid AND c.status='CLOSED'
        GROUP BY ci.carrier_id ORDER BY total_recovered DESC NULLS LAST
    """, (claims.tenant_id,))

    monthly = q("""
        SELECT DATE_TRUNC('month', c.opened_at) AS month,
               COUNT(c.id)       AS cases_opened,
               COUNT(c.id) FILTER (WHERE c.status='CLOSED') AS cases_closed,
               SUM(o.amount)     AS recovered
        FROM cases c
        LEFT JOIN outcomes o ON o.case_id = c.id AND o.outcome_status = 'SETTLED'
        WHERE c.tenant_id=%s::uuid
        GROUP BY 1 ORDER BY 1 DESC LIMIT 12
    """, (claims.tenant_id,))

    return {
        "by_carrier": [{"carrier_id": r["carrier_id"],
                        "case_count": r["case_count"],
                        "total_recovered": float(r["total_recovered"] or 0),
                        "avg_recovered": float(r["avg_recovered"] or 0),
                        "total_overcharge": float(r["total_overcharge"] or 0)} for r in by_carrier],
        "monthly": [{"month": r["month"].isoformat()[:7],
                     "cases_opened": r["cases_opened"],
                     "cases_closed": r["cases_closed"],
                     "recovered": float(r["recovered"] or 0)} for r in monthly],
    }


@router.get("/reports/compliance")
def report_compliance(claims=Depends(get_claims)):
    """Compliance report — SoD adherence, token issuance, WORM audit coverage."""
    total_cases = q1("SELECT COUNT(*) AS n FROM cases WHERE tenant_id=%s::uuid", (claims.tenant_id,))
    closed_cases = q1("SELECT COUNT(*) AS n FROM cases WHERE tenant_id=%s::uuid AND status='CLOSED'", (claims.tenant_id,))
    tokens_issued = q1("SELECT COUNT(*) AS n FROM governance_tokens WHERE tenant_id=%s::uuid", (claims.tenant_id,))
    tokens_consumed = q1("SELECT COUNT(*) AS n FROM governance_tokens WHERE tenant_id=%s::uuid AND status='CONSUMED'", (claims.tenant_id,))
    acr_count = q1("SELECT COUNT(*) AS n FROM action_certification_records WHERE tenant_id=%s::uuid", (claims.tenant_id,))
    worm_count = q1("SELECT COUNT(*) AS n FROM audit_worm_index WHERE tenant_id=%s::uuid", (claims.tenant_id,))
    overrides = q1("SELECT COUNT(*) AS n FROM override_records WHERE tenant_id=%s::uuid", (claims.tenant_id,))

    total = total_cases["n"] or 1
    return {
        "total_cases":       total_cases["n"],
        "closed_cases":      closed_cases["n"],
        "closure_rate":      round(closed_cases["n"] / total, 4),
        "tokens_issued":     tokens_issued["n"],
        "tokens_consumed":   tokens_consumed["n"],
        "token_utilisation": round(tokens_consumed["n"] / max(tokens_issued["n"], 1), 4),
        "acr_count":         acr_count["n"],
        "worm_entries":      worm_count["n"],
        "override_count":    overrides["n"],
        "sod_notes":         "Separation of Duties enforced at governance layer — proposer ≠ approver",
    }


@router.get("/acr/{acr_id}")
def get_acr(acr_id: str, claims=Depends(get_claims)):
    """Retrieve a specific Action Certification Record with its full audit bundle."""
    row = q1("""
        SELECT id, tenant_id, case_id, action_intent_id, governance_token_id,
               acr_hash, merkle_root, artifact_count, signature, created_at
        FROM action_certification_records
        WHERE id=%s::uuid AND tenant_id=%s::uuid
    """, (acr_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="ACR not found")

    worm = q("""
        SELECT artifact_type, artifact_hash, locked_at
        FROM audit_worm_index WHERE case_id=%s::uuid ORDER BY locked_at
    """, (row["case_id"],))

    return {
        "id": str(row["id"]), "tenant_id": str(row["tenant_id"]),
        "case_id": str(row["case_id"]),
        "action_intent_id": str(row["action_intent_id"]) if row.get("action_intent_id") else None,
        "governance_token_id": str(row["governance_token_id"]) if row.get("governance_token_id") else None,
        "acr_hash": row["acr_hash"], "merkle_root": row["merkle_root"],
        "artifact_count": row["artifact_count"], "signature": row["signature"],
        "created_at": row["created_at"].isoformat(),
        "worm_entries": [{"type": w["artifact_type"], "hash": w["artifact_hash"],
                          "locked_at": w["locked_at"].isoformat()} for w in worm],
    }
