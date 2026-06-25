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
from fastapi import FastAPI, APIRouter, Depends, Header, HTTPException, Query
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
from services.recovery.expected_recovery_svc.handler   import ExpectedRecoveryHandler
from services.recovery.expected_recovery_svc.models    import ExpectedRecoveryCreate
from services.recovery.recovery_instrument_svc.handler import RecoveryInstrumentHandler
from services.recovery.recovery_instrument_svc.models  import RecoveryInstrumentCreate
from services.recovery.recovery_match_svc.handler      import RecoveryMatchHandler
from services.recovery.ledger_svc.handler              import LedgerHandler
from services.recovery.write_off_svc.handler           import WriteOffHandler
from services.recovery.recovery_proof_svc.handler      import RecoveryProofHandler
from services.recovery.recovery_exceptions_svc.handler import RecoveryExceptionsHandler
import shared.db as _shared_db
_db_q1 = _shared_db.q1
from services.api_gateway.models import (
    HealthResponse, ExecuteRequest, ExecuteResponse,
    ReconcileRequest, ReconcileResponse, ACRResponse,
    VarianceRecord, ResolveVarianceRequest, ResolveVarianceResponse,
)
from services.api_gateway.models_ledger import (
    PostLedgerEntryRequest, ReverseLedgerEntryRequest, LedgerEntryResponse,
)
from services.api_gateway.models_recovery import (
    ExpectedRecoveryCreateRequest, ExpectedRecoveryResponse, SupersedeExpectedRecoveryRequest,
    RecoveryInstrumentCreateRequest, RecoveryInstrumentResponse,
    MatchRequest, ReverseMatchRequest, RecoveryMatchResponse,
)
from services.api_gateway.models_writeoff import (
    WriteOffCreateRequest, RejectWriteOffRequest, WriteOffResponse,
)
from services.api_gateway.models_proof import (
    GenerateProofRequest, RecoveryProofResponse,
)
from services.api_gateway.models_exceptions import (
    RecoveryExceptionResponse,
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
_expected_recovery   = ExpectedRecoveryHandler(DB_URL, _BROKER, TENANT_SLUG)
_recovery_instrument = RecoveryInstrumentHandler(DB_URL, _BROKER, TENANT_SLUG)
_recovery_match      = RecoveryMatchHandler(DB_URL, _BROKER, TENANT_SLUG)
_ledger              = LedgerHandler(DB_URL, _BROKER, TENANT_SLUG)
_write_off           = WriteOffHandler(DB_URL, _BROKER, TENANT_SLUG)
_recovery_proof      = RecoveryProofHandler(DB_URL, _BROKER, TENANT_SLUG)
_recovery_exceptions = RecoveryExceptionsHandler(DB_URL, _BROKER, TENANT_SLUG)


# ── Auth dependency ───────────────────────────────────────────────────────────

from middleware.oidc.token_verifier import TokenVerifier as _TV, TokenExpiredError as _TExpired, TokenInvalidError as _TInvalid
from fastapi.security import HTTPBearer as _Bearer, HTTPAuthorizationCredentials as _Creds
from fastapi import Security as _Security, Request as _Request
from typing import Optional as _Optional

_tv       = _TV(dev_secret=os.getenv("ZOIKO_DEV_SECRET", "").encode(), issuer=os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com"))
_security = _Bearer(auto_error=False)  # False = fall back to zoiko_jwt cookie when no Bearer header

def _auth_dep(
    request: _Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    credentials: _Optional[_Creds] = _Security(_security),
) -> ZoikoClaims:
    # Bearer header takes priority; fall back to HttpOnly cookie
    if credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get("zoiko_jwt")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        claims = _tv.verify(token)
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


# ── Phase 6 (Clarification 06 Slice 1) — Expected Recovery ───────────────────

@v1_router.post("/recovery/expected", response_model=ExpectedRecoveryResponse, status_code=201, tags=["recovery"])
def create_expected_recovery(
    body: ExpectedRecoveryCreateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    try:
        result = _expected_recovery.create(ExpectedRecoveryCreate(
            case_id                        = body.case_id,
            tenant_id                      = str(claims.tenant_id),
            expected_amount                = body.expected_amount,
            currency                       = body.currency,
            expected_recovery_method       = body.expected_recovery_method,
            counterparty_type              = body.counterparty_type,
            counterparty_id                = body.counterparty_id,
            expected_invoice_id            = body.expected_invoice_id,
            expected_external_invoice_ref  = body.expected_external_invoice_ref,
            authorization_decision_id      = body.authorization_decision_id,
            tolerance_policy_id            = body.tolerance_policy_id,
        ))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return ExpectedRecoveryResponse(
        expected_recovery_id    = result.expected_recovery_id,
        case_id                  = result.case_id,
        tenant_id                = result.tenant_id,
        expected_amount          = result.expected_amount,
        currency                 = result.currency,
        expected_recovery_method = result.expected_recovery_method,
        status                   = result.status,
        created_at               = result.created_at.isoformat(),
    )


@v1_router.get("/recovery/expected/{expected_recovery_id}", response_model=ExpectedRecoveryResponse, tags=["recovery"])
def get_expected_recovery(expected_recovery_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    result = _expected_recovery.get(expected_recovery_id, str(claims.tenant_id))
    if not result:
        raise HTTPException(status_code=404, detail="Expected recovery not found")
    return ExpectedRecoveryResponse(
        expected_recovery_id    = result.expected_recovery_id,
        case_id                  = result.case_id,
        tenant_id                = result.tenant_id,
        expected_amount          = result.expected_amount,
        currency                 = result.currency,
        expected_recovery_method = result.expected_recovery_method,
        status                   = result.status,
        created_at               = result.created_at.isoformat(),
    )


@v1_router.get("/recovery/expected:by-case", response_model=list[ExpectedRecoveryResponse], tags=["recovery"])
def list_expected_recoveries_by_case(case_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    results = _expected_recovery.list_by_case(case_id, str(claims.tenant_id))
    return [
        ExpectedRecoveryResponse(
            expected_recovery_id    = r.expected_recovery_id,
            case_id                  = r.case_id,
            tenant_id                = r.tenant_id,
            expected_amount          = r.expected_amount,
            currency                 = r.currency,
            expected_recovery_method = r.expected_recovery_method,
            status                   = r.status,
            created_at               = r.created_at.isoformat(),
        )
        for r in results
    ]


@v1_router.post(
    "/recovery/expected/{expected_recovery_id}/supersede",
    response_model=ExpectedRecoveryResponse, status_code=201, tags=["recovery"],
)
def supersede_expected_recovery(
    expected_recovery_id: str,
    body: SupersedeExpectedRecoveryRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    try:
        result = _expected_recovery.supersede(
            expected_recovery_id      = expected_recovery_id,
            tenant_id                  = str(claims.tenant_id),
            expected_amount            = body.expected_amount,
            currency                   = body.currency,
            expected_recovery_method   = body.expected_recovery_method,
            reason                     = body.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return ExpectedRecoveryResponse(
        expected_recovery_id    = result.expected_recovery_id,
        case_id                  = result.case_id,
        tenant_id                = result.tenant_id,
        expected_amount          = result.expected_amount,
        currency                 = result.currency,
        expected_recovery_method = result.expected_recovery_method,
        status                   = result.status,
        created_at               = result.created_at.isoformat(),
    )


# ── Phase 6 (Clarification 06 Slice 1) — Recovery Instruments ────────────────

@v1_router.post("/recovery/instruments", response_model=RecoveryInstrumentResponse, status_code=201, tags=["recovery"])
def create_recovery_instrument(
    body: RecoveryInstrumentCreateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    instrument_date = None
    if body.instrument_date:
        from datetime import date as _date
        instrument_date = _date.fromisoformat(body.instrument_date)

    try:
        result = _recovery_instrument.create(RecoveryInstrumentCreate(
            tenant_id                     = str(claims.tenant_id),
            instrument_type               = body.instrument_type,
            instrument_amount             = body.instrument_amount,
            created_by                    = claims.sub,
            currency                      = body.currency,
            counterparty_type             = body.counterparty_type,
            counterparty_id               = body.counterparty_id,
            related_case_id               = body.related_case_id,
            external_reference            = body.external_reference,
            related_external_invoice_ref  = body.related_external_invoice_ref,
            instrument_date               = instrument_date,
            source_record_id              = body.source_record_id,
        ))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return RecoveryInstrumentResponse(
        recovery_instrument_id = result.recovery_instrument_id,
        tenant_id                = result.tenant_id,
        instrument_type          = result.instrument_type,
        instrument_amount         = result.instrument_amount,
        currency                  = result.currency,
        status                    = result.status,
        related_case_id           = result.related_case_id,
        created_by                = result.created_by,
        created_at                = result.created_at.isoformat(),
    )


@v1_router.get("/recovery/instruments/{recovery_instrument_id}", response_model=RecoveryInstrumentResponse, tags=["recovery"])
def get_recovery_instrument(recovery_instrument_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    result = _recovery_instrument.get(recovery_instrument_id, str(claims.tenant_id))
    if not result:
        raise HTTPException(status_code=404, detail="Recovery instrument not found")
    return RecoveryInstrumentResponse(
        recovery_instrument_id = result.recovery_instrument_id,
        tenant_id                = result.tenant_id,
        instrument_type          = result.instrument_type,
        instrument_amount         = result.instrument_amount,
        currency                  = result.currency,
        status                    = result.status,
        related_case_id           = result.related_case_id,
        created_by                = result.created_by,
        created_at                = result.created_at.isoformat(),
    )


@v1_router.get("/recovery/instruments:by-case", response_model=list[RecoveryInstrumentResponse], tags=["recovery"])
def list_recovery_instruments_by_case(case_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    results = _recovery_instrument.list_by_case(case_id, str(claims.tenant_id))
    return [
        RecoveryInstrumentResponse(
            recovery_instrument_id = r.recovery_instrument_id,
            tenant_id                = r.tenant_id,
            instrument_type          = r.instrument_type,
            instrument_amount         = r.instrument_amount,
            currency                  = r.currency,
            status                    = r.status,
            related_case_id           = r.related_case_id,
            created_by                = r.created_by,
            created_at                = r.created_at.isoformat(),
        )
        for r in results
    ]


@v1_router.get("/recovery/instruments:by-counterparty", response_model=list[RecoveryInstrumentResponse], tags=["recovery"])
def list_recovery_instruments_by_counterparty(counterparty_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    results = _recovery_instrument.list_by_counterparty(counterparty_id, str(claims.tenant_id))
    return [
        RecoveryInstrumentResponse(
            recovery_instrument_id = r.recovery_instrument_id,
            tenant_id                = r.tenant_id,
            instrument_type          = r.instrument_type,
            instrument_amount         = r.instrument_amount,
            currency                  = r.currency,
            status                    = r.status,
            related_case_id           = r.related_case_id,
            created_by                = r.created_by,
            created_at                = r.created_at.isoformat(),
        )
        for r in results
    ]


# ── Phase 6 (Clarification 06 Slice 1) — Recovery Matching ───────────────────

def _match_to_response(r) -> RecoveryMatchResponse:
    return RecoveryMatchResponse(
        match_id               = r.match_id,
        expected_recovery_id   = r.expected_recovery_id,
        recovery_instrument_id = r.recovery_instrument_id,
        tenant_id               = r.tenant_id,
        match_tier              = r.match_tier,
        match_method            = r.match_method,
        match_confidence        = r.match_confidence,
        matched_amount          = r.matched_amount,
        expected_amount         = r.expected_amount,
        variance                = r.variance,
        currency                = r.currency,
        allocation_status       = r.allocation_status,
        matched_by              = r.matched_by,
        matched_at              = r.matched_at.isoformat(),
    )


@v1_router.post("/recovery/match", response_model=RecoveryMatchResponse, status_code=201, tags=["recovery"])
def create_recovery_match(
    body: MatchRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    try:
        result = _recovery_match.match(body.expected_recovery_id, str(claims.tenant_id), claims.sub)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="No candidate recovery instrument available")
    return _match_to_response(result)


@v1_router.get("/recovery/matches:by-expected", response_model=list[RecoveryMatchResponse], tags=["recovery"])
def list_recovery_matches_by_expected(expected_recovery_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    results = _recovery_match.list_by_expected(expected_recovery_id, str(claims.tenant_id))
    return [_match_to_response(r) for r in results]


@v1_router.get("/recovery/matches:by-case", response_model=list[RecoveryMatchResponse], tags=["recovery"])
def list_recovery_matches_by_case(case_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    results = _recovery_match.list_by_case(case_id, str(claims.tenant_id))
    return [_match_to_response(r) for r in results]


@v1_router.post("/recovery/matches/{match_id}/reverse", response_model=RecoveryMatchResponse, tags=["recovery"])
def reverse_recovery_match(
    match_id: str,
    body: ReverseMatchRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    try:
        result = _recovery_match.reverse(match_id, str(claims.tenant_id), claims.sub, body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _match_to_response(result)


# ── Phase 6 (Clarification 06 Slice 1) — Ledger Closure ──────────────────────

def _ledger_entry_to_response(r) -> LedgerEntryResponse:
    return LedgerEntryResponse(
        entry_id                  = r.entry_id,
        tenant_id                  = r.tenant_id,
        case_id                    = r.case_id,
        entry_type                 = r.entry_type,
        amount                     = r.amount,
        currency                   = r.currency,
        debit_account              = r.debit_account,
        credit_account             = r.credit_account,
        source_recovery_match_id   = r.source_recovery_match_id,
        reversal_of_entry_id       = r.reversal_of_entry_id,
        status                     = r.status,
        posted_at                  = r.posted_at.isoformat(),
        created_at                 = r.created_at.isoformat(),
    )


@v1_router.post("/ledger/entries", response_model=LedgerEntryResponse, status_code=201, tags=["ledger"])
def post_ledger_entry(
    body: PostLedgerEntryRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    try:
        result = _ledger.post_for_match(body.match_id, str(claims.tenant_id), claims.sub)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _ledger_entry_to_response(result)


@v1_router.get("/ledger/entries/{entry_id}", response_model=LedgerEntryResponse, tags=["ledger"])
def get_ledger_entry(entry_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    result = _ledger.get(entry_id, str(claims.tenant_id))
    if not result:
        raise HTTPException(status_code=404, detail="Ledger entry not found")
    return _ledger_entry_to_response(result)


@v1_router.get("/ledger/entries:by-case", response_model=list[LedgerEntryResponse], tags=["ledger"])
def list_ledger_entries_by_case(case_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    results = _ledger.list_by_case(case_id, str(claims.tenant_id))
    return [_ledger_entry_to_response(r) for r in results]


@v1_router.post("/ledger/entries/{entry_id}/reverse", response_model=LedgerEntryResponse, tags=["ledger"])
def reverse_ledger_entry(
    entry_id: str,
    body: ReverseLedgerEntryRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    try:
        result = _ledger.reverse_entry(entry_id, str(claims.tenant_id), claims.sub, body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _ledger_entry_to_response(result)


# ── Phase 6 (Clarification 06 Slice 1) — Write-Off Workflow ──────────────────

def _write_off_to_response(r) -> WriteOffResponse:
    return WriteOffResponse(
        write_off_id          = r.write_off_id,
        tenant_id              = r.tenant_id,
        case_id                = r.case_id,
        expected_recovery_id   = r.expected_recovery_id,
        amount                 = r.amount,
        currency               = r.currency,
        reason_code            = r.reason_code,
        policy_version_id      = r.policy_version_id,
        authorized_by          = r.authorized_by,
        authorized_at          = r.authorized_at.isoformat() if r.authorized_at else None,
        ledger_entry_id        = r.ledger_entry_id,
        status                 = r.status,
        created_at             = r.created_at.isoformat(),
    )


@v1_router.post("/recovery/write-offs", response_model=WriteOffResponse, status_code=201, tags=["recovery"])
def create_write_off(
    body: WriteOffCreateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    try:
        result = _write_off.request(
            body.expected_recovery_id, str(claims.tenant_id), claims.sub,
            body.reason_code, body.amount,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _write_off_to_response(result)


@v1_router.get("/recovery/write-offs/{write_off_id}", response_model=WriteOffResponse, tags=["recovery"])
def get_write_off(write_off_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    result = _write_off.get(write_off_id, str(claims.tenant_id))
    if not result:
        raise HTTPException(status_code=404, detail="Write-off not found")
    return _write_off_to_response(result)


@v1_router.get("/recovery/write-offs:by-case", response_model=list[WriteOffResponse], tags=["recovery"])
def list_write_offs_by_case(case_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    results = _write_off.list_by_case(case_id, str(claims.tenant_id))
    return [_write_off_to_response(r) for r in results]


@v1_router.post("/recovery/write-offs/{write_off_id}/authorize", response_model=WriteOffResponse, tags=["recovery"])
def authorize_write_off(
    write_off_id: str,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    try:
        result = _write_off.authorize(write_off_id, str(claims.tenant_id), claims.sub)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _write_off_to_response(result)


@v1_router.post("/recovery/write-offs/{write_off_id}/post", response_model=WriteOffResponse, tags=["recovery"])
def post_write_off(
    write_off_id: str,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    try:
        result = _write_off.post(write_off_id, str(claims.tenant_id), claims.sub)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _write_off_to_response(result)


@v1_router.post("/recovery/write-offs/{write_off_id}/reject", response_model=WriteOffResponse, tags=["recovery"])
def reject_write_off(
    write_off_id: str,
    body: RejectWriteOffRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    try:
        result = _write_off.reject(write_off_id, str(claims.tenant_id), claims.sub, body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _write_off_to_response(result)


# ── Phase 6 (Clarification 06 Slice 1) — Recovery Proof / ACR Readiness ───────

def _proof_to_response(r) -> RecoveryProofResponse:
    return RecoveryProofResponse(
        proof_id                  = r.proof_id,
        tenant_id                  = r.tenant_id,
        case_id                    = r.case_id,
        claimed_amount             = r.claimed_amount,
        currency                   = r.currency,
        expected_recovery_ids      = r.expected_recovery_ids,
        recovery_instrument_ids    = r.recovery_instrument_ids,
        recovery_match_ids         = r.recovery_match_ids,
        ledger_entry_ids           = r.ledger_entry_ids,
        total_expected             = r.total_expected,
        total_recovered            = r.total_recovered,
        total_unrecovered          = r.total_unrecovered,
        recovery_status            = r.recovery_status,
        ledger_status              = r.ledger_status,
        acr_ready                  = r.acr_ready,
        superseded_by              = r.superseded_by,
        created_at                 = r.created_at.isoformat(),
    )


@v1_router.post("/recovery/proofs", response_model=RecoveryProofResponse, status_code=201, tags=["recovery"])
def generate_recovery_proof(
    body: GenerateProofRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    try:
        result = _recovery_proof.generate(body.case_id, str(claims.tenant_id), claims.sub)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _proof_to_response(result)


@v1_router.get("/recovery/proofs/{proof_id}", response_model=RecoveryProofResponse, tags=["recovery"])
def get_recovery_proof(proof_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    result = _recovery_proof.get(proof_id, str(claims.tenant_id))
    if not result:
        raise HTTPException(status_code=404, detail="Recovery proof not found")
    return _proof_to_response(result)


@v1_router.get("/recovery/proofs:by-case", response_model=list[RecoveryProofResponse], tags=["recovery"])
def list_recovery_proofs_by_case(case_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    results = _recovery_proof.list_by_case(case_id, str(claims.tenant_id))
    return [_proof_to_response(r) for r in results]


@v1_router.get("/recovery/proofs:latest", response_model=RecoveryProofResponse, tags=["recovery"])
def get_latest_recovery_proof(case_id: str, claims: ZoikoClaims = Depends(_auth_dep)):
    result = _recovery_proof.get_latest_by_case(case_id, str(claims.tenant_id))
    if not result:
        raise HTTPException(status_code=404, detail="No recovery proof found for case")
    return _proof_to_response(result)


@v1_router.get("/recovery/exceptions", response_model=list[RecoveryExceptionResponse], tags=["recovery"])
def list_recovery_exceptions(
    case_id: str | None = Query(None),
    stuck_after_days: int = Query(7, ge=0),
    claims: ZoikoClaims = Depends(_auth_dep),
):
    results = _recovery_exceptions.list_exceptions(str(claims.tenant_id), case_id, stuck_after_days)
    return [
        RecoveryExceptionResponse(
            exception_type       = r.exception_type,
            tenant_id            = r.tenant_id,
            case_id              = r.case_id,
            expected_recovery_id = r.expected_recovery_id,
            recovery_match_id    = r.recovery_match_id,
            status               = r.status,
            amount               = r.amount,
            currency             = r.currency,
            age_days             = r.age_days,
            detail               = r.detail,
            detected_at          = r.detected_at.isoformat(),
        )
        for r in results
    ]


# ── Route registration ────────────────────────────────────────────────────────
app.include_router(v1_router, prefix="/v1")
app.include_router(v1_router)
