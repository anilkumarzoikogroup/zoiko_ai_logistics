"""
SC-003 Execution Gateway — FastAPI application.
Port: 8021

Routes:
  GET  /health
  POST /execute                                      — 8-gate check, ISSUE_SLA_CREDIT
  POST /reconcile                                    — Commitment Match reconciliation
  GET  /cases/{case_id}/variances                    — variance records
  POST /cases/{case_id}/variances/{var_id}/resolve   — resolve or waive variance
  POST /cases/{case_id}/acr                          — issue WORM-locked ACR
  GET  /cases/{case_id}/acr                          — fetch ACR record

Required headers (mutating):
  Authorization: Bearer <JWT>
  X-Tenant-ID:   <tenant-uuid>
  Idempotency-Key: <client-uuid>
"""
import os
from dotenv import load_dotenv
import paths  # noqa: F401 — must be first

load_dotenv()

from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from services.api_gateway.auth import get_claims
from services.api_gateway.models import (
    ExecuteRequest, ReconcileRequest, ResolveVarianceRequest, IssueACRRequest,
)
from services.execution_gateway.handler import ExecutionGatewayHandler
from services.reconciliation_svc.handler import ReconciliationHandler
from services.audit_acr_svc.handler import AuditACRHandler
from shared.db import DB_URL as _DEFAULT_DB_URL

DB_URL      = os.getenv("DB_URL", _DEFAULT_DB_URL)
TENANT_SLUG = os.getenv("TENANT_SLUG", "default")


def _make_broker():
    from kafka.mock_kafka import MockKafkaBroker
    return MockKafkaBroker()


_BROKER = _make_broker()

app = FastAPI(
    title="Zoiko SC-003 — Shipment Exception Execution Gateway",
    version="1.0.0",
    description="8-gate execution, reconciliation, and ACR for SLA penalty recovery",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "sc003-execution", "version": "1.0.0"}


# ── Execute ───────────────────────────────────────────────────────────────────

@app.post("/execute")
def execute(
    body: ExecuteRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims=Depends(get_claims),
):
    return ExecutionGatewayHandler(DB_URL, _BROKER).execute(
        tenant_id  = claims.tenant_id,
        case_id    = body.case_id,
        token_id   = body.token_id,
        actor_sub  = claims.sub,
        action     = body.action,
        metadata   = body.metadata,
    )


# ── Reconcile ─────────────────────────────────────────────────────────────────

@app.post("/reconcile")
def reconcile(
    body: ReconcileRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims=Depends(get_claims),
):
    return ReconciliationHandler(DB_URL, _BROKER).reconcile(
        tenant_id   = claims.tenant_id,
        case_id     = body.case_id,
        envelope_id = body.envelope_id,
        actor_sub   = claims.sub,
    )


# ── Variances ─────────────────────────────────────────────────────────────────

@app.get("/cases/{case_id}/variances")
def get_variances(case_id: str, claims=Depends(get_claims)):
    return ReconciliationHandler(DB_URL, _BROKER).get_variances(claims.tenant_id, case_id)


@app.post("/cases/{case_id}/variances/{variance_id}/resolve")
def resolve_variance(
    case_id: str,
    variance_id: str,
    body: ResolveVarianceRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims=Depends(get_claims),
):
    if body.resolution not in ("RESOLVED", "WAIVED"):
        raise HTTPException(status_code=422, detail="resolution must be RESOLVED or WAIVED")
    return ReconciliationHandler(DB_URL, _BROKER).resolve_variance(
        tenant_id   = claims.tenant_id,
        case_id     = case_id,
        variance_id = variance_id,
        resolution  = body.resolution,
        actor_sub   = claims.sub,
        note        = body.note or "",
    )


# ── ACR ───────────────────────────────────────────────────────────────────────

@app.post("/cases/{case_id}/acr")
def issue_acr(
    case_id: str,
    body: IssueACRRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims=Depends(get_claims),
):
    result = AuditACRHandler(DB_URL, _BROKER).issue_acr(
        tenant_id   = claims.tenant_id,
        case_id     = case_id,
        envelope_id = body.envelope_id,
        actor_sub   = claims.sub,
    )
    if result.get("status") == "ERROR":
        raise HTTPException(status_code=422, detail=result.get("detail", "ACR error"))
    return result


@app.get("/cases/{case_id}/acr")
def get_acr(case_id: str, claims=Depends(get_claims)):
    record = AuditACRHandler(DB_URL, _BROKER).get_acr(claims.tenant_id, case_id)
    if not record:
        raise HTTPException(status_code=404, detail="ACR not yet issued for this case")
    return record
