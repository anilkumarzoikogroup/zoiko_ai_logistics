"""
Phase 4 API Gateway — Execution + Reconciliation + ACR

Routes (all registered under /v1/ AND / for backward compat):
  GET  /health
  POST /v1/execute                         — 8-gate execution, marks token CONSUMED
  POST /v1/reconcile                       — reconcile dispatched envelope
  POST /v1/cases/{case_id}/acr             — issue ACR for closed case
  GET  /v1/cases/{case_id}/acr             — retrieve ACR verify bundle

Required headers on all mutating routes:
  Authorization: Bearer <JWT>
  X-Tenant-ID:   <tenant-uuid>
  Idempotency-Key: <unique-string>

This gateway runs on port 8001 (Phase 2 runs on 8000).
"""
import os
from dotenv import load_dotenv
import paths  # noqa: F401 — must be first

load_dotenv()

from fastapi import FastAPI, APIRouter, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from middleware.oidc.claims import ZoikoClaims

DB_URL      = os.getenv("DB_URL")
TENANT_SLUG = os.getenv("TENANT_SLUG", "default")

from kafka.mock_kafka import MockKafkaBroker as _MockBroker
_BROKER = _MockBroker()

from services.execution_gateway.handler   import ExecutionGateway
from services.execution_gateway.models    import ExecutionRequest
from services.reconciliation_svc.handler import ReconciliationHandler
from services.audit_acr_svc.handler      import AuditACRHandler
from services.audit_acr_svc.verifier     import verify_bundle
import shared.db as _shared_db
_db_q1 = _shared_db.q1
from services.api_gateway.models import (
    HealthResponse, ExecuteRequest, ExecuteResponse,
    ReconcileRequest, ReconcileResponse, ACRResponse,
)

app = FastAPI(title="Zoiko Phase 4 — Execution Gateway", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OTel distributed tracing (FR-022)
try:
    from zoiko_common.observability.tracing import setup_tracing
    setup_tracing("phase4-execution-gateway")
except Exception:
    pass

# Security event publisher (FR-024)
from zoiko_common.security.events import SecurityEventPublisher, SecurityEventKind
_sec = SecurityEventPublisher(broker=_BROKER)

v1_router = APIRouter()

_execution      = ExecutionGateway(DB_URL, _BROKER, TENANT_SLUG)
_reconciliation = ReconciliationHandler(DB_URL, _BROKER, TENANT_SLUG)
_acr            = AuditACRHandler(DB_URL, _BROKER, TENANT_SLUG)


# ── Auth dependency ───────────────────────────────────────────────────────────

def _get_claims(
    authorization: str = Header(...),
    x_tenant_id:   str = Header(..., alias="X-Tenant-ID"),
) -> ZoikoClaims:
    from services.api_gateway.auth import get_claims as _gc
    # re-use the Phase 2/3 auth helper pattern
    return _gc.__wrapped__(authorization, x_tenant_id) if hasattr(_gc, "__wrapped__") else None


try:
    from middleware.oidc.token_verifier import TokenVerifier as _TV
    import jwt as _jwt
    _tv = _TV(
        dev_secret    = os.getenv("ZOIKO_DEV_SECRET").encode(),
        issuer        = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com"),
    )
    _DEV_MODE = os.getenv("ZOIKO_DEV_MODE", "false").lower() == "true"

    def _auth_dep(
        authorization: str = Header(...),
        x_tenant_id:   str = Header(..., alias="X-Tenant-ID"),
    ) -> ZoikoClaims:
        token = authorization.removeprefix("Bearer ").strip()
        if _DEV_MODE:
            import psycopg2, psycopg2.extras, uuid
            psycopg2.extras.register_uuid()
            conn = psycopg2.connect(DB_URL)
            cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT id, slug FROM tenants WHERE id=%s::uuid OR slug=%s LIMIT 1",
                        (x_tenant_id, x_tenant_id))
            row = cur.fetchone()
            conn.close()
            if row:
                tid = str(row["id"])
                slug = row["slug"]
            else:
                tid = x_tenant_id
                slug = "default"
            try:
                claims = _tv.verify(token)
            except Exception:
                claims = ZoikoClaims(sub="dev-user", tenant_id=tid, roles=["admin","analyst","manager"], zoiko_env="dev")
            object.__setattr__(claims, "tenant_id", tid)
            return claims
        return _tv.verify(token)

except Exception:
    def _auth_dep(
        authorization: str = Header(...),
        x_tenant_id:   str = Header(..., alias="X-Tenant-ID"),
    ) -> ZoikoClaims:
        raise HTTPException(status_code=500, detail="Auth not configured")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["ops"])
@app.get("/v1/health", response_model=HealthResponse, tags=["ops"], include_in_schema=False)
def health():
    return HealthResponse(status="ok", service="execution-gateway", version="4.0.0")


