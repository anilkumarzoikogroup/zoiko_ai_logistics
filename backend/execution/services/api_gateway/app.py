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

import io, json, zipfile
from fastapi import FastAPI, APIRouter, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

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
    VarianceRecord, ResolveVarianceRequest, ResolveVarianceResponse,
)

app = FastAPI(title="Zoiko Phase 4 — Execution Gateway", version="4.0.0")

try:
    from zoiko_common.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)
except ImportError:
    pass

_cors_origins = [o.strip() for o in os.getenv("ZOIKO_CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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

from middleware.oidc.token_verifier import TokenVerifier as _TV, TokenExpiredError as _TExpired, TokenInvalidError as _TInvalid
from fastapi.security import HTTPBearer as _Bearer, HTTPAuthorizationCredentials as _Creds
from fastapi import Security as _Security

_tv       = _TV(dev_secret=os.getenv("ZOIKO_DEV_SECRET", "").encode(), issuer=os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com"))
_security = _Bearer(auto_error=True)

def _auth_dep(
    x_tenant_id: str  = Header(..., alias="X-Tenant-ID"),
    credentials: _Creds = _Security(_security),
) -> ZoikoClaims:
    try:
        claims = _tv.verify(credentials.credentials)
    except _TExpired:
        raise HTTPException(status_code=401, detail="Token expired. Please log in again.")
    except _TInvalid as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")
    if str(claims.tenant_id) != str(x_tenant_id):
        raise HTTPException(status_code=403, detail="X-Tenant-ID does not match token tenant.")
    return claims


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


@v1_router.get("/cases/{case_id}/acr/download", tags=["audit"])
def download_acr_zip(case_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    """
    Download the offline-verifiable ACR zip package.
    Contains: acr.json, merkle_proof.json, public_keys/<kid>.pem, verify.sh, README.txt
    """
    row = _acr.get_acr(case_id, str(claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="ACR not yet issued for this case")

    verify_bundle_data = row.get("verify_bundle") or row
    if isinstance(verify_bundle_data, str):
        verify_bundle_data = json.loads(verify_bundle_data)

    # Build the zip in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # acr.json — main verify bundle
        zf.writestr("acr.json", json.dumps(verify_bundle_data, indent=2))

        # merkle_proof.json — artifact list with hashes for manual inspection
        artifacts = verify_bundle_data.get("artifacts", [])
        proof = {
            "acr_id":      verify_bundle_data.get("acr_id"),
            "case_id":     case_id,
            "merkle_root": verify_bundle_data.get("merkle_root"),
            "artifacts":   artifacts,
        }
        zf.writestr("merkle_proof.json", json.dumps(proof, indent=2))

        # public_keys/<kid>.pem — base64-encoded DER public keys
        for kid, key_b64 in verify_bundle_data.get("public_keys", {}).items():
            safe_kid = kid.replace("/", "_").replace(":", "_")
            zf.writestr(f"public_keys/{safe_kid}.pem", key_b64)

        # verify.sh — offline verification script
        verify_sh_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..", "verify.sh"
        )
        if os.path.exists(verify_sh_path):
            with open(verify_sh_path, "rb") as f:
                zf.writestr("verify.sh", f.read())

        # README.txt
        readme = (
            f"Zoiko ACR Verify Package\n"
            f"========================\n"
            f"Case:    {case_id}\n"
            f"ACR ID:  {verify_bundle_data.get('acr_id', 'N/A')}\n\n"
            f"Offline verification:\n"
            f"  bash verify.sh acr.json\n\n"
            f"Files:\n"
            f"  acr.json          — full ACR verify bundle\n"
            f"  merkle_proof.json — Merkle tree artifact list\n"
            f"  public_keys/      — Ed25519 public keys (PEM/base64 DER)\n"
            f"  verify.sh         — standalone bash verifier\n"
        )
        zf.writestr("README.txt", readme)

    buf.seek(0)
    filename = f"acr_verify_{case_id}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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


# ── Variance resolution (T-011) ──────────────────────────────────────────────

@v1_router.get("/cases/{case_id}/variances", response_model=list[VarianceRecord], tags=["variance"])
def list_variances(case_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    """List all variance records for a case (OPEN ones block ACR issuance)."""
    import psycopg2, psycopg2.extras, uuid as _uuid
    psycopg2.extras.register_uuid()
    rows = _shared_db.q(
        """SELECT id::text, case_id::text, tenant_id::text, variance_type,
                  expected_value, actual_value, delta, status,
                  resolved_by, resolved_at, created_at
           FROM variance_records
           WHERE case_id=%s::uuid AND tenant_id=%s::uuid
           ORDER BY created_at DESC""",
        (_uuid.UUID(case_id), str(claims.tenant_id)),
    )
    return [
        VarianceRecord(
            id             = r["id"],
            case_id        = r["case_id"],
            tenant_id      = r["tenant_id"],
            variance_type  = r["variance_type"],
            expected_value = float(r["expected_value"]) if r["expected_value"] is not None else None,
            actual_value   = float(r["actual_value"])   if r["actual_value"]   is not None else None,
            delta          = float(r["delta"])           if r["delta"]          is not None else None,
            status         = r["status"],
            resolved_by    = r["resolved_by"],
            resolved_at    = r["resolved_at"].isoformat() if r["resolved_at"] else None,
            created_at     = r["created_at"].isoformat(),
        )
        for r in rows
    ]


@v1_router.patch(
    "/cases/{case_id}/variances/{variance_id}/resolve",
    response_model=ResolveVarianceResponse,
    tags=["variance"],
)
def resolve_variance(
    case_id:     str,
    variance_id: str,
    body: ResolveVarianceRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    """Resolve or waive an open variance record. Required before ACR can be issued."""
    if body.action not in ("RESOLVE", "WAIVE"):
        raise HTTPException(status_code=422, detail="action must be RESOLVE or WAIVE")

    import psycopg2, psycopg2.extras, uuid as _uuid
    from datetime import datetime, timezone
    psycopg2.extras.register_uuid()

    new_status = "RESOLVED" if body.action == "RESOLVE" else "WAIVED"
    now = datetime.now(timezone.utc)

    with _shared_db.get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, status FROM variance_records "
            "WHERE id=%s::uuid AND case_id=%s::uuid AND tenant_id=%s::uuid",
            (_uuid.UUID(variance_id), _uuid.UUID(case_id), str(claims.tenant_id)),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Variance record not found")
        if row["status"] != "OPEN":
            raise HTTPException(status_code=422, detail=f"Variance is already {row['status']}")
        cur.execute(
            """UPDATE variance_records
               SET status=%s, resolved_by=%s, resolved_at=%s
               WHERE id=%s::uuid""",
            (new_status, body.resolved_by, now, _uuid.UUID(variance_id)),
        )
        conn.commit()

    return ResolveVarianceResponse(
        id          = variance_id,
        case_id     = case_id,
        status      = new_status,
        resolved_by = body.resolved_by,
        resolved_at = now.isoformat(),
    )


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
