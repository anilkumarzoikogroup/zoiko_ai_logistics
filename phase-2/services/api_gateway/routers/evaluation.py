"""Evaluation & Drift Service: evaluation runs, metrics, drift signals."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from services.api_gateway.auth import get_claims
from shared.db import q, q1

router = APIRouter(tags=["evaluation"])


class EvalRunIn(BaseModel):
    run_type:      str = "PRECISION"
    model_version: str = ""

@router.post("/evaluations/run", status_code=201)
def start_evaluation_run(body: EvalRunIn, claims=Depends(get_claims)):
    row = q1("""
        INSERT INTO evaluation_runs (id, tenant_id, run_type, model_version, status)
        VALUES (gen_random_uuid(), %s::uuid, %s, %s, 'RUNNING')
        RETURNING id, tenant_id, run_type, model_version, status, started_at
    """, (claims.tenant_id, body.run_type, body.model_version))
    return {"id": str(row["id"]), "tenant_id": str(row["tenant_id"]),
            "run_type": row["run_type"], "model_version": row["model_version"],
            "status": row["status"], "started_at": row["started_at"].isoformat()}

@router.get("/evaluations/{run_id}")
def get_evaluation_run(run_id: str, claims=Depends(get_claims)):
    row = q1("SELECT * FROM evaluation_runs WHERE id=%s::uuid AND tenant_id=%s::uuid", (run_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return {**row, "id": str(row["id"]), "tenant_id": str(row["tenant_id"]),
            "precision_score": float(row["precision_score"]) if row.get("precision_score") else None,
            "recall_score": float(row["recall_score"]) if row.get("recall_score") else None,
            "override_rate": float(row["override_rate"]) if row.get("override_rate") else None,
            "recovery_amount": float(row["recovery_amount"]) if row.get("recovery_amount") else None,
            "started_at": row["started_at"].isoformat(),
            "completed_at": row["completed_at"].isoformat() if row.get("completed_at") else None}


# ── Metrics ────────────────────────────────────────────────────────────────────

@router.get("/metrics/recovery")
def metrics_recovery(claims=Depends(get_claims)):
    """Total and average recovery amounts from closed cases."""
    row = q1("""
        SELECT
            COUNT(*) FILTER (WHERE status='CLOSED') AS total_closed,
            COUNT(*) FILTER (WHERE status='ABORTED') AS total_aborted,
            SUM(o.amount) AS total_recovered,
            AVG(o.amount) AS avg_recovered
        FROM cases c
        LEFT JOIN outcomes o ON o.case_id = c.id AND o.outcome_status = 'SETTLED'
        WHERE c.tenant_id=%s::uuid
    """, (claims.tenant_id,))
    return {
        "total_closed": row["total_closed"] or 0,
        "total_aborted": row["total_aborted"] or 0,
        "total_recovered": float(row["total_recovered"] or 0),
        "avg_recovered": float(row["avg_recovered"] or 0),
    }

@router.get("/metrics/precision")
def metrics_precision(claims=Depends(get_claims)):
    """Latest precision/recall scores from evaluation runs."""
    rows = q("""
        SELECT run_type, precision_score, recall_score, model_version, completed_at
        FROM evaluation_runs
        WHERE tenant_id=%s::uuid AND status='COMPLETED'
        ORDER BY completed_at DESC LIMIT 10
    """, (claims.tenant_id,))
    return {"runs": [{"run_type": r["run_type"],
                      "precision": float(r["precision_score"]) if r.get("precision_score") else None,
                      "recall": float(r["recall_score"]) if r.get("recall_score") else None,
                      "model_version": r["model_version"],
                      "completed_at": r["completed_at"].isoformat() if r.get("completed_at") else None}
                     for r in rows]}

@router.get("/metrics/drift")
def metrics_drift(claims=Depends(get_claims)):
    """Recent drift signals grouped by severity."""
    rows = q("""
        SELECT signal_type, severity, metric_name, baseline_value, current_value, delta, detected_at
        FROM drift_signals WHERE tenant_id=%s::uuid
        ORDER BY detected_at DESC LIMIT 50
    """, (claims.tenant_id,))
    return {"signals": [{"signal_type": r["signal_type"], "severity": r["severity"],
                          "metric_name": r["metric_name"],
                          "baseline": float(r["baseline_value"]) if r.get("baseline_value") else None,
                          "current": float(r["current_value"]) if r.get("current_value") else None,
                          "delta": float(r["delta"]) if r.get("delta") else None,
                          "detected_at": r["detected_at"].isoformat()} for r in rows]}

@router.get("/metrics/override-rates")
def metrics_override_rates(claims=Depends(get_claims)):
    """Override rates by type over all time."""
    total = q1("SELECT COUNT(*) AS n FROM cases WHERE tenant_id=%s::uuid", (claims.tenant_id,))
    overrides = q("""
        SELECT override_type, COUNT(*) AS cnt
        FROM override_records WHERE tenant_id=%s::uuid
        GROUP BY override_type ORDER BY cnt DESC
    """, (claims.tenant_id,))
    total_cases = total["n"] or 1
    return {
        "total_cases": total["n"],
        "override_breakdown": [{"type": r["override_type"], "count": r["cnt"],
                                  "rate": round(r["cnt"] / total_cases, 4)} for r in overrides],
    }