# ── Execute ───────────────────────────────────────────────────────────────────

@v1_router.post("/execute", response_model=ExecuteResponse, status_code=201, tags=["execution"])
def execute(
    body: ExecuteRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    """
    Run the 8-gate execution check and dispatch the credit if all pass.
    Atomically marks the governance token as CONSUMED.
    """
    req = ExecutionRequest(
        token_id  = body.token_id,
        tenant_id = str(claims.tenant_id),
        actor_sub = claims.sub,
    )
    try:
        result = _execution.execute(req)
    except ValueError as e:
        err_str = str(e)
        if "already consumed" in err_str.lower() or "gate 3" in err_str.lower():
            _sec.publish(SecurityEventKind.TOKEN_REPLAY, str(claims.tenant_id), {
                "token_id":  body.token_id,
                "actor_sub": claims.sub,
                "detail":    err_str,
            })
        raise HTTPException(status_code=422, detail=err_str)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return ExecuteResponse(
        envelope_id   = result.envelope_id,
        token_id      = result.token_id,
        case_id       = result.case_id,
        status        = result.status,
        connector_ref = result.connector_ref or "",
        dispatched_at = result.dispatched_at.isoformat(),
    )


# ── Reconcile ─────────────────────────────────────────────────────────────────

@v1_router.post("/reconcile", response_model=ReconcileResponse, status_code=201, tags=["reconciliation"])
def reconcile(
    body: ReconcileRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    """Reconcile a dispatched envelope against the connector settlement."""
    try:
        result = _reconciliation.reconcile(
            envelope_id = body.envelope_id,
            tenant_id   = str(claims.tenant_id),
            actor_sub   = body.actor_sub,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return ReconcileResponse(
        reconciliation_id = result.reconciliation_id,
        envelope_id       = result.envelope_id,
        status            = result.status,
        delta             = result.delta,
        reconciled_at     = result.reconciled_at.isoformat(),
    )


# ── ACR ───────────────────────────────────────────────────────────────────────

@v1_router.post("/cases/{case_id}/acr", response_model=ACRResponse, status_code=201, tags=["audit"])
def issue_acr(
    case_id: str,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    """Issue the Action Certification Record — the final audit artifact."""
    try:
        result = _acr.issue_acr(
            case_id   = case_id,
            tenant_id = str(claims.tenant_id),
            actor_sub = claims.sub,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return ACRResponse(
        acr_id         = result.acr_id,
        case_id        = result.case_id,
        merkle_root    = result.merkle_root,
        artifact_count = result.artifact_count,
        is_locked      = result.is_locked,
        issued_at      = result.issued_at.isoformat(),
        verify_bundle  = result.verify_bundle,
    )


@v1_router.get("/cases/{case_id}/acr", tags=["audit"])
def get_acr(case_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    """Retrieve the ACR verify bundle for a case."""
    row = _acr.get_acr(case_id, str(claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="ACR not yet issued for this case")
    return row


@v1_router.get("/acrs/{acr_id}/verify-package", tags=["audit"])
def download_verify_package(acr_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    """
    Download the ACR verify package — the JSON bundle needed for offline verification.
    Contains: acr_id, case_id, merkle_root, artifacts[], public_keys{}, acr_signature.
    """
    row = _db_q1(
        db_url=DB_URL,
        sql="""
            SELECT verify_bundle
            FROM   action_certification_records
            WHERE  id=%s::uuid AND tenant_id=%s::uuid
            LIMIT  1
        """,
        params=(acr_id, str(claims.tenant_id)),
    )
    if not row:
        raise HTTPException(status_code=404, detail="ACR not found")
    bundle = row["verify_bundle"]
    if isinstance(bundle, str):
        import json
        bundle = json.loads(bundle)
    return bundle


# ── Public verifier (no auth) ─────────────────────────────────────────────────

@app.post("/v1/verifier/acrs/verify", tags=["verifier"])
@app.post("/verifier/acrs/verify", tags=["verifier"], include_in_schema=False)
def verify_acr_bundle(bundle: dict):
    """
    Public endpoint — no auth required.
    Accepts a full ACR verify bundle (from /v1/acrs/{id}/verify-package)
    and returns a cryptographic verification result.

    Use for: T-012 (golden ACR → PASS), T-013 (tampered → FAIL), T-030.
    """
    result = verify_bundle(bundle)
    return {
        "passed":            result.passed,
        "acr_id":            result.acr_id,
        "case_id":           result.case_id,
        "merkle_root_match": result.merkle_root_match,
        "signature_valid":   result.signature_valid,
        "artifact_count":    result.artifact_count,
        "errors":            result.errors,
    }


# ── Route registration ────────────────────────────────────────────────────────
app.include_router(v1_router, prefix="/v1")
app.include_router(v1_router)
