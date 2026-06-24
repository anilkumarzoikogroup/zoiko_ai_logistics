"""Clarification 07 §19 — Observability API routes.

Exposes the 15 required metrics and 9 required alert conditions
so dashboards, on-call tooling and CI health checks can consume them.
"""
from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException

from services.api_gateway.auth      import get_claims
from services.observability_svc.handler import ObservabilityHandler

router = APIRouter(tags=["c07-observability"])

DB_URL = os.getenv("DB_URL", "")


def _obs(): return ObservabilityHandler(DB_URL)


@router.get("/data/observability/metrics")
def get_observability_metrics(claims=Depends(get_claims)):
    """§19.1 — All 15 required C07 metrics for this tenant."""
    try:
        return _obs().metrics(str(claims.tenant_id))
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/data/observability/alerts")
def get_observability_alerts(claims=Depends(get_claims)):
    """§19.2 — Currently firing C07 alert conditions for this tenant."""
    try:
        return _obs().alerts(str(claims.tenant_id))
    except Exception as e:
        raise HTTPException(500, str(e))
