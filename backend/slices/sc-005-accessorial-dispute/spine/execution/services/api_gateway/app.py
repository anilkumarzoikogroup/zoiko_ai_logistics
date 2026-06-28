"""SC-005 Execution Gateway — port 8041."""
import paths  # noqa: F401 — must be first

import os
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from services.api_gateway.auth import get_claims
from services.api_gateway.models import (
    ExecuteRequest, ReconcileRequest, ResolveVarianceRequest, IssueACRRequest,
)
from services.execution_gateway.handler import ExecutionGatewayHandler
from services.reconciliation_svc.handler import ReconciliationHandler
from services.audit_acr_svc.handler import AuditACRHandler
from shared.db import DB_URL, q, q1
from middleware.oidc.claims import ZoikoClaims

_DB_URL = os.getenv("DB_URL") or DB_URL

try:
    from platform_lib.kafka.mock_kafka import MockKafkaBroker
except ImportError:
    try:
        from backend.platform.kafka.mock_kafka import MockKafkaBroker
    except ImportError:
        class MockKafkaBroker:  # type: ignore
            def publish(self, *a, **kw): pass

broker = MockKafkaBroker()

app = FastAPI(
    title="Zoiko SC-005 — Accessorial Dispute Execution",
    version="1.0.0",
    description="8-gate execution → reconciliation (PARTIAL_ACCEPTANCE) → ACR for Accessorial Dispute",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "sc005-execution", "version": "1.0.0"}


@app.post("/v1/execute", status_code=201)
def execute(
    body:            ExecuteRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
):
    handler = ExecutionGatewayHandler(db_url=_DB_URL)
    result  = handler.execute(
        tenant_id=str(claims.tenant_id),
        case_id=body.case_id,
        token_id=body.token_id,
        actor_sub=body.actor_sub,
        action=body.action,
        metadata=body.metadata,
    )
    if result.get("status") == "REJECTED":
        raise HTTPException(status_code=422, detail=result)
    return result


@app.post("/v1/reconcile", status_code=201)
def reconcile(
    body:            ReconcileRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
):
    handler = ReconciliationHandler(db_url=_DB_URL)
    result  = handler.reconcile(
        tenant_id=str(claims.tenant_id),
        case_id=body.case_id,
        envelope_id=body.envelope_id,
        actor_sub=body.actor_sub,
    )
    if result.get("status") == "ERROR":
        raise HTTPException(status_code=422, detail=result.get("detail"))
    return result


@app.get("/v1/cases/{case_id}/variances")
def get_variances(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    rows = q(
        """SELECT id::text, variance_type, expected_value, actual_value,
                  delta, status, created_at
           FROM reconciliation_variances
           WHERE case_id=%s::uuid AND tenant_id=%s::uuid
           ORDER BY created_at DESC""",
        (case_id, str(claims.tenant_id)),
        db_url=_DB_URL,
    )
    return {"variances": rows, "total": len(rows)}


@app.post("/v1/cases/{case_id}/variances/{variance_id}/resolve", status_code=200)
def resolve_variance(
    case_id:     str,
    variance_id: str,
    body:        ResolveVarianceRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
):
    q(
        """
        UPDATE reconciliation_variances
        SET status=%s, resolution_note=%s, resolved_by=%s, resolved_at=NOW()
        WHERE id=%s::uuid AND case_id=%s::uuid AND tenant_id=%s::uuid AND status='OPEN'
        """,
        (body.resolution, body.note, body.actor_sub, variance_id, case_id, str(claims.tenant_id)),
        db_url=_DB_URL,
    )
    row = q1(
        "SELECT id::text, status FROM reconciliation_variances WHERE id=%s::uuid",
        (variance_id,),
        db_url=_DB_URL,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Variance not found")
    return row


@app.post("/v1/cases/{case_id}/acr", status_code=201)
def issue_acr(
    case_id:         str,
    body:            IssueACRRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
):
    handler = AuditACRHandler(db_url=_DB_URL)
    result  = handler.issue_acr(
        tenant_id=str(claims.tenant_id),
        case_id=case_id,
        actor_sub=body.actor_sub,
    )
    return result


@app.get("/v1/cases/{case_id}/acr")
def get_acr(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    row = q1(
        """SELECT id::text, case_id::text, tenant_id::text, artifact_count,
                  merkle_root, kid, issued_by, is_locked, issued_at
           FROM action_certification_records
           WHERE case_id=%s::uuid AND tenant_id=%s::uuid
           ORDER BY issued_at DESC
           LIMIT 1""",
        (case_id, str(claims.tenant_id)),
        db_url=_DB_URL,
    )
    if not row:
        raise HTTPException(status_code=404, detail="No ACR found")
    return row
