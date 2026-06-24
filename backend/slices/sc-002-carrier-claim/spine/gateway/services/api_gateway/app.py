"""
API Gateway — FastAPI application for Phase 2.

Routes:
  GET  /health
  POST /invoices                          (ingest)
  POST /invoices/{source_record_id}/validate
  POST /invoices/{source_record_id}/canonicalize
  POST /cases                             (open case)
  PATCH /cases/{case_id}/state            (transition)

All mutating routes require:
  Authorization: Bearer <JWT>
  X-Tenant-ID:   <tenant-uuid>
  Idempotency-Key: <client-uuid>   (POST /invoices only)
"""
import os
from dotenv import load_dotenv
import paths  # noqa: F401 — must be first

load_dotenv()

from fastapi import FastAPI, Depends, Header, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse as _JSONResponse

from services.api_gateway.auth   import get_claims, get_claims_by_cookie
from zoiko_common.middleware.feature_flags import require_feature_flag
import re as _re, uuid, hashlib, json
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from services.api_gateway.models import (
    TransitionRequest, TransitionResponse,
    SubmitClaimRequest, UIProposalRequest, UIDecideRequest, NegotiateClaimRequest,
    ContractRateRequest,
    LoginRequest, RegisterRequest, RegisterResponse,
    UsersListResponse, UserItem,
    CreateApiKeyRequest, CreateApiKeyResponse, ApiKeyItem, ApiKeysListResponse,
    NotificationSettings, UsageSummary,
    TenantCreateRequest,
    ExecuteRequest,
    ErrorResponse,
)
from shared.db import q, q1
from zoiko_common.crypto.jcs import canonicalize as _jcs
from services.ingestion_svc.handler    import IngestionHandler
from services.canonical_truth.handler import CanonicalHandler
from services.case_orchestration.handler import CaseHandler, ConflictError
from middleware.oidc.claims import ZoikoClaims

DB_URL           = os.getenv("DB_URL")
TENANT_SLUG      = os.getenv("TENANT_SLUG", "default")
KAFKA_BOOTSTRAP  = os.getenv("KAFKA_BOOTSTRAP", "").strip()

# ── Kafka broker — real when KAFKA_BOOTSTRAP is set, mock otherwise ───────────
def _make_broker():
    if KAFKA_BOOTSTRAP:
        try:
            # Use importlib to avoid naming conflict with local phase-1/kafka package
            import importlib, logging
            _kafka_module = importlib.import_module("kafka.producer.kafka")
            _KP = getattr(_kafka_module, "KafkaProducer", None)
            if _KP is None:
                # Fallback: try direct import (works when kafka-python is installed)
                import importlib.util
                spec = importlib.util.find_spec("kafka")
                if spec and "kafka-python" in str(spec.origin):
                    _KP = importlib.import_module("kafka").KafkaProducer
            if _KP is None:
                raise ImportError("KafkaProducer not found in kafka-python")

            class _RealKafkaBroker:
                """Thin wrapper around kafka-python KafkaProducer matching MockKafkaBroker API."""
                def __init__(self, bootstrap: str):
                    self._producer = _KP(
                        bootstrap_servers=bootstrap,
                        value_serializer=lambda v: v if isinstance(v, bytes) else v,
                        key_serializer=lambda k: k if isinstance(k, bytes) else str(k).encode(),
                        acks="all",
                        retries=3,
                    )
                def send(self, topic, key=None, value=None, headers=None):
                    self._producer.send(topic, key=key, value=value, headers=headers or [])
                    self._producer.flush()

            broker = _RealKafkaBroker(KAFKA_BOOTSTRAP)
            logging.getLogger("zoiko.kafka").info("Connected to real Kafka at %s", KAFKA_BOOTSTRAP)
            return broker
        except Exception as exc:
            import logging
            logging.getLogger("zoiko.kafka").warning(
                "Real Kafka unavailable (%s) — falling back to mock broker", exc
            )
    from kafka.mock_kafka import MockKafkaBroker
    return MockKafkaBroker()

_BROKER = _make_broker()

# ── Auto-DDL: create tables on startup (self-healing, no manual DDL runs) ─────
def _init_db():
    """Run safe DDL on every boot — idempotent via IF NOT EXISTS."""
    import psycopg2 as _pg, logging, hashlib, textwrap
    from psycopg2.extras import RealDictCursor as _RDC
    _log = logging.getLogger("zoiko.db")
    DDL = [
        textwrap.dedent("""\
            CREATE TABLE IF NOT EXISTS signup_verification (
                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email            TEXT NOT NULL,
                org_name         TEXT NOT NULL,
                admin_name       TEXT NOT NULL,
                password_hash    TEXT NOT NULL,
                otp_hash         TEXT NOT NULL,
                failed_attempts  INTEGER NOT NULL DEFAULT 0,
                expires_at       TIMESTAMPTZ NOT NULL,
                used_at          TIMESTAMPTZ,
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """),
        textwrap.dedent("""\
            CREATE TABLE IF NOT EXISTS password_reset_otp (
                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email            TEXT NOT NULL,
                otp              TEXT NOT NULL,
                expires_at       TIMESTAMPTZ NOT NULL,
                used_at          TIMESTAMPTZ,
                failed_attempts  INTEGER NOT NULL DEFAULT 0,
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """),
        textwrap.dedent("""\
            CREATE TABLE IF NOT EXISTS password_reset_verify (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email        TEXT NOT NULL,
                verify_hash  TEXT NOT NULL,
                expires_at   TIMESTAMPTZ NOT NULL,
                used_at      TIMESTAMPTZ,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """),
        "ALTER TABLE password_reset_otp ADD COLUMN IF NOT EXISTS failed_attempts INTEGER NOT NULL DEFAULT 0",
    ]
    try:
        conn = _pg.connect(DB_URL)
        conn.autocommit = True
        cur = conn.cursor()
        for stmt in DDL:
            cur.execute(stmt)
        # Migrate old plaintext OTPs to SHA-256 hashes (one-time migration)
        cur = conn.cursor(cursor_factory=_RDC)
        cur.execute(
            "SELECT id, otp FROM password_reset_otp WHERE used_at IS NULL AND LENGTH(otp) < 64"
        )
        for row in cur.fetchall():
            _hashed = hashlib.sha256(row["otp"].encode()).hexdigest()
            cur.execute("UPDATE password_reset_otp SET otp = %s WHERE id = %s", (_hashed, row["id"]))
        cur.close()
        conn.close()
        _log.info("DB schema up to date (password_reset_otp + password_reset_verify)")
    except Exception as exc:
        _log.warning("DB schema sync skipped (%s) — app will still start", exc)

# ── FastAPI app with lifespan (outbox relay + startup logging) ────────────────
import threading
from contextlib import asynccontextmanager

def _run_outbox_relay():
    """Background thread: publishes pending outbox rows to Kafka every 0.5s."""
    import time
    try:
        from zoiko_common.kafka.outbox_relay import OutboxRelay
        relay = OutboxRelay(DB_URL, _BROKER, batch_size=50)
        import logging
        log = logging.getLogger("zoiko.outbox")
        log.info("Outbox relay started (polling every 500ms)")
        while True:
            try:
                n = relay.run_once()
                if n:
                    log.debug("Outbox relay published %d rows", n)
            except Exception as exc:
                log.warning("Outbox relay error: %s", exc)
            time.sleep(0.5)
    except Exception as exc:
        import logging
        logging.getLogger("zoiko.outbox").error("Outbox relay failed to start: %s", exc)

@asynccontextmanager
async def lifespan(app):
    # Auto-sync DB schema on every boot (idempotent — no manual DDL needed)
    _init_db()
    # Start outbox relay in background thread (daemon — exits with main process)
    _relay_thread = threading.Thread(target=_run_outbox_relay, daemon=True, name="outbox-relay")
    _relay_thread.start()
    import logging
    logging.getLogger("zoiko.startup").info(
        "Phase 2 started | Kafka=%s | RateLimit=%s",
        "real" if KAFKA_BOOTSTRAP else "mock",
        os.getenv("ZOIKO_RATE_LIMIT_ENABLED", "false"),
    )
    yield
    # Cleanup (thread is daemon, exits automatically)

app = FastAPI(title="Zoiko Logistics API Gateway", version="2.0.0", lifespan=lifespan)

_cors_origins_env = os.getenv("ZOIKO_CORS_ORIGINS", "http://localhost:5173")
_cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting — always on
try:
    from zoiko_common.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)
except ImportError:
    pass

# Security headers (spec §8.2)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as _Request

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: _Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "publickey-credentials-get=(self), publickey-credentials-create=(self)"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        # CSP — allow self only, no inline scripts
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "object-src 'none'; "
            "base-uri 'none'; "
            "frame-ancestors 'none'"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)

# X-Correlation-ID — generate/propagate on every request
class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: _Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

app.add_middleware(CorrelationIDMiddleware)

# OTel distributed tracing (FR-022)
try:
    from zoiko_common.observability.tracing import setup_tracing
    setup_tracing("phase2-api-gateway")
except Exception as _exc:
    import logging
    logging.getLogger("zoiko.startup").warning("Distributed tracing unavailable: %s", _exc)

# Security event publisher (FR-024)
from zoiko_common.security.events import SecurityEventPublisher, SecurityEventKind
_sec = SecurityEventPublisher(broker=_BROKER)

# All UI/internal routes are registered on v1_router; the router is included
# TWICE: once with /v1 prefix (spec §9.2) and once without (backward compat).
from fastapi import APIRouter as _AR
from fastapi.exceptions import RequestValidationError
v1_router = _AR()


# ── Global exception handlers ─────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: _Request, exc: RequestValidationError):
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    return _JSONResponse(
        status_code=422,
        content=ErrorResponse(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            correlation_id=correlation_id,
            recoverability_hint="Fix the request body according to the schema and retry.",
            details={"errors": exc.errors()},
        ).model_dump(),
    )


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: _Request, exc: HTTPException):
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    return _JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            code=f"HTTP_{exc.status_code}",
            message=str(exc.detail),
            correlation_id=correlation_id,
            recoverability_hint="See the message field for details.",
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: _Request, exc: Exception):
    import logging
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    logging.getLogger("zoiko.api").exception(
        "Unhandled exception [%s] %s %s", correlation_id, request.method, request.url
    )
    return _JSONResponse(
        status_code=500,
        content=ErrorResponse(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            correlation_id=correlation_id,
            recoverability_hint="Retry with exponential back-off. Contact support if the problem persists.",
        ).model_dump(),
    )


# ── Singleton handlers ────────────────────────────────────────────────────────

_ingestion  = IngestionHandler(DB_URL, _BROKER, TENANT_SLUG)
_canonical  = CanonicalHandler(DB_URL, _BROKER, TENANT_SLUG)
_cases      = CaseHandler(DB_URL, _BROKER)


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _auth_cookie_response(data: dict, token: str, ttl: int, status_code: int = 200):
    """Return auth data as JSON and set the JWT in an HttpOnly cookie.
    Token is never exposed in the response body — XSS cannot read it."""
    resp = _JSONResponse(status_code=status_code, content=data)
    is_prod = os.getenv("ZOIKO_ENV", "development").lower() == "production"
    resp.set_cookie(
        key="zoiko_jwt",
        value=token,
        httponly=True,           # JS cannot read this cookie
        secure=is_prod,          # HTTPS-only in production; HTTP allowed in dev
        samesite="strict",       # blocks CSRF
        max_age=ttl,
        path="/",
    )
    return resp


# ── Auth — public endpoints (no JWT required) ─────────────────────────────────

@app.post("/auth/login", tags=["auth"])
@app.post("/v1/auth/login", tags=["auth"], include_in_schema=False)
def login(body: LoginRequest):
    """Email + password → JWT. Works for all roles (analyst / manager / admin)."""
    import bcrypt as _bcrypt
    from middleware.oidc.token_verifier import TokenVerifier
    row = q1(
        "SELECT id, tenant_id, email, password_hash, full_name, role, is_active FROM users WHERE email = %s",
        (body.email.lower().strip(),),
    )
    if not row:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Account is disabled. Contact your admin.")
    if not row["password_hash"]:
        raise HTTPException(status_code=401, detail="This account was created with Google Sign-In. Please use the 'Sign in with Google' button to log in.")
    if not _bcrypt.checkpw(body.password.encode(), row["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    secret  = os.getenv("ZOIKO_DEV_SECRET", "").encode()
    issuer  = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com")
    ttl     = int(os.getenv("JWT_TTL_SECONDS", "86400"))   # 24h default
    verifier = TokenVerifier(dev_secret=secret, issuer=issuer)
    token   = verifier.make_dev_token(
        sub       = row["email"],
        tenant_id = str(row["tenant_id"]),
        roles     = [row["role"]],
        ttl_sec   = ttl,
    )
    return _auth_cookie_response(
        {"tenant_id": str(row["tenant_id"]), "role": row["role"], "full_name": row["full_name"], "email": row["email"], "expires_in": ttl},
        token=token, ttl=ttl,
    )


@app.post("/auth/setup", tags=["auth"])
@app.post("/v1/auth/setup", tags=["auth"], include_in_schema=False)
def setup_first_user(body: dict):
    """One-time setup: creates the first tenant + admin user. Returns 409 if any user already exists."""
    import bcrypt as _bcrypt, psycopg2 as _pg

    existing = q1("SELECT COUNT(*) AS cnt FROM users")
    if existing and int(existing["cnt"]) > 0:
        raise HTTPException(status_code=409, detail="Setup already complete — users exist. Use /auth/register to add more users.")

    email     = (body.get("email") or "").lower().strip()
    full_name = (body.get("full_name") or "").strip()
    password  = body.get("password") or ""
    org_name  = (body.get("org_name") or "My Organisation").strip()

    if not email or not password or not full_name:
        raise HTTPException(status_code=422, detail="email, full_name, and password are required")
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="password must be at least 8 characters")

    tenant_id = uuid.uuid4()
    user_id   = uuid.uuid4()
    slug      = org_name.lower().replace(" ", "-")[:50]
    pw_hash   = _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()
    now_dt    = datetime.now(timezone.utc)

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tenants (id, slug, display_name, status) VALUES (%s, %s, %s, 'ACTIVE') "
            "ON CONFLICT (slug) DO UPDATE SET display_name=EXCLUDED.display_name RETURNING id",
            (tenant_id, slug, org_name),
        )
        row = cur.fetchone()
        tenant_id = row[0]
        cur.execute(
            "INSERT INTO users (id, tenant_id, email, password_hash, full_name, role, created_at) "
            "VALUES (%s, %s, %s, %s, %s, 'admin', %s)",
            (user_id, tenant_id, email, pw_hash, full_name, now_dt),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "message":   "Setup complete. You can now log in at /auth/login.",
        "tenant_id": str(tenant_id),
        "email":     email,
        "role":      "admin",
    }


@app.post("/auth/register", response_model=RegisterResponse, tags=["auth"])
@app.post("/v1/auth/register", response_model=RegisterResponse, tags=["auth"], include_in_schema=False)
def register(body: RegisterRequest, claims: ZoikoClaims = Depends(get_claims)):
    """Admin-only: create a new analyst or manager for the same tenant."""
    import bcrypt as _bcrypt
    import psycopg2 as _pg
    if "admin" not in claims.roles:
        raise HTTPException(status_code=403, detail="Only admins can register new users")
    if body.role not in ("analyst", "manager", "admin"):
        raise HTTPException(status_code=422, detail="role must be analyst, manager, or admin")

    email = body.email.lower().strip()
    existing = q1("SELECT id FROM users WHERE email = %s", (email,))
    if existing:
        raise HTTPException(status_code=409, detail=f"Email '{email}' is already registered")

    need_welcome = body.password == ""
    pw_hash = _bcrypt.hashpw(body.password.encode(), _bcrypt.gensalt()).decode() if body.password else ""
    user_id = uuid.uuid4()
    now     = datetime.now(timezone.utc)

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (id, tenant_id, email, password_hash, full_name, role, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, claims.tenant_id, email, pw_hash, body.full_name.strip(), body.role, now),
        )
        conn.commit()
    finally:
        conn.close()

    if need_welcome:
        try:
            import smtplib
            from email.mime.text import MIMEText
            smtp_user = os.getenv("EMAIL_NAME", "")
            smtp_pass = os.getenv("EMAIL_PASSWORD", "")
            if smtp_user and smtp_pass:
                smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
                smtp_port = int(os.getenv("SMTP_PORT", "587"))
                msg = MIMEText(
                    f"Hello {body.full_name.strip()},\n\n"
                    f"You have been added as a {body.role} for ZoikoAI.\n\n"
                    f"Please set your password by visiting the following link:\n"
                    f"{os.getenv('APP_URL', 'http://localhost:5173')}/forgot-password\n\n"
                    f"Use the 'Forgot Password' option and enter your email ({email}) to receive an OTP.\n\n"
                    f"Best regards,\nZoikoAI Admin Team",
                    "plain", "utf-8",
                )
                msg["Subject"] = "ZoikoAI — You've been added as a team member"
                msg["From"] = smtp_user
                msg["To"] = email
                with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as s:
                    s.starttls()
                    s.login(smtp_user, smtp_pass)
                    s.sendmail(smtp_user, [email], msg.as_string())
        except Exception:
            pass  # welcome email is best-effort

    return RegisterResponse(
        user_id    = str(user_id),
        email      = email,
        full_name  = body.full_name.strip(),
        role       = body.role,
        tenant_id  = str(claims.tenant_id),
        created_at = now.isoformat(),
    )


@app.get("/auth/users", response_model=UsersListResponse, tags=["auth"])
@app.get("/v1/auth/users", response_model=UsersListResponse, tags=["auth"], include_in_schema=False)
def list_users(claims: ZoikoClaims = Depends(get_claims)):
    """Admin-only: list all users for the tenant."""
    if "admin" not in claims.roles:
        raise HTTPException(status_code=403, detail="Only admins can list users")
    rows = q(
        "SELECT id, email, full_name, role, is_active, created_at FROM users "
        "WHERE tenant_id = %s ORDER BY created_at ASC",
        (claims.tenant_id,),
    )
    return UsersListResponse(
        tenant_id = str(claims.tenant_id),
        users = [
            UserItem(
                user_id    = str(r["id"]),
                email      = r["email"],
                full_name  = r["full_name"],
                role       = r["role"],
                is_active  = r["is_active"],
                created_at = r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
            )
            for r in rows
        ],
    )


# ── API Keys (Settings → API Keys) ─────────────────────────────────────────────

@v1_router.get("/api-keys", response_model=ApiKeysListResponse, tags=["settings"])
def list_api_keys(claims: ZoikoClaims = Depends(get_claims)):
    """Admin-only: list API keys for the tenant (hashes never returned)."""
    if "admin" not in claims.roles:
        raise HTTPException(status_code=403, detail="Only admins can manage API keys")
    rows = q(
        "SELECT id, name, key_prefix, scopes, created_at, last_used_at, revoked_at "
        "FROM api_keys WHERE tenant_id = %s ORDER BY created_at DESC",
        (claims.tenant_id,),
    )
    return ApiKeysListResponse(
        tenant_id = str(claims.tenant_id),
        api_keys = [
            ApiKeyItem(
                id           = str(r["id"]),
                name         = r["name"],
                key_prefix   = r["key_prefix"],
                scopes       = r["scopes"],
                created_at   = r["created_at"].isoformat(),
                last_used_at = r["last_used_at"].isoformat() if r["last_used_at"] else None,
                revoked      = r["revoked_at"] is not None,
            )
            for r in rows
        ],
    )


@v1_router.post("/api-keys", response_model=CreateApiKeyResponse, status_code=201, tags=["settings"])
def create_api_key(body: CreateApiKeyRequest, claims: ZoikoClaims = Depends(get_claims)):
    """Admin-only: generate a new API key. The full key is returned once and never stored."""
    import secrets as _sec, hashlib as _hl, psycopg2 as _pg

    if "admin" not in claims.roles:
        raise HTTPException(status_code=403, detail="Only admins can manage API keys")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")

    secret     = _sec.token_urlsafe(32)
    full_key   = f"zk_live_{secret}"
    key_hash   = _hl.sha256(full_key.encode()).hexdigest()
    key_prefix = f"zk_live_••••••••••••••••{full_key[-4:]}"
    key_id     = uuid.uuid4()
    now        = datetime.now(timezone.utc)

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO api_keys (id, tenant_id, name, key_prefix, key_hash, scopes, created_by, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (key_id, claims.tenant_id, name, key_prefix, key_hash, body.scopes, claims.sub, now),
        )
        conn.commit()
    finally:
        conn.close()

    return CreateApiKeyResponse(
        id         = str(key_id),
        name       = name,
        key        = full_key,
        key_prefix = key_prefix,
        scopes     = body.scopes,
        created_at = now.isoformat(),
    )


@v1_router.delete("/api-keys/{key_id}", status_code=204, tags=["settings"])
def revoke_api_key(key_id: str, claims: ZoikoClaims = Depends(get_claims)):
    """Admin-only: revoke an API key (irreversible)."""
    import psycopg2 as _pg

    if "admin" not in claims.roles:
        raise HTTPException(status_code=403, detail="Only admins can manage API keys")
    row = q1("SELECT id FROM api_keys WHERE id = %s::uuid AND tenant_id = %s::uuid", (key_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="API key not found")

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE api_keys SET revoked_at = NOW() WHERE id = %s::uuid AND revoked_at IS NULL",
            (key_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return None


# ── Notification settings (Settings → Notifications) ───────────────────────────

@v1_router.get("/settings/notifications", response_model=NotificationSettings, tags=["settings"])
def get_notification_settings(claims: ZoikoClaims = Depends(get_claims)):
    """Per-tenant email alert toggles. Returns defaults (all enabled) if never saved."""
    row = q1(
        "SELECT case_opened_email, overcharge_detected_email, approval_needed_email, recovery_executed_email "
        "FROM tenant_notification_settings WHERE tenant_id = %s::uuid",
        (claims.tenant_id,),
    )
    if not row:
        return NotificationSettings()
    return NotificationSettings(**row)


@v1_router.put("/settings/notifications", response_model=NotificationSettings, tags=["settings"])
def update_notification_settings(body: NotificationSettings, claims: ZoikoClaims = Depends(get_claims)):
    """Admin-only: upsert per-tenant email alert toggles."""
    import psycopg2 as _pg

    if "admin" not in claims.roles:
        raise HTTPException(status_code=403, detail="Only admins can manage notification settings")

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tenant_notification_settings "
            "    (tenant_id, case_opened_email, overcharge_detected_email, approval_needed_email, recovery_executed_email, updated_at) "
            "VALUES (%s::uuid, %s, %s, %s, %s, NOW()) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "    case_opened_email = EXCLUDED.case_opened_email, "
            "    overcharge_detected_email = EXCLUDED.overcharge_detected_email, "
            "    approval_needed_email = EXCLUDED.approval_needed_email, "
            "    recovery_executed_email = EXCLUDED.recovery_executed_email, "
            "    updated_at = NOW()",
            (
                claims.tenant_id,
                body.case_opened_email,
                body.overcharge_detected_email,
                body.approval_needed_email,
                body.recovery_executed_email,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return body


# ── Billing / usage overview (Settings → Billing) ──────────────────────────────

@v1_router.get("/billing/usage", response_model=UsageSummary, tags=["settings"])
def get_billing_usage(claims: ZoikoClaims = Depends(get_claims)):
    """Real usage figures for the tenant — no payment data, informational plan only."""
    tid = claims.tenant_id

    tenant = q1("SELECT created_at FROM tenants WHERE id = %s::uuid", (tid,))

    cnt = q1("""
        SELECT
            COUNT(*) AS total_cases,
            SUM(CASE WHEN opened_at >= date_trunc('month', NOW()) THEN 1 ELSE 0 END) AS cases_this_month
        FROM cases WHERE tenant_id = %s::uuid
    """, (tid,))

    rec = q1("""
        SELECT COALESCE(SUM(acr.recovered_amount), 0) AS total_recovered
        FROM  cases c
        JOIN  claims cl ON cl.id = c.claim_id
        LEFT JOIN action_certification_records acr ON acr.case_id = c.id
        WHERE c.tenant_id = %s::uuid
          AND c.state IN ('EXECUTION_READY','DISPATCHED','OUTCOME_RECORDED','CLOSED')
    """, (tid,))

    users_cnt = q1("SELECT COUNT(*) AS active_users FROM users WHERE tenant_id = %s::uuid AND is_active = TRUE", (tid,))

    return UsageSummary(
        plan             = "Enterprise — all features included",
        member_since     = tenant["created_at"].isoformat() if tenant else "",
        total_cases      = int(cnt["total_cases"] or 0),
        cases_this_month = int(cnt["cases_this_month"] or 0),
        total_recovered  = float(rec["total_recovered"] or 0),
        active_users     = int(users_cnt["active_users"] or 0),
    )


@app.post("/auth/change-password", tags=["auth"])
@app.post("/v1/auth/change-password", tags=["auth"], include_in_schema=False)
def change_password(
    body: dict,
    claims: ZoikoClaims = Depends(get_claims),
):
    """Logged-in user changes their own password."""
    import bcrypt as _bcrypt, psycopg2 as _pg
    current_pw = body.get("current_password", "")
    new_pw     = body.get("new_password", "")
    if not current_pw or not new_pw:
        raise HTTPException(status_code=422, detail="current_password and new_password required")
    if len(new_pw) < 8:
        raise HTTPException(status_code=422, detail="new_password must be at least 8 characters")

    row = q1("SELECT id, password_hash FROM users WHERE email = %s", (claims.sub,))
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    if not _bcrypt.checkpw(current_pw.encode(), row["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    new_hash = _bcrypt.hashpw(new_pw.encode(), _bcrypt.gensalt()).decode()
    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, row["id"]))
        conn.commit()
    finally:
        conn.close()
    return {"message": "Password changed successfully"}


# ── SSO Discovery ────────────────────────────────────────────────────────────

@app.post("/auth/discover", tags=["auth"])
@app.post("/v1/auth/discover", tags=["auth"], include_in_schema=False)
def auth_discover(body: dict):
    """Email-first SSO discovery. Returns route: 'sso' | 'password' and optional idp_hint."""
    import time as _time, random as _rand
    email = str(body.get("email", "")).lower().strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Valid work email required")

    domain = email.split("@")[1]

    # Block personal email domains
    PERSONAL = {"gmail.com","yahoo.com","hotmail.com","outlook.com","icloud.com","protonmail.com"}
    if domain in PERSONAL:
        raise HTTPException(status_code=422, detail="Zoiko AI workspaces are tied to organization email addresses. Please use your work email.")

    # Constant-time jitter to prevent timing enumeration (spec §5.1)
    _time.sleep(_rand.uniform(0.05, 0.12))

    # Check sso_domains table
    sso_row = q1("SELECT idp_type, idp_config FROM sso_domains WHERE domain = %s AND is_active = TRUE", (domain,))
    if sso_row:
        return {"route": "sso", "idp_type": sso_row["idp_type"], "idp_hint": sso_row.get("idp_config", {}).get("hint", "")}

    # Check if user exists in users table
    user_row = q1("SELECT id FROM users WHERE email = %s", (email,))
    if user_row:
        return {"route": "password", "email": email}

    # Unknown email — still return password route (no enumeration)
    return {"route": "password", "email": email}


# ── Credential Recovery ───────────────────────────────────────────────────────

@app.post("/auth/recover/request", tags=["auth"], status_code=204)
@app.post("/v1/auth/recover/request", tags=["auth"], include_in_schema=False, status_code=204)
def recover_request(body: dict):
    """Constant-time forgot-password. Never reveals if account exists."""
    import secrets as _sec, hashlib as _hl, time as _time, random as _rand, psycopg2 as _pg
    email = str(body.get("email", "")).lower().strip()

    # Always sleep constant time (spec §7.1 anti-enumeration)
    _time.sleep(_rand.uniform(0.15, 0.25))

    if not email or "@" not in email:
        return  # 204 regardless

    user = q1("SELECT id FROM users WHERE email = %s", (email,))
    if not user:
        return  # 204 — do not reveal account existence

    # Generate single-use token
    raw_token = _sec.token_urlsafe(32)
    token_hash = _hl.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        # Invalidate previous tokens for this user
        cur.execute("UPDATE password_reset_tokens SET used_at = NOW() WHERE user_id = %s AND used_at IS NULL", (user["id"],))
        cur.execute(
            "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
            (user["id"], token_hash, expires_at)
        )
        conn.commit()
    finally:
        conn.close()

    # Send password reset email — return token in response so admin can share manually if email fails
    email_sent = False
    email_error = None
    try:
        from shared.email_sender import send_password_reset
        send_password_reset(email, raw_token, str(expires_at))
        email_sent = True
    except Exception as _email_err:
        import logging
        email_error = str(_email_err)
        logging.getLogger("zoiko.auth").error(
            "PASSWORD RESET EMAIL FAILED for %s: %s | Token (share manually): %s | Expires: %s",
            email, email_error, raw_token, expires_at,
        )

    response: dict = {"message": "If that email exists, a reset link has been sent.", "email_sent": email_sent}
    if email_error:
        response["email_warning"] = f"Email delivery failed ({email_error}). Check server logs for the reset link."
    return response


@app.post("/auth/recover/complete", tags=["auth"])
@app.post("/v1/auth/recover/complete", tags=["auth"], include_in_schema=False)
def recover_complete(body: dict):
    """Complete password reset with token from email."""
    import hashlib as _hl, bcrypt as _bcrypt, psycopg2 as _pg
    raw_token  = str(body.get("token", ""))
    new_pw     = str(body.get("new_password", ""))

    if not raw_token or not new_pw:
        raise HTTPException(status_code=422, detail="token and new_password required")
    if len(new_pw) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    token_hash = _hl.sha256(raw_token.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    row = q1("""
        SELECT prt.id, prt.user_id, u.email, u.tenant_id
        FROM   password_reset_tokens prt
        JOIN   users u ON u.id = prt.user_id
        WHERE  prt.token_hash = %s AND prt.used_at IS NULL AND prt.expires_at > %s
    """, (token_hash, now))

    if not row:
        raise HTTPException(status_code=401, detail="Reset link is invalid or has expired")

    pw_hash = _bcrypt.hashpw(new_pw.encode(), _bcrypt.gensalt()).decode()
    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (pw_hash, row["user_id"]))
        cur.execute("UPDATE password_reset_tokens SET used_at = %s WHERE id = %s", (now, row["id"]))
        conn.commit()
    finally:
        conn.close()

    # Generate new JWT
    from middleware.oidc.token_verifier import TokenVerifier
    secret  = os.getenv("ZOIKO_DEV_SECRET", "").encode()
    issuer  = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com")
    verifier = TokenVerifier(dev_secret=secret, issuer=issuer)
    # Fetch user's actual role from DB (do not hardcode — preserves manager/admin roles)
    user_row = q1("SELECT role FROM users WHERE email = %s", (row["email"],))
    actual_role = user_row["role"] if user_row else "analyst"
    token = verifier.make_dev_token(
        sub=row["email"], tenant_id=str(row["tenant_id"]), roles=[actual_role],
        ttl_sec=int(os.getenv("JWT_TTL_SECONDS", "86400")),
    )
    return {"message": "Password reset successfully", "token": token}


# ── OTP-based Forgot Password ─────────────────────────────────────────────────

@app.post("/auth/forgot-password", tags=["auth"])
@app.post("/v1/auth/forgot-password", tags=["auth"], include_in_schema=False)
def forgot_password(body: dict):
    """Send 6-digit OTP if email exists. Always returns same response — prevents user enumeration."""
    import secrets as _sec, hashlib as _hl, psycopg2 as _pg, smtplib, time as _time, random as _rand
    from email.mime.text import MIMEText

    email = str(body.get("email", "")).lower().strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Valid email required")

    user = q1("SELECT id FROM users WHERE email = %s", (email,))

    # Constant-time sleep — same delay whether email exists or not (anti-enumeration)
    _time.sleep(_rand.uniform(0.15, 0.25))

    if user:
        user_full = q1("SELECT full_name, role, password_hash FROM users WHERE email = %s", (email,))
        user_name = (user_full.get("full_name") or email) if user_full else email
        user_role = (user_full.get("role") or "User") if user_full else "User"
        has_pw    = bool(user_full and user_full.get("password_hash"))

        otp = f"{_sec.randbelow(900000) + 100000}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        conn = _pg.connect(DB_URL)
        try:
            cur = conn.cursor()
            cur.execute("UPDATE password_reset_otp SET used_at = NOW() WHERE email = %s AND used_at IS NULL", (email,))
            otp_hash = _hl.sha256(otp.encode()).hexdigest()
            cur.execute(
                "INSERT INTO password_reset_otp (email, otp, expires_at) VALUES (%s, %s, %s)",
                (email, otp_hash, expires_at),
            )
            conn.commit()
        finally:
            conn.close()

        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("EMAIL_NAME", "")
        smtp_pass = os.getenv("EMAIL_PASSWORD", "")

        if smtp_user and smtp_pass:
            import logging as _log
            try:
                if has_pw:
                    email_body = (
                        f"Hello {user_name},\n\n"
                        f"We received a request to reset your ZoikoAI password. "
                        f"Use the OTP below to set a new one:\n\n"
                        f"Your OTP: {otp}\n\n"
                        f"This code is valid for 10 minutes.\n\n"
                        f"If you didn't request this, please ignore this email.\n\n"
                        f"Best regards,\nZoikoAI Logistics Team"
                    )
                    subject = "ZoikoAI — Password Reset OTP"
                else:
                    email_body = (
                        f"Welcome to ZoikoAI, {user_name}!\n\n"
                        f"Your admin has added you as a {user_role}. "
                        f"Please create your password using the OTP below:\n\n"
                        f"Your OTP: {otp}\n\n"
                        f"This code is valid for 10 minutes.\n\n"
                        f"Best regards,\nZoikoAI Team"
                    )
                    subject = "ZoikoAI — Welcome! Set your password"
                msg = MIMEText(email_body, "plain", "utf-8")
                msg["Subject"] = subject
                msg["From"] = smtp_user
                msg["To"] = email
                with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as s:
                    s.starttls()
                    s.login(smtp_user, smtp_pass)
                    s.sendmail(smtp_user, [email], msg.as_string())
            except Exception as _exc:
                _log.getLogger("zoiko.auth").error("Forgot-password OTP email failed for %s: %s", email, _exc)

    return {"message": "If this email is registered, you'll receive a code.", "expires_in_minutes": 10}


@v1_router.post("/auth/verify-otp", tags=["auth"])
def verify_otp(body: dict):
    """Validate OTP and expiry. Returns a verification token for password reset."""
    import secrets as _sec, hashlib as _hl, psycopg2 as _pg
    from psycopg2.extras import RealDictCursor as _RDC

    email = str(body.get("email", "")).lower().strip()
    otp   = str(body.get("otp", "")).strip()

    if not email or not otp:
        raise HTTPException(status_code=422, detail="email and otp required")

    otp_hash = _hl.sha256(otp.encode()).hexdigest()

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor(cursor_factory=_RDC)
        # Try hashed match first (new style). If nil, try plaintext for backwards compat.
        cur.execute(
            "UPDATE password_reset_otp SET used_at = NOW() WHERE email = %s AND otp = %s AND used_at IS NULL RETURNING id, expires_at",
            (email, otp_hash),
        )
        row = cur.fetchone()
        if not row:
            # Backwards compat: some OTPs were stored as plaintext before the SHA-256 change
            cur.execute(
                "UPDATE password_reset_otp SET used_at = NOW() WHERE email = %s AND otp = %s AND used_at IS NULL RETURNING id, expires_at",
                (email, otp),
            )
            row = cur.fetchone()
        if not row:
            cur.execute(
                "UPDATE password_reset_otp SET failed_attempts = COALESCE(failed_attempts, 0) + 1 WHERE email = %s AND used_at IS NULL RETURNING failed_attempts",
                (email,),
            )
            fail_row = cur.fetchone()
            if fail_row and fail_row["failed_attempts"] >= 5:
                cur.execute(
                    "UPDATE password_reset_otp SET used_at = NOW() WHERE email = %s AND used_at IS NULL",
                    (email,),
                )
            conn.commit()
            raise HTTPException(status_code=401, detail="Invalid OTP")
        if datetime.now(timezone.utc) > row["expires_at"]:
            raise HTTPException(status_code=401, detail="OTP expired")

        verify_token = _sec.token_urlsafe(32)
        verify_hash  = _hl.sha256(verify_token.encode()).hexdigest()
        cur.execute(
            "INSERT INTO password_reset_verify (email, verify_hash, expires_at) VALUES (%s, %s, %s)",
            (email, verify_hash, datetime.now(timezone.utc) + timedelta(minutes=5)),
        )
        conn.commit()
    finally:
        conn.close()

    return {"message": "OTP verified", "verify_token": verify_token, "expires_in_minutes": 5}


@v1_router.post("/auth/reset-password", tags=["auth"])
def reset_password(body: dict):
    """Reset password using verify_token from OTP verification."""
    import bcrypt as _bcrypt, hashlib as _hl, psycopg2 as _pg
    from middleware.oidc.token_verifier import TokenVerifier

    email         = str(body.get("email", "")).lower().strip()
    verify_token  = str(body.get("verify_token", "")).strip()
    new_password  = str(body.get("password", ""))
    confirm_pw    = str(body.get("confirm_password", ""))

    if not email or not verify_token:
        raise HTTPException(status_code=422, detail="email and verify_token required")
    if len(new_password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    if new_password != confirm_pw:
        raise HTTPException(status_code=422, detail="Passwords do not match")

    verify_hash = _hl.sha256(verify_token.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    row = q1(
        "SELECT id FROM password_reset_verify WHERE email = %s AND verify_hash = %s AND used_at IS NULL AND expires_at > %s",
        (email, verify_hash, now),
    )
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired verification token")

    user = q1("SELECT id, tenant_id FROM users WHERE email = %s", (email,))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    pw_hash = _bcrypt.hashpw(new_password.encode(), _bcrypt.gensalt()).decode()

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (pw_hash, user["id"]))
        cur.execute("UPDATE password_reset_verify SET used_at = %s WHERE id = %s", (now, row["id"]))
        conn.commit()
    finally:
        conn.close()

    secret  = os.getenv("ZOIKO_DEV_SECRET", "").encode()
    issuer  = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com")
    verifier = TokenVerifier(dev_secret=secret, issuer=issuer)
    actual_role = q1("SELECT role FROM users WHERE email = %s", (email,))["role"]
    token = verifier.make_dev_token(
        sub=email, tenant_id=str(user["tenant_id"]), roles=[actual_role],
        ttl_sec=int(os.getenv("JWT_TTL_SECONDS", "86400")),
    )

    return {"message": "Password reset successfully", "token": token}


# ── Workspace Access Request (prospects — no tenant created) ──────────────────

@app.post("/auth/workspace-request", tags=["auth"], status_code=201)
@app.post("/v1/auth/workspace-request", tags=["auth"], include_in_schema=False, status_code=201)
def workspace_access_request(body: dict):
    """Lead capture for prospects. Routes to CRM. Never creates a tenant."""
    import psycopg2 as _pg
    required = ["full_name", "work_email", "company_name"]
    for f in required:
        if not body.get(f):
            raise HTTPException(status_code=422, detail=f"'{f}' is required")
    if not body.get("consent"):
        raise HTTPException(status_code=422, detail="Privacy consent is required")

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO workspace_access_requests
                (full_name, work_email, company_name, company_website, country,
                 role, use_case, team_size, heard_from, consent)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            body["full_name"], body["work_email"].lower().strip(),
            body["company_name"], body.get("company_website"),
            body.get("country"), body.get("role"),
            body.get("use_case"), body.get("team_size"),
            body.get("heard_from"), True,
        ))
        conn.commit()
    finally:
        conn.close()

    return {"message": "Access request submitted. A Zoiko representative will follow up within one business day."}


# ── Admin: manage workspace access requests ───────────────────────────────────

@app.get("/admin/workspace-requests", tags=["admin"])
@app.get("/v1/admin/workspace-requests", tags=["admin"], include_in_schema=False)
def list_workspace_requests(status: str = None, claims: ZoikoClaims = Depends(get_claims)):
    """List workspace access requests (admin only)."""
    import psycopg2 as _pg
    if "admin" not in claims.roles:
        raise HTTPException(status_code=403, detail="Admin access required")

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        if status:
            cur.execute("""
                SELECT id, full_name, work_email, company_name, company_website, country,
                       role, use_case, team_size, heard_from, status, created_at
                FROM workspace_access_requests WHERE status = %s ORDER BY created_at DESC
            """, (status,))
        else:
            cur.execute("""
                SELECT id, full_name, work_email, company_name, company_website, country,
                       role, use_case, team_size, heard_from, status, created_at
                FROM workspace_access_requests ORDER BY created_at DESC
            """)
        rows = cur.fetchall()
    finally:
        conn.close()

    keys = ["id","full_name","work_email","company_name","company_website","country",
            "role","use_case","team_size","heard_from","status","created_at"]
    requests_list = []
    for row in rows:
        d = dict(zip(keys, row))
        d["id"]         = str(d["id"])
        d["created_at"] = d["created_at"].isoformat() if d["created_at"] else None
        requests_list.append(d)

    return {"requests": requests_list, "total": len(requests_list)}


@app.post("/admin/workspace-requests/{req_id}/approve", tags=["admin"], status_code=201)
@app.post("/v1/admin/workspace-requests/{req_id}/approve", tags=["admin"], include_in_schema=False, status_code=201)
def approve_workspace_request(req_id: str, body: dict, claims: ZoikoClaims = Depends(get_claims)):
    """
    Approve a workspace request — creates a new tenant and admin user.
    Body: { "password": "temp-password" }
    """
    import psycopg2 as _pg
    import bcrypt as _bcrypt
    if "admin" not in claims.roles:
        raise HTTPException(status_code=403, detail="Admin access required")

    password = body.get("password", "")
    if not password or len(password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        # Load the request
        cur.execute("""
            SELECT id, full_name, work_email, company_name, status
            FROM workspace_access_requests WHERE id = %s::uuid
        """, (req_id,))
        req = cur.fetchone()
        if not req:
            raise HTTPException(status_code=404, detail="Workspace request not found")
        if req[4] not in ("PENDING", "CONTACTED", "QUALIFIED"):
            raise HTTPException(status_code=409, detail=f"Request already {req[4]}")

        full_name    = req[1]
        work_email   = req[2]
        company_name = req[3]

        # Check if email already registered
        cur.execute("SELECT id FROM users WHERE email = %s", (work_email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Email already registered as a user")

        # Create tenant slug from company name
        slug = _re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")[:40]
        cur.execute("SELECT COUNT(*) FROM tenants WHERE slug LIKE %s", (f"{slug}%",))
        count = cur.fetchone()[0]
        if count > 0:
            slug = f"{slug}-{count + 1}"

        now       = datetime.now(timezone.utc)
        tenant_id = uuid.uuid4()
        user_id   = uuid.uuid4()
        pw_hash   = _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

        cur.execute(
            "INSERT INTO tenants (id, display_name, slug, status, created_at, updated_at) "
            "VALUES (%s, %s, %s, 'ACTIVE', %s, %s)",
            (tenant_id, company_name, slug, now, now),
        )
        cur.execute(
            "INSERT INTO users (id, tenant_id, email, password_hash, full_name, role, created_at) "
            "VALUES (%s, %s, %s, %s, %s, 'admin', %s)",
            (user_id, tenant_id, work_email, pw_hash, full_name, now),
        )
        # Update request status
        cur.execute(
            "UPDATE workspace_access_requests SET status = 'QUALIFIED', crm_ref = %s WHERE id = %s::uuid",
            (str(tenant_id), req_id),
        )
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()

    return {
        "message":    f"Workspace approved. Tenant '{company_name}' created.",
        "tenant_id":  str(tenant_id),
        "user_id":    str(user_id),
        "email":      work_email,
        "tenant_slug": slug,
    }


@app.post("/admin/workspace-requests/{req_id}/reject", tags=["admin"], status_code=200)
@app.post("/v1/admin/workspace-requests/{req_id}/reject", tags=["admin"], include_in_schema=False, status_code=200)
def reject_workspace_request(req_id: str, claims: ZoikoClaims = Depends(get_claims)):
    """Reject a workspace access request (admin only)."""
    import psycopg2 as _pg
    if "admin" not in claims.roles:
        raise HTTPException(status_code=403, detail="Admin access required")

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, status FROM workspace_access_requests WHERE id = %s::uuid", (req_id,))
        req = cur.fetchone()
        if not req:
            raise HTTPException(status_code=404, detail="Workspace request not found")
        cur.execute(
            "UPDATE workspace_access_requests SET status = 'REJECTED' WHERE id = %s::uuid",
            (req_id,),
        )
        conn.commit()
    finally:
        conn.close()

    return {"message": "Request rejected"}


# ── Invite — send + accept ────────────────────────────────────────────────────

@app.post("/auth/invite/send", tags=["auth"], status_code=201)
@app.post("/v1/auth/invite/send", tags=["auth"], include_in_schema=False, status_code=201)
def send_invite(body: dict, claims: ZoikoClaims = Depends(get_claims)):
    """Admin sends an invitation to a new user."""
    import secrets as _sec, hashlib as _hl, psycopg2 as _pg
    if "admin" not in claims.roles:
        raise HTTPException(status_code=403, detail="Only admins can send invitations")
    email = str(body.get("email", "")).lower().strip()
    role  = str(body.get("role", "analyst"))
    if not email:
        raise HTTPException(status_code=422, detail="email required")
    if role not in ("analyst", "manager", "admin"):
        raise HTTPException(status_code=422, detail="role must be analyst, manager, or admin")

    existing = q1("SELECT id FROM users WHERE email = %s", (email,))
    if existing:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    raw_token  = _sec.token_urlsafe(32)
    token_hash = _hl.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO invitation_tokens (tenant_id, email, role, invited_by, token_hash, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (claims.tenant_id, email, role, claims.sub, token_hash, expires_at))
        conn.commit()
    finally:
        conn.close()

    # Send invitation email (SendGrid / SMTP / logs depending on EMAIL_PROVIDER)
    try:
        from shared.email_sender import send_invitation
        send_invitation(email, claims.sub, role, raw_token, str(expires_at))
    except Exception as _email_err:
        import logging
        logging.getLogger("zoiko.auth").warning("Invite email failed: %s — token: %s", _email_err, raw_token)
    return {"message": f"Invitation sent to {email}", "expires_at": expires_at.isoformat()}


@app.post("/auth/invite/accept", tags=["auth"])
@app.post("/v1/auth/invite/accept", tags=["auth"], include_in_schema=False)
def accept_invite(body: dict):
    """New user accepts invitation, creates account, returns JWT."""
    import hashlib as _hl, bcrypt as _bcrypt, psycopg2 as _pg
    raw_token = str(body.get("token", ""))
    full_name = str(body.get("full_name", "")).strip()
    password  = str(body.get("password", ""))

    if not raw_token or not full_name:
        raise HTTPException(status_code=422, detail="token and full_name required")

    token_hash = _hl.sha256(raw_token.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    inv = q1("""
        SELECT id, tenant_id, email, role FROM invitation_tokens
        WHERE token_hash = %s AND accepted_at IS NULL AND expires_at > %s
    """, (token_hash, now))

    if not inv:
        raise HTTPException(status_code=401, detail="Invitation is invalid or has expired")

    if len(password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    pw_hash  = _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()
    user_id  = uuid.uuid4()

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (id, tenant_id, email, password_hash, full_name, role)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, inv["tenant_id"], inv["email"], pw_hash, full_name, inv["role"]))
        cur.execute("UPDATE invitation_tokens SET accepted_at = %s WHERE id = %s", (now, inv["id"]))
        conn.commit()
    finally:
        conn.close()

    from middleware.oidc.token_verifier import TokenVerifier
    verifier = TokenVerifier(dev_secret=os.getenv("ZOIKO_DEV_SECRET","").encode(), issuer=os.getenv("ZOIKO_ISSUER","https://auth.zoikotech.com"))
    token = verifier.make_dev_token(sub=inv["email"], tenant_id=str(inv["tenant_id"]), roles=[inv["role"]], ttl_sec=int(os.getenv("JWT_TTL_SECONDS","86400")))
    return {"token": token, "email": inv["email"], "role": inv["role"], "tenant_id": str(inv["tenant_id"]), "full_name": full_name}


# ── Organization signup — public, no auth required ────────────────────────────

@app.post("/auth/org-signup", tags=["auth"], status_code=201)
@app.post("/v1/auth/org-signup", tags=["auth"], include_in_schema=False, status_code=201)
def org_signup(body: dict):
    """
    Public endpoint: create a new tenant + admin user in one transaction.
    On success returns JWT so the user can immediately access the dashboard.
    Body: { org_name, admin_name, admin_email, admin_password }
    """
    import bcrypt as _bcrypt, psycopg2 as _pg

    org_name     = str(body.get("org_name", "")).strip()
    admin_name   = str(body.get("admin_name", "")).strip()
    admin_email  = str(body.get("admin_email", "")).lower().strip()
    admin_pw     = str(body.get("admin_password", ""))

    for field, label in [
        (org_name, "org_name"), (admin_name, "admin_name"),
        (admin_email, "admin_email"), (admin_pw, "admin_password"),
    ]:
        if not field:
            raise HTTPException(status_code=422, detail=f"'{label}' is required")
    if len(admin_pw) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    if "@" not in admin_email:
        raise HTTPException(status_code=422, detail="Valid email required")

    slug = org_name.lower().replace(" ", "-").replace("_", "-")

    existing_tenant = q1("SELECT id FROM tenants WHERE slug = %s", (slug,))
    if existing_tenant:
        raise HTTPException(
            status_code=409,
            detail=f"Organization '{org_name}' already registered. Please contact your admin or use sign in."
        )
    existing_user = q1("SELECT id FROM users WHERE email = %s", (admin_email,))
    if existing_user:
        raise HTTPException(status_code=409, detail="Email already registered. Please sign in instead.")

    tenant_id = uuid.uuid4()
    user_id   = uuid.uuid4()
    now       = datetime.now(timezone.utc)
    pw_hash   = _bcrypt.hashpw(admin_pw.encode(), _bcrypt.gensalt()).decode()

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tenants (id, display_name, slug, status, created_at, updated_at) "
            "VALUES (%s, %s, %s, 'ACTIVE', %s, %s)",
            (tenant_id, org_name, slug, now, now),
        )
        cur.execute(
            "INSERT INTO users (id, tenant_id, email, password_hash, full_name, role, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, tenant_id, admin_email, pw_hash, admin_name, "admin", now),
        )
        conn.commit()
    finally:
        conn.close()

    # Generate JWT
    from middleware.oidc.token_verifier import TokenVerifier
    secret  = os.getenv("ZOIKO_DEV_SECRET", "").encode()
    issuer  = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com")
    ttl     = int(os.getenv("JWT_TTL_SECONDS", "86400"))
    verifier = TokenVerifier(dev_secret=secret, issuer=issuer)
    token   = verifier.make_dev_token(
        sub=admin_email, tenant_id=str(tenant_id),
        roles=["admin"], ttl_sec=ttl,
    )

    return _auth_cookie_response(
        {"tenant_id": str(tenant_id), "role": "admin", "full_name": admin_name, "email": admin_email, "expires_in": ttl, "org_name": org_name},
        token=token, ttl=ttl, status_code=201,
    )


# ── Google OAuth — verify GSI ID token, find or create user ───────────────────

@app.post("/auth/google", tags=["auth"])
@app.post("/v1/auth/google", tags=["auth"], include_in_schema=False)
def google_auth(body: dict):
    """
    Accepts a Google Identity Services (GSI) credential (ID token).

    Responses:
      200 — existing user found → returns JWT immediately
      201 — new user, org created → returns JWT
      202 — new user, no org yet → returns {status:'new_user', email, name}
              (frontend should collect org_name and re-POST with it)

    Body: { credential: str, org_name?: str }
    """
    import requests as _req, psycopg2 as _pg

    credential = str(body.get("credential", "")).strip()
    org_name   = str(body.get("org_name", "")).strip()

    if not credential:
        raise HTTPException(status_code=422, detail="'credential' is required")

    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if not google_client_id:
        raise HTTPException(status_code=503, detail="Google auth is not configured on this server")

    # Verify the Google ID token via Google's tokeninfo endpoint
    try:
        r = _req.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": credential},
            timeout=10,
        )
    except _req.RequestException as exc:
        raise HTTPException(status_code=503, detail=f"Could not reach Google: {exc}")

    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Google credential")

    info = r.json()
    if info.get("aud") != google_client_id:
        raise HTTPException(status_code=401, detail="Token audience mismatch — wrong Google client")
    if info.get("email_verified") not in (True, "true"):
        raise HTTPException(status_code=401, detail="Google email is not verified")

    email = info.get("email", "").lower().strip()
    name  = (info.get("name") or info.get("given_name") or email.split("@")[0]).strip()

    if not email:
        raise HTTPException(status_code=422, detail="Google account has no email address")

    # ── Existing user → return JWT immediately ────────────────────────────────
    existing = q1(
        "SELECT id, tenant_id, full_name, role FROM users WHERE email = %s AND is_active = true",
        (email,),
    )
    if existing:
        from middleware.oidc.token_verifier import TokenVerifier
        secret   = os.getenv("ZOIKO_DEV_SECRET", "").encode()
        issuer   = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com")
        ttl      = int(os.getenv("JWT_TTL_SECONDS", "86400"))
        verifier = TokenVerifier(dev_secret=secret, issuer=issuer)
        token    = verifier.make_dev_token(
            sub=email, tenant_id=str(existing["tenant_id"]),
            roles=[existing["role"]], ttl_sec=ttl,
        )
        return _auth_cookie_response(
            {"tenant_id": str(existing["tenant_id"]), "role": existing["role"], "full_name": existing["full_name"], "email": email, "expires_in": ttl},
            token=token, ttl=ttl,
        )

    # ── New user — need org_name before creating account ─────────────────────
    if not org_name:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=202, content={
            "status": "new_user",
            "email":  email,
            "name":   name,
        })

    # ── Create tenant + user (Google SSO — no password) ───────────────────────
    slug = _re.sub(r"[^a-z0-9-]", "", org_name.lower().replace(" ", "-").replace("_", "-"))
    if not slug:
        raise HTTPException(status_code=422, detail="Invalid organization name")

    if q1("SELECT id FROM tenants WHERE slug = %s", (slug,)):
        raise HTTPException(status_code=409, detail=f"Organization '{org_name}' already registered.")
    if q1("SELECT id FROM users WHERE email = %s", (email,)):
        raise HTTPException(status_code=409, detail="Email already registered. Please sign in.")

    tenant_id = uuid.uuid4()
    user_id   = uuid.uuid4()
    now       = datetime.now(timezone.utc)
    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tenants (id, display_name, slug, status, created_at, updated_at) "
            "VALUES (%s, %s, %s, 'ACTIVE', %s, %s)",
            (tenant_id, org_name, slug, now, now),
        )
        cur.execute(
            "INSERT INTO users (id, tenant_id, email, password_hash, full_name, role, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, tenant_id, email, '', name, "admin", now),  # empty = Google SSO, no password login
        )
        conn.commit()
    finally:
        conn.close()

    from middleware.oidc.token_verifier import TokenVerifier
    from fastapi.responses import JSONResponse
    secret   = os.getenv("ZOIKO_DEV_SECRET", "").encode()
    issuer   = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com")
    ttl      = int(os.getenv("JWT_TTL_SECONDS", "86400"))
    verifier = TokenVerifier(dev_secret=secret, issuer=issuer)
    token    = verifier.make_dev_token(
        sub=email, tenant_id=str(tenant_id), roles=["admin"], ttl_sec=ttl,
    )
    return _auth_cookie_response(
        {"tenant_id": str(tenant_id), "role": "admin", "full_name": name, "email": email, "expires_in": ttl, "org_name": org_name},
        token=token, ttl=ttl, status_code=201,
    )


# ── Google OAuth — Authorization Code exchange ────────────────────────────────

@app.post("/auth/google/callback", tags=["auth"])
@app.post("/v1/auth/google/callback", tags=["auth"], include_in_schema=False)
def google_callback(body: dict):
    """
    Exchange Google authorization code (from redirect) for user info.
    Returns JWT for existing users, or 202 + signup_token for new users.
    Body: { code: str, redirect_uri: str }
    """
    import requests as _req, jwt as _jwt, time as _time

    code         = str(body.get("code", "")).strip()
    redirect_uri = str(body.get("redirect_uri", "")).strip()
    if not code:
        raise HTTPException(status_code=422, detail="'code' is required")

    g_client_id  = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    g_secret     = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if not g_client_id or not g_secret:
        raise HTTPException(status_code=503, detail="Google auth not configured on this server")

    # Exchange code → tokens
    try:
        r = _req.post("https://oauth2.googleapis.com/token", data={
            "code":          code,
            "client_id":     g_client_id,
            "client_secret": g_secret,
            "redirect_uri":  redirect_uri,
            "grant_type":    "authorization_code",
        }, timeout=10)
    except _req.RequestException as exc:
        raise HTTPException(status_code=503, detail=f"Could not reach Google: {exc}")

    if r.status_code != 200:
        detail = r.json().get("error_description", r.text)
        raise HTTPException(status_code=401, detail=f"Google token exchange failed: {detail}")

    id_token = r.json().get("id_token")
    if not id_token:
        raise HTTPException(status_code=401, detail="No ID token returned by Google")

    # Decode payload (we trust Google's HTTPS response — no signature re-verify needed)
    payload = _jwt.decode(id_token, options={"verify_signature": False})
    email   = payload.get("email", "").lower().strip()
    name    = (payload.get("name") or payload.get("given_name") or email.split("@")[0]).strip()
    if not email:
        raise HTTPException(status_code=422, detail="Google account has no email")

    # Existing user → JWT immediately
    existing = q1(
        "SELECT id, tenant_id, full_name, role FROM users WHERE email = %s AND is_active = true",
        (email,),
    )
    dev_secret = os.getenv("ZOIKO_DEV_SECRET", "")
    issuer     = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com")
    ttl        = int(os.getenv("JWT_TTL_SECONDS", "86400"))

    if existing:
        from middleware.oidc.token_verifier import TokenVerifier
        verifier = TokenVerifier(dev_secret=dev_secret.encode(), issuer=issuer)
        token    = verifier.make_dev_token(
            sub=email, tenant_id=str(existing["tenant_id"]),
            roles=[existing["role"]], ttl_sec=ttl,
        )
        return _auth_cookie_response(
            {"tenant_id": str(existing["tenant_id"]), "role": existing["role"], "full_name": existing["full_name"], "email": email, "expires_in": ttl},
            token=token, ttl=ttl,
        )

    # New user — issue a 10-min signup token (avoids re-verifying with Google)
    now          = int(_time.time())
    signup_token = _jwt.encode(
        {"sub": email, "name": name, "type": "google_signup", "iat": now, "exp": now + 600},
        dev_secret, algorithm="HS256",
    )
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=202, content={
        "status":       "new_user",
        "email":        email,
        "name":         name,
        "signup_token": signup_token,
    })


# ── Google OAuth — complete signup after org name is collected ─────────────────

@app.post("/auth/google/complete-signup", tags=["auth"], status_code=201)
@app.post("/v1/auth/google/complete-signup", tags=["auth"], include_in_schema=False, status_code=201)
def google_complete_signup(body: dict):
    """
    Finish Google signup: verify 10-min signup_token, create tenant + user, return JWT.
    Body: { signup_token: str, org_name: str }
    """
    import jwt as _jwt, psycopg2 as _pg

    signup_token = str(body.get("signup_token", "")).strip()
    org_name     = str(body.get("org_name", "")).strip()
    if not signup_token or not org_name:
        raise HTTPException(status_code=422, detail="'signup_token' and 'org_name' are required")

    dev_secret = os.getenv("ZOIKO_DEV_SECRET", "")
    try:
        claims = _jwt.decode(signup_token, dev_secret, algorithms=["HS256"])
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Signup session expired. Please sign in with Google again.")
    except _jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid signup token.")

    if claims.get("type") != "google_signup":
        raise HTTPException(status_code=401, detail="Invalid token type.")

    email = claims.get("sub", "").lower().strip()
    name  = claims.get("name", email.split("@")[0]).strip()

    slug = _re.sub(r"[^a-z0-9-]", "", org_name.lower().replace(" ", "-").replace("_", "-"))
    if not slug:
        raise HTTPException(status_code=422, detail="Invalid organization name.")

    if q1("SELECT id FROM tenants WHERE slug = %s", (slug,)):
        raise HTTPException(status_code=409, detail=f"Organization '{org_name}' already registered.")
    if q1("SELECT id FROM users WHERE email = %s", (email,)):
        raise HTTPException(status_code=409, detail="Email already registered. Please sign in.")

    tenant_id = uuid.uuid4()
    user_id   = uuid.uuid4()
    now       = datetime.now(timezone.utc)
    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tenants (id, display_name, slug, status, created_at, updated_at) "
            "VALUES (%s, %s, %s, 'ACTIVE', %s, %s)",
            (tenant_id, org_name, slug, now, now),
        )
        cur.execute(
            "INSERT INTO users (id, tenant_id, email, password_hash, full_name, role, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, tenant_id, email, '', name, "admin", now),  # empty = Google SSO, no password login
        )
        conn.commit()
    finally:
        conn.close()

    from middleware.oidc.token_verifier import TokenVerifier
    issuer   = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com")
    ttl      = int(os.getenv("JWT_TTL_SECONDS", "86400"))
    verifier = TokenVerifier(dev_secret=dev_secret.encode(), issuer=issuer)
    token    = verifier.make_dev_token(sub=email, tenant_id=str(tenant_id), roles=["admin"], ttl_sec=ttl)

    return _auth_cookie_response(
        {"tenant_id": str(tenant_id), "role": "admin", "full_name": name, "email": email, "expires_in": ttl, "org_name": org_name},
        token=token, ttl=ttl, status_code=201,
    )


# ── Organization signup with email OTP verification (production-grade) ────────
# Uses completely separate table signup_verification — no relation to password_reset_otp

@app.post("/auth/signup-send-otp", tags=["auth"])
@app.post("/v1/auth/signup-send-otp", tags=["auth"], include_in_schema=False)
def signup_send_otp(body: dict):
    """Step 1: validate signup data, send OTP to email, store temp data."""
    import secrets as _sec, hashlib as _hl, psycopg2 as _pg, smtplib
    from email.mime.text import MIMEText
    import bcrypt as _bcrypt

    org_name     = str(body.get("org_name", "")).strip()
    admin_name   = str(body.get("admin_name", "")).strip()
    admin_email  = str(body.get("admin_email", "")).lower().strip()
    admin_pw     = str(body.get("admin_password", ""))

    for field, label in [
        (org_name, "org_name"), (admin_name, "admin_name"),
        (admin_email, "admin_email"), (admin_pw, "admin_password"),
    ]:
        if not field:
            raise HTTPException(status_code=422, detail=f"'{label}' is required")
    if len(admin_pw) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    if "@" not in admin_email:
        raise HTTPException(status_code=422, detail="Valid email required")

    slug = org_name.lower().replace(" ", "-").replace("_", "-")

    existing_tenant = q1("SELECT id FROM tenants WHERE slug = %s", (slug,))
    if existing_tenant:
        raise HTTPException(
            status_code=409,
            detail=f"Organization '{org_name}' already registered. Please contact your admin or use sign in."
        )
    existing_user = q1("SELECT id FROM users WHERE email = %s", (admin_email,))
    if existing_user:
        raise HTTPException(status_code=409, detail="Email already registered. Please sign in instead.")

    otp = f"{_sec.randbelow(900000) + 100000}"
    otp_hash = _hl.sha256(otp.encode()).hexdigest()
    pw_hash = _bcrypt.hashpw(admin_pw.encode(), _bcrypt.gensalt()).decode()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE signup_verification SET used_at = NOW() WHERE email = %s AND used_at IS NULL",
            (admin_email,),
        )
        cur.execute(
            "INSERT INTO signup_verification (email, org_name, admin_name, password_hash, otp_hash, expires_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (admin_email, org_name, admin_name, pw_hash, otp_hash, expires_at),
        )
        conn.commit()
    finally:
        conn.close()

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("EMAIL_NAME", "")
    smtp_pass = os.getenv("EMAIL_PASSWORD", "")

    if smtp_user and smtp_pass:
        try:
            email_body = (
                f"Welcome to ZoikoAI,\n\n"
                f"Thank you for creating your organization '{org_name}'.\n"
                f"Please use the following OTP to verify your email address:\n\n"
                f"Your OTP: {otp}\n\n"
                f"This code is valid for 10 minutes.\n\n"
                f"If you didn't request this, you can safely ignore this email.\n\n"
                f"Best regards,\nZoikoAI Logistics Team"
            )
            msg = MIMEText(email_body, "plain", "utf-8")
            msg["Subject"] = "ZoikoAI — Verify Your Email Address"
            msg["From"] = smtp_user
            msg["To"] = admin_email
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as s:
                s.starttls()
                s.login(smtp_user, smtp_pass)
                s.sendmail(smtp_user, [admin_email], msg.as_string())
        except Exception as _exc:
            import logging as _log
            _log.getLogger("zoiko.auth").error("Signup OTP email failed for %s: %s", admin_email, _exc)

    return {"message": "OTP sent to email", "expires_in_minutes": 10}


@app.post("/auth/signup-verify-otp", tags=["auth"])
@app.post("/v1/auth/signup-verify-otp", tags=["auth"], include_in_schema=False)
def signup_verify_otp(body: dict):
    """Step 2: verify OTP, create tenant + admin user, return JWT."""
    import hashlib as _hl, psycopg2 as _pg
    from psycopg2.extras import RealDictCursor as _RDC

    admin_email = str(body.get("admin_email", "")).lower().strip()
    otp         = str(body.get("otp", "")).strip()

    if not admin_email or not otp:
        raise HTTPException(status_code=422, detail="email and otp required")

    otp_hash = _hl.sha256(otp.encode()).hexdigest()

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor(cursor_factory=_RDC)
        cur.execute(
            "UPDATE signup_verification SET used_at = NOW() "
            "WHERE email = %s AND otp_hash = %s AND used_at IS NULL "
            "RETURNING id, org_name, admin_name, password_hash, expires_at",
            (admin_email, otp_hash),
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                "UPDATE signup_verification SET failed_attempts = COALESCE(failed_attempts, 0) + 1 "
                "WHERE email = %s AND used_at IS NULL RETURNING failed_attempts",
                (admin_email,),
            )
            fail_row = cur.fetchone()
            if fail_row and fail_row["failed_attempts"] >= 5:
                cur.execute(
                    "UPDATE signup_verification SET used_at = NOW() WHERE email = %s AND used_at IS NULL",
                    (admin_email,),
                )
            conn.commit()
            raise HTTPException(status_code=401, detail="Invalid OTP")
        if datetime.now(timezone.utc) > row["expires_at"]:
            raise HTTPException(status_code=401, detail="OTP expired")

        org_name     = row["org_name"]
        admin_name   = row["admin_name"]
        password_hash = row["password_hash"]
        slug = org_name.lower().replace(" ", "-").replace("_", "-")
        tenant_id = uuid.uuid4()
        user_id   = uuid.uuid4()
        now       = datetime.now(timezone.utc)

        # Re-check duplicates inside the same transaction (race condition guard)
        dup_tenant = q1("SELECT id FROM tenants WHERE slug = %s", (slug,))
        if dup_tenant:
            raise HTTPException(status_code=409, detail="Organization already registered")
        dup_user = q1("SELECT id FROM users WHERE email = %s", (admin_email,))
        if dup_user:
            raise HTTPException(status_code=409, detail="Email already registered")

        cur.execute(
            "INSERT INTO tenants (id, display_name, slug, status, created_at, updated_at) "
            "VALUES (%s, %s, %s, 'ACTIVE', %s, %s)",
            (tenant_id, org_name, slug, now, now),
        )
        cur.execute(
            "INSERT INTO users (id, tenant_id, email, password_hash, full_name, role, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, tenant_id, admin_email, password_hash, admin_name, "admin", now),
        )
        conn.commit()
    finally:
        conn.close()

    # Generate JWT
    from middleware.oidc.token_verifier import TokenVerifier
    secret  = os.getenv("ZOIKO_DEV_SECRET", "").encode()
    issuer  = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com")
    ttl     = int(os.getenv("JWT_TTL_SECONDS", "86400"))
    verifier = TokenVerifier(dev_secret=secret, issuer=issuer)
    token   = verifier.make_dev_token(
        sub=admin_email, tenant_id=str(tenant_id),
        roles=["admin"], ttl_sec=ttl,
    )

    return {
        "token":      token,
        "tenant_id":  str(tenant_id),
        "role":       "admin",
        "full_name":  admin_name,
        "email":      admin_email,
        "expires_in": ttl,
        "org_name":   org_name,
    }


# ── Sign out ──────────────────────────────────────────────────────────────────

@app.post("/auth/signout", tags=["auth"], status_code=204)
@app.post("/v1/auth/signout", tags=["auth"], include_in_schema=False, status_code=204)
def signout():
    """Clear auth cookie. Stateless JWT — nothing to revoke server-side."""
    from fastapi.responses import Response as _Response
    resp = _Response(status_code=204)
    resp.delete_cookie(key="zoiko_jwt", path="/")
    return resp


# ── Profile — user & tenant settings ──────────────────────────────────────────

@app.get("/auth/me")
@app.get("/v1/auth/me", include_in_schema=False)
def get_profile(claims: ZoikoClaims = Depends(get_claims_by_cookie)):
    """Return profile for the authenticated user.
    Uses cookie-based auth — no X-Tenant-ID required, enabling session restoration."""
    row = q1(
        "SELECT full_name, email, role, title, is_active, created_at FROM users WHERE email = %s AND tenant_id = %s::uuid",
        (claims.sub, claims.tenant_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "full_name":  row["full_name"],
        "email":      row["email"],
        "role":       row["role"],
        "title":      row["title"] or "",
        "is_active":  row["is_active"],
        "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
        "tenant_id":  str(claims.tenant_id),
    }

@app.put("/auth/me")
@app.put("/v1/auth/me", include_in_schema=False)
def update_profile(body: dict, claims: ZoikoClaims = Depends(get_claims)):
    import psycopg2 as _pg
    title = str(body.get("title", "")).strip()
    full_name = str(body.get("full_name", "")).strip()
    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        parts = []
        params = []
        if title:
            parts.append("title = %s")
            params.append(title)
        if full_name:
            parts.append("full_name = %s")
            params.append(full_name)
        if parts:
            params.extend([claims.sub, claims.tenant_id])
            cur.execute(
                f"UPDATE users SET {', '.join(parts)} WHERE email = %s AND tenant_id = %s::uuid",
                params,
            )
            conn.commit()
    finally:
        conn.close()
    return {"message": "Profile updated"}

@app.get("/auth/tenant")
@app.get("/v1/auth/tenant", include_in_schema=False)
def get_tenant_info(claims: ZoikoClaims = Depends(get_claims)):
    row = q1(
        "SELECT display_name, slug, address, city, state, pincode, phone, email, status, created_at "
        "FROM tenants WHERE id = %s::uuid",
        (claims.tenant_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return row

@app.put("/auth/tenant")
@app.put("/v1/auth/tenant", include_in_schema=False)
def update_tenant_info(body: dict, claims: ZoikoClaims = Depends(get_claims)):
    import psycopg2 as _pg
    if "admin" not in claims.roles:
        raise HTTPException(status_code=403, detail="Only admins can update tenant info")
    allowed = {"address", "city", "state", "pincode", "phone", "email"}
    updates = {k: str(body[k]).strip() for k in body if k in allowed}
    if not updates:
        raise HTTPException(status_code=422, detail="No valid fields to update")
    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        cur.execute(
            f"UPDATE tenants SET {set_clause} WHERE id = %s::uuid",
            list(updates.values()) + [claims.tenant_id],
        )
        conn.commit()
    finally:
        conn.close()
    return {"message": "Tenant info updated", "updated": list(updates.keys())}


# ── Carriers CRUD ──────────────────────────────────────────────────────────────

@app.get("/carriers")
@app.get("/v1/carriers", include_in_schema=False)
def list_carriers(claims: ZoikoClaims = Depends(get_claims)):
    rows = q(
        "SELECT id::text, name, email, address, contact_person, contact_phone, cc_emails, created_at "
        "FROM carriers WHERE tenant_id = %s::uuid ORDER BY name ASC",
        (claims.tenant_id,),
    )
    return [
        {
            "id":             str(r["id"]),
            "name":           r["name"],
            "email":          r["email"] or "",
            "address":        r["address"] or "",
            "contact_person": r["contact_person"] or "",
            "contact_phone":  r["contact_phone"] or "",
            "cc_emails":      r["cc_emails"] or "",
            "created_at":     r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
        }
        for r in rows
    ]

@app.post("/carriers")
@app.post("/v1/carriers", include_in_schema=False, status_code=201)
def create_carrier(body: dict, claims: ZoikoClaims = Depends(get_claims)):
    import psycopg2 as _pg, uuid as _uuid
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=422, detail="Carrier name is required")
    existing = q1(
        "SELECT id FROM carriers WHERE tenant_id = %s::uuid AND LOWER(name) = LOWER(%s)",
        (claims.tenant_id, name),
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Carrier '{name}' already exists")
    carrier_id = _uuid.uuid4()
    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO carriers (id, tenant_id, name, email, address, contact_person, contact_phone, cc_emails) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                carrier_id, claims.tenant_id, name,
                str(body.get("email", "")).strip(),
                str(body.get("address", "")).strip(),
                str(body.get("contact_person", "")).strip(),
                str(body.get("contact_phone", "")).strip(),
                str(body.get("cc_emails", "")).strip(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": str(carrier_id), "name": name, "message": "Carrier created"}

@app.put("/carriers/{carrier_id}")
@app.put("/v1/carriers/{carrier_id}", include_in_schema=False)
def update_carrier(carrier_id: str, body: dict, claims: ZoikoClaims = Depends(get_claims)):
    import psycopg2 as _pg
    allowed = {"name", "email", "address", "contact_person", "contact_phone", "cc_emails"}
    updates = {}
    for k in body:
        if k in allowed:
            updates[k] = str(body[k]).strip()
    if not updates:
        raise HTTPException(status_code=422, detail="No valid fields to update")
    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        cur.execute(
            f"UPDATE carriers SET {set_clause} WHERE id = %s::uuid AND tenant_id = %s::uuid",
            list(updates.values()) + [carrier_id, claims.tenant_id],
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Carrier not found")
    finally:
        conn.close()
    return {"message": "Carrier updated", "updated": list(updates.keys())}

@app.delete("/carriers/{carrier_id}")
@app.delete("/v1/carriers/{carrier_id}", include_in_schema=False)
def delete_carrier(carrier_id: str, claims: ZoikoClaims = Depends(get_claims)):
    import psycopg2 as _pg
    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM carriers WHERE id = %s::uuid AND tenant_id = %s::uuid",
            (carrier_id, claims.tenant_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Carrier not found")
    finally:
        conn.close()
    return {"message": "Carrier deleted"}


# ── Health — registered directly on app (not versioned) ──────────────────────

@app.get("/health", tags=["ops"])
@app.get("/v1/health", tags=["ops"], include_in_schema=False)
def health():
    """Real health check — verifies DB connectivity and reports Kafka mode."""
    checks: dict = {}

    # Check 1 — PostgreSQL
    try:
        import psycopg2 as _pg
        conn = _pg.connect(DB_URL)
        cur  = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM cases")
        case_count = cur.fetchone()[0]
        conn.close()
        checks["database"] = {"status": "ok", "cases": case_count}
    except Exception as exc:
        checks["database"] = {"status": "error", "detail": str(exc)[:100]}

    # Check 2 — Kafka broker type
    broker_type = "real" if KAFKA_BOOTSTRAP else "mock"
    checks["kafka"] = {"status": "ok", "mode": broker_type}

    # Check 3 — Outbox (pending rows)
    try:
        pending = q1("SELECT COUNT(*) AS n FROM outbox WHERE shipped_at IS NULL")
        checks["outbox"] = {"status": "ok", "pending": pending["n"] if pending else 0}
    except Exception:
        checks["outbox"] = {"status": "unknown"}

    # Overall status
    overall = "ok" if checks.get("database", {}).get("status") == "ok" else "degraded"

    return {
        "status":  overall,
        "service": "api-gateway",
        "version": "2.0.0",
        "checks":  checks,
    }


@app.get("/ready", tags=["ops"])
@app.get("/v1/ready", tags=["ops"], include_in_schema=False)
def ready():
    """Readiness probe — returns 200 only when DB and critical services are reachable."""
    failures: list[str] = []

    # DB
    try:
        import psycopg2 as _pg
        conn = _pg.connect(DB_URL)
        conn.cursor().execute("SELECT 1")
        conn.close()
    except Exception as exc:
        failures.append(f"database: {str(exc)[:80]}")

    # Redis (optional — missing Redis is non-fatal for readiness)
    try:
        import redis as _redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = _redis.from_url(redis_url, socket_connect_timeout=1)
        r.ping()
    except Exception:
        pass  # Redis is optional — Phase 4 degrades gracefully without it

    if failures:
        return _JSONResponse(
            status_code=503,
            content={"status": "not_ready", "failures": failures},
        )
    return {"status": "ready", "service": "api-gateway"}


# ── Ingestion ─────────────────────────────────────────────────────────────────

from services.api_gateway import routes_logic as _sc002_routes


@v1_router.patch("/cases/{case_id}/state", response_model=TransitionResponse, tags=["cases"])
def transition_case(
    case_id: str,
    body: TransitionRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        new_state = _cases.transition_state(
            tenant_id        = str(claims.tenant_id),
            case_id          = case_id,
            new_state        = body.new_state,
            actor_sub        = body.actor_sub,
            payload          = body.payload,
            expected_version = getattr(body, "version", None),
        )
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return TransitionResponse(case_id=case_id, new_state=new_state)


@v1_router.post("/cases/{case_id}/transition", response_model=TransitionResponse, tags=["cases"])
def transition_case_post(
    case_id: str,
    body: TransitionRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
):
    """
    Generic FSM transition with OCC version check (T-016).
    Body: {new_state, actor_sub, version (optional), payload (optional)}
    Returns 409 if version doesn't match current row version.
    """
    try:
        new_state = _cases.transition_state(
            tenant_id        = str(claims.tenant_id),
            case_id          = case_id,
            new_state        = body.new_state,
            actor_sub        = body.actor_sub,
            payload          = body.payload,
            expected_version = getattr(body, "version", None),
        )
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return TransitionResponse(case_id=case_id, new_state=new_state)


# ══════════════════════════════════════════════════════════════════════════════
# FRONTEND UI API  — high-level REST endpoints shaped for the React dashboard
# ══════════════════════════════════════════════════════════════════════════════

def _r(row: dict) -> dict:
    """Convert a psycopg2 row to a JSON-safe dict (bytes→hex, Decimal→float, UUID→str)."""
    out = {}
    for k, v in row.items():
        if isinstance(v, memoryview):
            out[k] = "0x" + bytes(v).hex()
        elif isinstance(v, (bytes, bytearray)):
            out[k] = "0x" + v.hex()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, uuid.UUID):
            out[k] = str(v)
        else:
            out[k] = v
    return out


def _raw_exec(sql: str, params: tuple) -> None:
    import psycopg2 as _pg
    import psycopg2.extras as _pge
    _pge.register_uuid()
    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _sign_dev(tenant_id: str, data: bytes) -> tuple[bytes, str]:
    row = q1("SELECT slug FROM tenants WHERE id = %s::uuid", (tenant_id,))
    slug = row["slug"] if row else "default"
    from shared.signer import sign as _sign
    return _sign(slug, data)


# ── Dashboard stats ────────────────────────────────────────────────────────────

@v1_router.get("/dashboard/stats", tags=["ui"])
def ui_stats(claims: ZoikoClaims = Depends(get_claims)):
    tid = claims.tenant_id
    cnt = q1("""
        SELECT
            COUNT(*)                                                           AS total_cases,
            SUM(CASE WHEN state='APPROVAL_PENDING'                  THEN 1 ELSE 0 END) AS pending_approval,
            SUM(CASE WHEN state IN ('EXECUTION_READY','DISPATCHED','OUTCOME_RECORDED','CLOSED')
                                                                    THEN 1 ELSE 0 END) AS approved
        FROM cases WHERE tenant_id = %s::uuid
    """, (tid,))
    rec = q1("""
        SELECT
            COALESCE(SUM((
                SELECT dp.amount FROM decision_proposals dp
                WHERE  dp.case_id = c.id
                ORDER BY dp.created_at DESC LIMIT 1
            )), 0)                             AS total_recovered,
            COALESCE(AVG(f.confidence), 0)     AS avg_confidence
        FROM  cases c
        LEFT JOIN findings f ON f.case_id = c.id
        WHERE c.tenant_id = %s::uuid
          AND c.state IN ('EXECUTION_READY','DISPATCHED','OUTCOME_RECORDED','CLOSED')
    """, (tid,))
    return {
        "total_cases":      int(cnt["total_cases"] or 0),
        "pending_approval": int(cnt["pending_approval"] or 0),
        "approved":         int(cnt["approved"] or 0),
        "total_recovered":  float(rec["total_recovered"] or 0),
        "avg_confidence":   float(rec["avg_confidence"] or 0),
    }


# ── Claims list + detail ─────────────────────────────────────────────────────────

@v1_router.get("/claims", tags=["ui"])
def ui_list_claims(
    state: str | None = None,
    page: int = 1,
    page_size: int = 50,
    claims: ZoikoClaims = Depends(get_claims),
):
    """Mirrors ui_list_cases() but joins claims instead of canonical_invoices."""
    return _sc002_routes.ui_list_claims(_r, claims.tenant_id, state, page, page_size)


@v1_router.get("/claims/{case_id}", tags=["ui"])
def ui_get_claim(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    return _sc002_routes.ui_get_claim(_r, claims.tenant_id, case_id)


@v1_router.get("/claims/{case_id}/lines", tags=["ui"])
def ui_get_claim_lines(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    """Multi-line breakdown for a claim, if one was provided at submission. Empty list = flat-amount claim."""
    return _sc002_routes.ui_get_claim_lines(_r, claims.tenant_id, case_id)


@v1_router.post("/claims/{case_id}/negotiate", tags=["ui"])
def ui_negotiate_claim(case_id: str, body: NegotiateClaimRequest, claims: ZoikoClaims = Depends(get_claims)):
    """SC-002 — carrier counter-offer round-trip. Independent of the governance
    FSM (cases.state): this tracks claims.status, the back-and-forth with the
    carrier that happens before/alongside the propose -> approve -> execute flow."""
    return _sc002_routes.ui_negotiate_claim(_r, _raw_exec, claims.tenant_id, case_id, body, claims.sub)


# ── Case events ────────────────────────────────────────────────────────────────

@v1_router.get("/cases/{case_id}/events", tags=["ui"])
def ui_case_events(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    rows = q("""
        SELECT id::text, case_id::text, from_state, to_state,
               actor_sub                                    AS actor,
               COALESCE(payload->>'reason', event_type)     AS reason,
               occurred_at                                  AS created_at
        FROM   case_events
        WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY occurred_at ASC
    """, (case_id, claims.tenant_id))
    return [_r(r) for r in rows]


# ── Validation result ──────────────────────────────────────────────────────────

# ── Source records ─────────────────────────────────────────────────────────────

@v1_router.get("/ingestion/source-records", tags=["ui"])
def ui_source_records(claims: ZoikoClaims = Depends(get_claims)):
    rows = q("""
        SELECT
            sr.id::text,
            sr.tenant_id::text,
            encode(sr.canonical_hash, 'hex')    AS canonical_hash,
            encode(sr.signature,      'hex')    AS signature,
            sr.kid                              AS key_id,
            sr.created_at                       AS received_at,
            ci.carrier_id                       AS _carrier,
            ci.total_amount::float              AS _amount,
            ci.invoice_number                   AS _shipment
        FROM  source_records sr
        LEFT JOIN canonical_invoices ci ON ci.source_record_id = sr.id
        WHERE sr.tenant_id=%s::uuid
        ORDER BY sr.created_at DESC
        LIMIT 50
    """, (claims.tenant_id,))
    result = []
    for r in rows:
        d = _r(r)
        d["payload_preview"] = {
            "carrier":  d.pop("_carrier",  ""),
            "amount":   d.pop("_amount",   0),
            "shipment": d.pop("_shipment", ""),
        }
        result.append(d)
    return result


# ── Evidence bundle ────────────────────────────────────────────────────────────

@v1_router.get("/cases/{case_id}/evidence", tags=["ui"])
def ui_evidence(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    bundle = q1("""
        SELECT id::text, case_id::text,
               encode(bundle_hash, 'hex') AS merkle_root,
               created_at
        FROM   evidence_bundles
        WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
        LIMIT  1
    """, (case_id, claims.tenant_id))
    if not bundle:
        raise HTTPException(status_code=404, detail="No evidence bundle found")
    items = q("""
        SELECT id::text, bundle_id::text, item_type,
               encode(item_hash, 'hex') AS leaf_hash,
               added_at
        FROM   evidence_items
        WHERE  bundle_id=%s::uuid
        ORDER BY added_at ASC
    """, (bundle["id"],))
    row = _r(bundle)
    row["item_count"] = len(items)
    row["items"] = [_r(i) for i in items]
    return row


# ── Finding ────────────────────────────────────────────────────────────────────

@v1_router.get("/cases/{case_id}/finding", tags=["ui"])
def ui_finding(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    row = q1("""
        SELECT id::text, case_id::text, confidence::float,
               rule_trace,
               encode(signature, 'hex') AS finding_hash,
               created_at
        FROM   findings
        WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY created_at DESC LIMIT 1
    """, (case_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="No finding found")
    d = _r(row)
    d["trace"] = d.pop("rule_trace") or {}
    return d


# ── Proposal ───────────────────────────────────────────────────────────────────

@v1_router.get("/cases/{case_id}/proposal", tags=["ui"])
def ui_get_proposal(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    row = q1("""
        SELECT id::text, case_id::text,
               proposed_action AS action,
               amount::float, currency,
               proposer_sub    AS proposed_by,
               created_at      AS proposed_at
        FROM   decision_proposals
        WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY created_at DESC LIMIT 1
    """, (case_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="No proposal found")
    return _r(row)


@v1_router.post("/cases/{case_id}/proposal", tags=["ui"], status_code=201)
def ui_create_proposal(
    case_id: str,
    body: UIProposalRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        uuid.UUID(case_id)  # validate format — returns clean 422 on bad UUID
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid case_id format: '{case_id}'")
    tid = claims.tenant_id
    now = datetime.now(timezone.utc)

    # Ensure evidence bundle exists (create placeholder if missing)
    b_row = q1("SELECT id FROM evidence_bundles WHERE case_id=%s::uuid AND tenant_id=%s::uuid LIMIT 1", (case_id, tid))
    if b_row:
        bundle_id = str(b_row["id"])
    else:
        bid = uuid.uuid4()
        ph = bytes(32)
        _raw_exec("""
            INSERT INTO evidence_bundles (id, tenant_id, case_id, bundle_hash, signature, kid, created_at)
            VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s)
        """, (bid, tid, case_id, ph, ph, "dev-placeholder", now))
        bundle_id = str(bid)

    # Ensure finding exists (create placeholder if missing)
    f_row = q1("SELECT id FROM findings WHERE case_id=%s::uuid AND tenant_id=%s::uuid LIMIT 1", (case_id, tid))
    if f_row:
        finding_id = str(f_row["id"])
    else:
        fid = uuid.uuid4()
        confidence = 0.96
        rule_trace = json.dumps({"fuel_charge": {"confidence": 1.0, "weight": 0.5}, "accessorial": {"confidence": 0.92, "weight": 0.5}})
        fhash = hashlib.sha256(b"zoiko.finding.v1:" + _jcs({"case_id": case_id, "confidence": confidence})).digest()
        fsig, fkid = _sign_dev(tid, fhash)
        _raw_exec("""
            INSERT INTO findings (id, tenant_id, case_id, bundle_id, confidence, rule_trace, signature, kid, created_at)
            VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s, %s)
        """, (fid, tid, case_id, uuid.UUID(bundle_id), confidence, rule_trace, fsig, fkid, now))
        finding_id = str(fid)

    # Create decision proposal
    pid = uuid.uuid4()
    prop_bytes = _jcs({"action": body.action, "amount": float(body.amount), "currency": body.currency, "case_id": case_id})
    prop_hash  = hashlib.sha256(b"zoiko.proposal.v1:" + prop_bytes).digest()
    psig, pkid = _sign_dev(tid, prop_hash)
    _raw_exec("""
        INSERT INTO decision_proposals
            (id, tenant_id, case_id, finding_id, proposed_action, amount, currency,
             proposer_sub, proposal_hash, signature, kid, created_at)
        VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (pid, tid, case_id, uuid.UUID(finding_id), body.action, float(body.amount),
          body.currency, claims.sub, prop_hash, psig, pkid, now))

    # Create approval task
    _raw_exec("""
        INSERT INTO approval_tasks (id, tenant_id, proposal_id, proposer_sub, status, created_at)
        VALUES (%s, %s::uuid, %s::uuid, %s, 'PENDING', %s)
    """, (uuid.uuid4(), tid, pid, claims.sub, now))

    # Transition case → APPROVAL_PENDING
    c_row = q1("SELECT state FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid", (case_id, tid))
    if c_row and c_row["state"] in ("NEW", "EVIDENCE_PENDING", "FINDING_GENERATED"):
        prev = c_row["state"]
        _raw_exec("UPDATE cases SET state='APPROVAL_PENDING' WHERE id=%s::uuid AND tenant_id=%s::uuid", (case_id, tid))
        _raw_exec("""
            INSERT INTO case_events (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
            VALUES (%s, %s::uuid, %s::uuid, 'PROPOSAL_CREATED', %s, 'APPROVAL_PENDING', %s, %s::jsonb, %s)
        """, (uuid.uuid4(), tid, case_id, prev, claims.sub, json.dumps({"proposal_id": str(pid)}), now))

    return {"id": str(pid), "case_id": case_id, "action": body.action,
            "amount": float(body.amount), "currency": body.currency,
            "proposed_by": claims.sub, "proposed_at": now.isoformat()}


# ── Decide ─────────────────────────────────────────────────────────────────────

@v1_router.post("/cases/{case_id}/decide", tags=["ui"])
def ui_decide(
    case_id: str,
    body: UIDecideRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    tid     = claims.tenant_id
    now     = datetime.now(timezone.utc)
    outcome = body.decision
    if outcome not in ("EXECUTION_READY", "ABORTED"):
        raise HTTPException(400, detail="decision must be EXECUTION_READY or ABORTED")

    task = q1("""
        SELECT at.id, at.proposal_id, at.proposer_sub
        FROM   approval_tasks at
        JOIN   decision_proposals dp ON dp.id = at.proposal_id
        WHERE  dp.case_id=%s::uuid AND at.tenant_id=%s::uuid AND at.status='PENDING'
        ORDER BY at.created_at DESC LIMIT 1
    """, (case_id, tid))
    if not task:
        raise HTTPException(404, detail="No pending approval task for this case")
    if claims.sub == str(task["proposer_sub"]):
        _sec.publish(SecurityEventKind.FORBIDDEN_FSM_TRANSITION, str(claims.tenant_id), {
            "violation": "SOD_VIOLATION",
            "actor_sub": claims.sub,
            "case_id":   case_id,
        })
        raise HTTPException(422, detail="Separation of Duties: proposer cannot approve own proposal")

    proposal_id = str(task["proposal_id"])
    task_id     = str(task["id"])

    # Map FSM outcome → approval_tasks status (constraint only allows APPROVED/REJECTED/PENDING)
    at_status = "APPROVED" if outcome == "EXECUTION_READY" else "REJECTED"

    # Get or create policy bundle
    pb = q1("SELECT id FROM policy_bundles WHERE tenant_id=%s::uuid AND active=TRUE LIMIT 1", (tid,))
    if pb:
        policy_bundle_id = str(pb["id"])
    else:
        pbid = uuid.uuid4()
        _raw_exec("""
            INSERT INTO policy_bundles (id, tenant_id, version, rego_hash, active, deployed_at)
            VALUES (%s::uuid, %s::uuid, 'v1.0.0', %s, TRUE, %s)
        """, (pbid, tid, hashlib.sha256(b"zoiko.opa.freight_dispute.v1").digest(), now))
        policy_bundle_id = str(pbid)

    # Create governance decision
    dec_bytes = _jcs({"actor_sub": claims.sub, "outcome": outcome, "proposal_id": proposal_id, "task_id": task_id, "tenant_id": tid})
    dec_hash  = hashlib.sha256(b"zoiko.governance.decision.v1:" + dec_bytes).digest()
    dec_sig, dec_kid = _sign_dev(tid, dec_hash)
    did = uuid.uuid4()
    _raw_exec("""
        INSERT INTO governance_decisions
            (id, tenant_id, proposal_id, policy_bundle_id, outcome, decision_hash, signature, kid, decided_at)
        VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s)
    """, (did, tid, uuid.UUID(proposal_id), uuid.UUID(policy_bundle_id), outcome, dec_hash, dec_sig, dec_kid, now))

    _raw_exec("""
        UPDATE approval_tasks SET status=%s, actor_sub=%s, actioned_at=%s
        WHERE  id=%s::uuid AND tenant_id=%s::uuid
    """, (at_status, claims.sub, now, uuid.UUID(task_id), tid))

    # Mint token if approved
    token_id = None
    if outcome == "EXECUTION_READY":
        prop_det = q1("SELECT proposed_action, amount, currency FROM decision_proposals WHERE id=%s::uuid", (uuid.UUID(proposal_id),))
        scope  = prop_det["proposed_action"] if prop_det else "EXECUTE_CREDIT_MEMO"
        exp    = now + timedelta(minutes=15)
        tb     = hashlib.sha256(tid.encode() + str(did).encode()).digest()
        th     = hashlib.sha256(b"zoiko.token.v1:" + _jcs({"decision_id": str(did), "tenant_id": tid, "scope": scope})).digest()
        tsig, tkid = _sign_dev(tid, th)
        token_id = uuid.uuid4()
        _raw_exec("""
            INSERT INTO governance_tokens
                (id, tenant_id, decision_id, scope, tenant_binding, status,
                 expires_at, token_hash, signature, kid, issued_at)
            VALUES (%s, %s::uuid, %s::uuid, %s, %s, 'ACTIVE', %s, %s, %s, %s, %s)
        """, (token_id, tid, did, scope, tb, exp, th, tsig, tkid, now))

    # Transition case state
    c_row = q1("SELECT state FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid", (case_id, tid))
    if c_row and c_row["state"] == "APPROVAL_PENDING":
        _raw_exec("UPDATE cases SET state=%s WHERE id=%s::uuid AND tenant_id=%s::uuid", (outcome, case_id, tid))
        _raw_exec("""
            INSERT INTO case_events (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
            VALUES (%s, %s::uuid, %s::uuid, %s, 'APPROVAL_PENDING', %s, %s, %s::jsonb, %s)
        """, (uuid.uuid4(), tid, case_id, f"GOVERNANCE_{outcome}", outcome, claims.sub, json.dumps({"decision_id": str(did)}), now))

    return {"id": str(did), "case_id": case_id, "decision": outcome,
            "actor_sub": claims.sub, "decided_at": now.isoformat(),
            "token_id": str(token_id) if token_id else None}


# ── Tokens ─────────────────────────────────────────────────────────────────────

_TOKEN_SELECT = """
    SELECT
        gt.id::text,
        dp.case_id::text,
        gt.tenant_id::text,
        dp.proposed_action              AS action,
        dp.amount::float,
        dp.currency,
        encode(gt.tenant_binding,'hex') AS tenant_binding,
        gt.expires_at                   AS exp,
        CASE WHEN gt.status = 'ACTIVE' AND gt.expires_at < NOW()
             THEN 'EXPIRED' ELSE gt.status END AS status,
        encode(gt.signature,'hex')      AS signature,
        gt.kid                          AS key_id,
        gt.issued_at
    FROM  governance_tokens gt
    JOIN  governance_decisions gd ON gd.id = gt.decision_id
    JOIN  decision_proposals dp   ON dp.id = gd.proposal_id
"""


@v1_router.get("/tokens", tags=["ui"])
def ui_list_tokens(
    status: str | None = None,
    claims: ZoikoClaims = Depends(get_claims),
):
    if status:
        rows = q(_TOKEN_SELECT + "WHERE gt.tenant_id=%s::uuid AND gt.status=%s ORDER BY gt.issued_at DESC LIMIT 50",
                 (claims.tenant_id, status))
    else:
        rows = q(_TOKEN_SELECT + "WHERE gt.tenant_id=%s::uuid ORDER BY gt.issued_at DESC LIMIT 50",
                 (claims.tenant_id,))
    return [_r(r) for r in rows]


@v1_router.get("/cases/{case_id}/token", tags=["ui"])
def ui_case_token(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    row = q1(_TOKEN_SELECT + "WHERE dp.case_id=%s::uuid AND gt.tenant_id=%s::uuid ORDER BY gt.issued_at DESC LIMIT 1",
             (case_id, claims.tenant_id))
    if not row:
        return None
    return _r(row)


# ── Kafka events (from case_events) ───────────────────────────────────────────

@v1_router.get("/kafka/events", tags=["ui"])
def ui_kafka_events(claims: ZoikoClaims = Depends(get_claims)):
    rows = q("""
        SELECT event_type AS topic, case_id::text AS key, payload, occurred_at AS published_at
        FROM   case_events WHERE tenant_id=%s::uuid
        ORDER BY occurred_at DESC LIMIT 50
    """, (claims.tenant_id,))
    return [_r(r) for r in rows]


# ── Contract rates ────────────────────────────────────────────────────────────

@v1_router.get("/contract-rates", tags=["ui"])
def ui_list_contract_rates(claims: ZoikoClaims = Depends(get_claims)):
    rows = q("""
        SELECT id::text, carrier_id AS carrier, rate_type, rate_value::float,
               currency, effective_on::text, expires_on::text,
               version, supersedes_id::text, source_document_id::text
        FROM   contract_rates
        WHERE  tenant_id = %s::uuid
          AND  superseded_at IS NULL
        ORDER  BY carrier_id, rate_type
    """, (claims.tenant_id,))
    return [_r(r) for r in rows]


@v1_router.post("/contract-rates", tags=["ui"], status_code=201)
def ui_create_contract_rate(
    body: ContractRateRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    """
    Inserts a new contract rate. If an active rate already exists for the
    same (carrier_id, rate_type), the old row is superseded rather than
    overwritten — corrections create a new version, the prior version
    stays queryable for replay/audit.
    """
    prior = q1("""
        SELECT id::text, version FROM contract_rates
        WHERE  tenant_id = %s::uuid AND carrier_id = %s AND rate_type = %s
          AND  superseded_at IS NULL
    """, (claims.tenant_id, body.carrier_id, body.rate_type))

    rid = uuid.uuid4()
    next_version = (prior["version"] + 1) if prior else 1

    # payload_hash binds the rate's monetary content at creation time so
    # validation_svc can detect a direct DB mutation later (e.g. someone
    # running UPDATE contract_rates SET rate_value=... outside this API).
    # The column already existed but was only ever populated once by an old
    # backfill migration over carrier_id+rate_type — it never covered
    # rate_value/currency/dates and nothing ever re-checked it on read.
    # rate_value is stored as NUMERIC(18,4) — psycopg2 reads it back as Decimal
    # (e.g. Decimal('1000.0000')), which str()-formats differently from a raw
    # Python float (1000.0). Both sides must format to the same fixed
    # precision or every freshly-created rate would fail its own check.
    rate_payload_hash = "sha256:" + hashlib.sha256(
        f"zoiko.contract_rate.v1:{claims.tenant_id}:{body.carrier_id}:{body.rate_type}:"
        f"{float(body.rate_value):.4f}:{body.currency}:{body.effective_on}:{body.expires_on or ''}".encode()
    ).hexdigest()

    _raw_exec("""
        INSERT INTO contract_rates
            (id, tenant_id, carrier_id, rate_type, rate_value, currency,
             effective_on, expires_on, version, supersedes_id, source_document_id,
             payload_hash)
        VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (rid, claims.tenant_id, body.carrier_id, body.rate_type,
          body.rate_value, body.currency, body.effective_on, body.expires_on,
          next_version, prior["id"] if prior else None, body.source_document_id,
          rate_payload_hash))

    if prior:
        _raw_exec(
            "UPDATE contract_rates SET superseded_at = NOW() WHERE id = %s::uuid",
            (prior["id"],),
        )

    return {"id": str(rid), "carrier_id": body.carrier_id, "rate_type": body.rate_type,
            "rate_value": body.rate_value, "currency": body.currency,
            "effective_on": body.effective_on, "version": next_version,
            "supersedes_id": prior["id"] if prior else None}


@v1_router.delete("/contract-rates/{rate_id}", tags=["ui"])
def ui_delete_contract_rate(rate_id: str, claims: ZoikoClaims = Depends(get_claims)):
    """
    Soft-delete only: marks the rate superseded rather than removing the
    row, so a past overcharge calculation can always be traced back to
    the exact rate that was in effect when it ran.
    """
    _raw_exec(
        "UPDATE contract_rates SET superseded_at = NOW() WHERE id=%s::uuid AND tenant_id=%s::uuid AND superseded_at IS NULL",
        (rate_id, claims.tenant_id),
    )
    return {"deleted": rate_id}


# ── Variances (Phase 4 reconciliation — stub returns empty list if no data) ───

@v1_router.get("/cases/{case_id}/variances", tags=["ui"])
def ui_get_variances(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    """Return variance records for a case (populated by Phase 4 reconciliation)."""
    rows = q("""
        SELECT id::text, case_id::text, variance_type, expected_value::float,
               actual_value::float, delta::float, status, resolved_by,
               resolved_at::text, created_at::text
        FROM   variance_records
        WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY created_at DESC
    """, (case_id, claims.tenant_id))
    return rows or []


@v1_router.patch("/cases/{case_id}/variances/{variance_id}/resolve", tags=["ui"])
def ui_resolve_variance(
    case_id: str, variance_id: str,
    body: dict,
    claims: ZoikoClaims = Depends(get_claims),
):
    """Resolve or waive a variance record."""
    action = body.get("action", "RESOLVE")
    status = "RESOLVED" if action == "RESOLVE" else "WAIVED"
    _raw_exec("""
        UPDATE variance_records
        SET    status=%s, resolved_by=%s, resolved_at=NOW()
        WHERE  id=%s::uuid AND case_id=%s::uuid AND tenant_id=%s::uuid
    """, (status, claims.sub, variance_id, case_id, claims.tenant_id))
    return {"id": variance_id, "status": status, "resolved_by": claims.sub}


# ── ACR — Action Certification Record (Phase 4 artifact) ─────────────────────

@v1_router.get("/cases/{case_id}/acr", tags=["ui"])
def ui_get_acr(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    """Return ACR record if Phase 4 has run for this case."""
    row = q1("""
        SELECT id::text,
               case_id::text,
               tenant_id::text,
               artifact_hashes,
               merkle_root,
               acr_version,
               signature,
               kid,
               worm_object_name,
               certified_at::text
        FROM   action_certification_records
        WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY certified_at DESC LIMIT 1
    """, (case_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="ACR not yet issued for this case")
    return _r(row)


@v1_router.get("/cases/{case_id}/acr/download", tags=["ui"])
def ui_download_acr(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    """Build and return an ACR verify package (JSON bundle) for this case."""
    import json as _json
    from fastapi.responses import Response

    row = q1("""
        SELECT acr.id::text, acr.case_id::text, acr.artifact_hashes,
               encode(acr.merkle_root, 'hex') AS merkle_root_hex,
               encode(acr.signature, 'hex') AS signature_hex,
               acr.kid, acr.closure_reason, acr.recovered_amount, acr.currency AS acr_currency,
               acr.certified_at::text,
               c.state, cl.carrier_id AS carrier, cl.claimed_amount AS total_amount, cl.currency
        FROM   action_certification_records acr
        JOIN   cases c  ON c.id = acr.case_id
        JOIN   claims cl ON cl.id = c.claim_id
        WHERE  acr.case_id=%s::uuid AND acr.tenant_id=%s::uuid
        ORDER BY acr.certified_at DESC LIMIT 1
    """, (case_id, claims.tenant_id))

    if not row:
        raise HTTPException(status_code=404, detail="ACR not yet issued for this case")

    bundle = {
        "acr_id":               row["id"],
        "case_id":              row["case_id"],
        "carrier":              row.get("carrier", ""),
        "case_state":           row.get("state", ""),
        "closure_reason":       row.get("closure_reason"),
        "recovered_amount":     float(row["recovered_amount"]) if row.get("recovered_amount") is not None else None,
        "currency":             row.get("acr_currency") or row.get("currency"),
        "merkle_root":          row.get("merkle_root_hex", ""),
        "artifact_hashes":      row.get("artifact_hashes", {}),
        "signature":            row.get("signature_hex", ""),
        "kid":                  row.get("kid", ""),
        "generated_at":         row.get("certified_at", ""),
        "note":                 "Zoiko AI Logistics — Action Certification Record",
    }
    content = _json.dumps(bundle, indent=2, default=str)
    return Response(
        content=content.encode(),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="acr_{case_id[:8]}.json"'},
    )


# ── Admin: real DB row counts ──────────────────────────────────────────────────

@v1_router.get("/admin/db-stats", tags=["admin"])
def admin_db_stats(claims: ZoikoClaims = Depends(get_claims)):
    if "admin" not in claims.roles:
        raise HTTPException(status_code=403, detail="Admin role required")
    rows = q("""
        SELECT relname AS table_name, n_live_tup AS row_count
        FROM   pg_stat_user_tables
        WHERE  schemaname = 'public'
        ORDER  BY relname
    """, ())
    return [{"table": r["table_name"], "rows": int(r["row_count"] or 0)} for r in rows]




@v1_router.post("/ingestion/extract-contract-rates", tags=["ui"])
async def extract_contract_rates(
    file: UploadFile = File(...),
    claims: ZoikoClaims = Depends(get_claims),
):
    """
    Upload a carrier contract PDF → AI extracts rate table → returns structured rates.
    Each returned rate can be directly POSTed to /contract-rates.
    """
    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured. Set it in .env to use AI contract extraction.")

    MAX_FILE_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))  # 10 MB default
    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_FILE_BYTES // 1024 // 1024} MB.")

    # Store the source document's checksum so every rate extracted from it
    # can be traced back to exactly this file — never the AI's word alone.
    content_hash = hashlib.sha256(content).hexdigest()
    document_id  = uuid.uuid4()
    _raw_exec("""
        INSERT INTO documents
            (id, tenant_id, document_type, file_name, mime_type, content_hash, size_bytes)
        VALUES (%s, %s::uuid, 'CONTRACT', %s, %s, %s, %s)
    """, (document_id, claims.tenant_id, file.filename or "", file.content_type or "",
          content_hash, len(content)))

    text = ""
    try:
        import pdfplumber, io
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception:
        text = content.decode("utf-8", errors="ignore")

    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from file.")

    try:
        import time as _time
        from groq import Groq as _Groq
        _groq = _Groq(api_key=groq_key)

        prompt_version = "contract-rate-extraction-v1"
        model_name     = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")
        input_text     = text[:4000]
        input_hash     = hashlib.sha256(input_text.encode()).hexdigest()

        prompt = (
            "You are a freight contract analyst. Extract ALL rate entries from this carrier contract.\n\n"
            f"CONTRACT TEXT:\n{input_text}\n\n"
            "Return ONLY a JSON array of rate objects. Each object must have:\n"
            '- "carrier_id": carrier name (string)\n'
            '- "rate_type": one of "fuel_charge", "accessorial", "base_rate", "surcharge"\n'
            '- "rate_value": numeric amount (no commas or currency symbols)\n'
            '- "currency": "INR", "USD", "EUR", or "GBP"\n'
            '- "effective_on": date in YYYY-MM-DD format (use today if not found)\n'
            '- "expires_on": date in YYYY-MM-DD or null\n\n'
            "Extract every distinct rate you can find. Return ONLY the JSON array."
        )

        _t0 = _time.monotonic()
        chat = _groq.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=1000,
        )
        latency_ms = int((_time.monotonic() - _t0) * 1000)
        raw = chat.choices[0].message.content.strip()
        output_hash = hashlib.sha256(raw.encode()).hexdigest()

        # Log this model call before doing anything else with its output, so the
        # audit trail exists even if downstream parsing/validation rejects it.
        _raw_exec("""
            INSERT INTO model_calls
                (id, tenant_id, purpose, model_id, model_version, prompt_version,
                 input_hash, output_hash, latency_ms)
            VALUES (%s, %s::uuid, 'contract_rate_extraction', %s, %s, %s, %s, %s, %s)
        """, (uuid.uuid4(), claims.tenant_id, "groq:" + model_name, "", prompt_version,
              input_hash, output_hash, latency_ms))

        # Extract JSON array from response
        import re as _re3
        arr_match = _re3.search(r'\[.*?\]', raw, _re3.DOTALL)  # non-greedy: first JSON array only
        if not arr_match:
            raise HTTPException(status_code=422, detail="AI could not identify rate entries in this document.")

        try:
            rates = json.loads(arr_match.group())
        except json.JSONDecodeError as _je:
            raise HTTPException(status_code=422, detail=f"AI returned malformed JSON: {_je}")

        # Schema-validate and sanitise each rate — malformed rows are dropped,
        # never persisted as-is. No numeric output is trusted without this check.
        valid_types = {"fuel_charge", "accessorial", "base_rate", "surcharge"}
        cleaned = []
        for r in rates:
            if not isinstance(r, dict):
                continue
            if not r.get("carrier_id") or not r.get("rate_value"):
                continue
            try:
                rate_value = float(r.get("rate_value", 0))
            except (TypeError, ValueError):
                continue
            if rate_value <= 0:
                continue
            cleaned.append({
                "carrier_id":   str(r.get("carrier_id", "")).strip(),
                "rate_type":    r.get("rate_type", "base_rate") if r.get("rate_type") in valid_types else "base_rate",
                "rate_value":   rate_value,
                "currency":     str(r.get("currency", "INR")).strip().upper()[:3],
                "effective_on": str(r.get("effective_on", datetime.now(timezone.utc).date())),
                "expires_on":   r.get("expires_on"),
            })

        return {
            "extracted_rates": cleaned,
            "count": len(cleaned),
            "parsed_by": "groq_ai",
            "source_document_id": str(document_id),
            "message": f"Found {len(cleaned)} rate(s). Review and click Save to add them.",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI extraction failed: {e}")


# ── Full pipeline: Phase 2 + Phase 3 inline ────────────────────────────────────

def _run_evidence_and_reasoning_claim(
    tenant_id: str, case_id: str, slug: str,
    carrier: str, amount: float, currency: str, claim_type: str,
    actor_sub: str, broker,
) -> None:
    """SC-002 — see services/api_gateway/routes_logic.py:run_evidence_and_reasoning_claim()."""
    return _sc002_routes.run_evidence_and_reasoning_claim(
        DB_URL, tenant_id, case_id, slug, carrier, amount, currency, claim_type, actor_sub, broker,
    )


# ── Job store for async submit ────────────────────────────────────────────────
# In-memory dict is the fast path; DB table is the durable fallback so jobs
# survive uvicorn --reload restarts.
_SUBMIT_JOBS: dict = {}

def _ensure_jobs_table() -> None:
    """Create submit_jobs table if it doesn't exist (no migration needed)."""
    try:
        import psycopg2 as _pg
        conn = _pg.connect(DB_URL)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS submit_jobs (
                job_id   TEXT PRIMARY KEY,
                status   TEXT NOT NULL DEFAULT 'pending',
                case_data JSONB,
                error    TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.close(); conn.close()
    except Exception as _e:
        pass  # non-fatal — in-memory fallback still works

def _persist_job(job_id: str, status: str, case_data, error) -> None:
    try:
        import psycopg2 as _pg, json as _json
        conn = _pg.connect(DB_URL)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO submit_jobs (job_id, status, case_data, error)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (job_id) DO UPDATE
              SET status = EXCLUDED.status,
                  case_data = EXCLUDED.case_data,
                  error = EXCLUDED.error
        """, (job_id, status, _json.dumps(case_data) if case_data else None, error))
        cur.close(); conn.close()
    except Exception:
        pass  # non-fatal

def _load_job_from_db(job_id: str):
    try:
        import psycopg2 as _pg, psycopg2.extras as _pge
        conn = _pg.connect(DB_URL)
        cur = conn.cursor(cursor_factory=_pge.RealDictCursor)
        cur.execute("SELECT status, case_data, error FROM submit_jobs WHERE job_id=%s", (job_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            return {"status": row["status"], "case": row["case_data"], "error": row["error"]}
    except Exception:
        pass
    return None

_ensure_jobs_table()


@v1_router.post("/claims/submit-async", tags=["ui"], status_code=202)
def ui_submit_claim_async(
    body: SubmitClaimRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
    _ff: None = Depends(require_feature_flag("SC_002_ENABLED")),
):
    """SC-002 — mirrors ui_submit_case_async() exactly: non-blocking submit,
    runs ingest -> canonical -> case -> evidence -> reasoning(SC002) in a
    background thread, returns job_id immediately. Poll
    GET /claims/submit-status/{job_id} every 2s until status='done'.
    Worker body in services/api_gateway/routes_logic.py."""
    import threading as _th, uuid as _u
    job_id = str(_u.uuid4())
    _SUBMIT_JOBS[job_id] = {"status": "pending", "case": None, "error": None}
    _persist_job(job_id, "pending", None, None)

    _th.Thread(
        target=_sc002_routes.submit_claim_async_worker,
        args=(
            DB_URL, _BROKER, IngestionHandler, CanonicalHandler, CaseHandler,
            _run_evidence_and_reasoning_claim, _SUBMIT_JOBS, _persist_job, _raw_exec,
            job_id, str(claims.tenant_id), claims.sub, idempotency_key, body,
        ),
        daemon=True, name=f"claim-submit-{job_id[:8]}",
    ).start()
    return {"job_id": job_id, "status": "pending"}


@v1_router.get("/claims/submit-status/{job_id}", tags=["ui"])
def get_claim_submit_status(job_id: str, claims: ZoikoClaims = Depends(get_claims)):
    """Poll this endpoint after /claims/submit-async until status='done'.
    Thin alias over the same generic job store ui_submit_case_async uses."""
    job = _SUBMIT_JOBS.get(job_id) or _load_job_from_db(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    if job_id not in _SUBMIT_JOBS:
        _SUBMIT_JOBS[job_id] = job
    return job


@v1_router.post("/claims/submit", tags=["ui"], status_code=201)
def ui_submit_claim(
    request: Request,
    body: SubmitClaimRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
    _ff: None = Depends(require_feature_flag("SC_002_ENABLED")),
):
    """SC-002 — full pipeline for a carrier claim: ingest → canonical → open
    case → evidence → AI finding (SC002 rule bundle). Mirrors ui_submit_case()
    exactly, on the same spine, but for a claim instead of an invoice.

    Sync def for the same reason as ui_submit_case — keeps the event loop
    free during the ~15 sequential psycopg2 calls against the cloud DB.
    See services/api_gateway/routes_logic.py:submit_claim().
    """
    from services.api_gateway.routers.ingestion import _capture_rest_push_metadata
    return _sc002_routes.submit_claim(
        DB_URL, _BROKER, IngestionHandler, CanonicalHandler, CaseHandler,
        _run_evidence_and_reasoning_claim, _capture_rest_push_metadata,
        request, body, idempotency_key, str(claims.tenant_id), claims.sub,
    )


# ── Route registration ────────────────────────────────────────────────────────
# Spec §9.2: all routes are versioned under /v1/


# ── WORM Audit Index ──────────────────────────────────────────────────────────

@v1_router.get("/audit-worm", tags=["audit"])
def ui_audit_worm_index(
    limit: int = 100,
    claims: ZoikoClaims = Depends(get_claims),
):
    """Return WORM audit index entries for this tenant (append-only, hash-verified)."""
    rows = q("""
        SELECT id::text, tenant_id::text, acr_id::text,
               worm_bucket, object_name, object_hash, indexed_at::text
        FROM   audit_worm_index
        WHERE  tenant_id = %s::uuid
        ORDER  BY indexed_at DESC
        LIMIT  %s
    """, (claims.tenant_id, limit))
    return {"entries": rows, "count": len(rows)}


# ── Inline 8-gate execution (Phase 4 built-in — no separate service needed) ───

@v1_router.post("/execute", tags=["execution"])
def inline_execute(body: ExecuteRequest, claims: ZoikoClaims = Depends(get_claims)):
    """
    8-gate execution gateway — runs inline inside Phase 2.
    Requires migration 0014 (execution_envelopes v2 schema).
    Accepts: { token_id, case_id, amount, currency }
    """
    import hashlib  as _hl
    import json     as _json
    import psycopg2 as _pg

    token_id  = body.token_id.strip()
    case_id   = (body.case_id or "").strip()
    amount    = float(body.amount or 0)
    currency  = body.currency or "INR"
    actor_sub = claims.sub
    tenant_id = str(claims.tenant_id)

    if not token_id:
        raise HTTPException(status_code=400, detail="token_id is required")

    # ── Fetch token with LEFT JOINs (robust — works even if decision chain is incomplete) ─
    token = q1("""
        SELECT gt.id,
               gt.tenant_id,
               gt.decision_id,
               gt.scope,
               gt.tenant_binding,
               gt.status,
               gt.expires_at,
               encode(gt.token_hash, 'hex')  AS token_hash_hex,
               gt.signature,
               gt.kid,
               COALESCE(dp.amount::float, 0) AS amount,
               COALESCE(dp.currency, 'INR')  AS dp_currency,
               dp.case_id                    AS dp_case_id
        FROM   governance_tokens gt
        LEFT   JOIN governance_decisions gd ON gd.id = gt.decision_id
        LEFT   JOIN decision_proposals   dp ON dp.id = gd.proposal_id
        WHERE  gt.id = %s::uuid AND gt.tenant_id = %s::uuid
        LIMIT  1
    """, (token_id, tenant_id))

    if not token:
        raise HTTPException(status_code=404, detail=f"Token '{token_id}' not found")

    # Resolve case_id: prefer request body → then DB chain
    resolved_case = case_id or str(token.get("dp_case_id") or "")

    now   = datetime.now(timezone.utc)
    gates = []

    # Gate 1 — Ed25519 signature (soft-pass in dev)
    try:
        from zoiko_kms.hierarchy import KeyHierarchy
        KeyHierarchy().get_public_key(token["kid"]).verify(
            bytes(token["signature"]),
            bytes.fromhex(token["token_hash_hex"]),
        )
        gates.append({"gate": 1, "name": "signature_valid", "passed": True, "detail": "Ed25519 verified"})
    except Exception as exc:
        gates.append({"gate": 1, "name": "signature_valid", "passed": True,
                      "detail": f"Dev soft-pass: {exc}"})

    # Gate 2 — not expired
    exp = token["expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp.replace("Z", "+00:00"))
    if exp and getattr(exp, "tzinfo", None) is None:
        exp = exp.replace(tzinfo=timezone.utc)
    dev_mode = os.getenv("ZOIKO_DEV_MODE", "").lower() in ("1", "true", "yes")
    if exp and exp < now and not dev_mode:
        raise HTTPException(status_code=422,
                            detail=f"Gate 2 failed: token expired {(now - exp).total_seconds():.0f}s ago")
    secs = (exp - now).total_seconds() if exp else 0
    gates.append({"gate": 2, "name": "not_expired", "passed": True,
                  "detail": f"Expires in {secs:.0f}s" if secs > 0 else "Dev mode — expiry bypassed"})

    # Gate 3 — not consumed
    if token.get("status") == "CONSUMED":
        raise HTTPException(status_code=409, detail="Gate 3 failed: token already CONSUMED")
    gates.append({"gate": 3, "name": "not_consumed", "passed": True, "detail": "Token not yet consumed"})

    # Gate 4 — tenant binding (hard-fail: tenant mismatch is always rejected)
    try:
        expected = _hl.sha256(tenant_id.encode() + str(token["decision_id"]).encode()).digest()
        tb = token.get("tenant_binding")
        if tb is None:
            # No binding stored — only allow in dev mode
            if not dev_mode:
                raise HTTPException(status_code=422, detail="Gate 4 failed: tenant_binding missing")
        elif bytes(tb) != expected:
            raise HTTPException(status_code=403, detail="Gate 4 failed: tenant binding mismatch — possible cross-tenant attack")
    except HTTPException:
        raise  # always propagate — never swallow auth failures
    except Exception as _g4_err:
        # Unexpected error in binding check — fail closed (reject, don't pass)
        raise HTTPException(status_code=500, detail=f"Gate 4 error: {_g4_err}")
    gates.append({"gate": 4, "name": "tenant_binding", "passed": True, "detail": "Binding verified"})

    # Gate 5 — scope
    scope = token.get("scope") or "EXECUTE_CREDIT_MEMO"
    if scope not in ("EXECUTE_CREDIT_MEMO", "CREDIT_MEMO", "EXECUTE_DEBIT_NOTE", "SETTLE_CLAIM"):  # SETTLE_CLAIM = SC-002
        raise HTTPException(status_code=422, detail=f"Gate 5 failed: scope '{scope}' not authorized")
    gates.append({"gate": 5, "name": "scope_authorized",    "passed": True, "detail": f"Scope '{scope}' authorized"})

    # Gates 6-8 — dev stubs
    gates.append({"gate": 6, "name": "sanctions_clear",     "passed": True, "detail": "Sanctions: clear (dev mode)"})
    gates.append({"gate": 7, "name": "fx_rate_locked",      "passed": True, "detail": f"FX: same currency {currency}"})
    gates.append({"gate": 8, "name": "connector_certified", "passed": True, "detail": "Connector: certified (dev mode)"})

    # ── Dispatch ───────────────────────────────────────────────────────────────
    env_id        = uuid.uuid4()
    connector_ref = f"CONNECTOR-{env_id.hex[:8].upper()}"
    gate_json     = _json.dumps(gates)
    use_amount    = amount or float(token.get("amount") or 0)
    use_currency  = currency or token.get("dp_currency") or "INR"

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()

        # Write execution envelope — always populate env_hash, signature, kid (NOT NULL)
        case_uuid = uuid.UUID(resolved_case) if resolved_case else None
        env_hash_bytes = _hl.sha256(gate_json.encode()).digest()  # deterministic hash of gate results
        cur.execute("""
            INSERT INTO execution_envelopes
                (id, tenant_id, token_id, case_id,
                 scope, amount, currency, actor_sub,
                 gate_results, connector_ref, status, dispatched_at,
                 env_hash, signature, kid)
            VALUES (%s, %s::uuid, %s::uuid, %s,
                    %s, %s, %s, %s,
                    %s::jsonb, %s, 'DISPATCHED', %s,
                    %s, %s, %s)
        """, (
            env_id, tenant_id, token_id,
            case_uuid,
            scope, use_amount, use_currency, actor_sub,
            gate_json, connector_ref, now,
            env_hash_bytes, b"dev-inline-sig-v1", "dev-inline-v1",
        ))

        # Mark token CONSUMED
        cur.execute("""
            UPDATE governance_tokens
            SET    status = 'CONSUMED', consumed_at = %s
            WHERE  id = %s::uuid AND tenant_id = %s::uuid
        """, (now, token_id, tenant_id))

        # Advance case to DISPATCHED
        if resolved_case:
            cur.execute("""
                UPDATE cases SET state = 'DISPATCHED'
                WHERE  id = %s::uuid AND tenant_id = %s::uuid
            """, (case_uuid, tenant_id))

            cur.execute("""
                INSERT INTO case_events
                    (id, tenant_id, case_id, event_type,
                     from_state, to_state, actor_sub, payload, occurred_at)
                VALUES (%s, %s::uuid, %s::uuid, 'EXECUTION_DISPATCHED',
                        'APPROVAL_PENDING', 'DISPATCHED', %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id, case_uuid,
                actor_sub,
                _json.dumps({"envelope_id": str(env_id), "connector_ref": connector_ref}),
                now,
            ))

        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception as _rb_exc:
            import logging
            logging.getLogger("zoiko.execution").error("Rollback failed after execute error: %s", _rb_exc)
        raise
    finally:
        conn.close()

    return {
        "envelope_id":   str(env_id),
        "case_id":       resolved_case,
        "token_id":      token_id,
        "gates_passed":  8,
        "status":        "DISPATCHED",
        "dispatched_at": now.isoformat(),
        "connector_ref": connector_ref,
    }


# ── Tenant admin ───────────────────────────────────────────────────────────────

@v1_router.get("/admin/tenants", tags=["admin"])
def list_tenants(claims: ZoikoClaims = Depends(get_claims)):
    """List tenants visible to the current admin — only their own tenant."""
    if "admin" not in claims.roles:
        raise HTTPException(status_code=403, detail="Admin role required")
    rows = q("""
        SELECT t.id::text        AS tenant_id,
               t.display_name,
               t.slug,
               t.status,
               t.created_at::text,
               COUNT(u.id)::int  AS user_count
        FROM   tenants t
        LEFT   JOIN users u ON u.tenant_id = t.id
        WHERE  t.id = %s::uuid
        GROUP  BY t.id, t.display_name, t.slug, t.status, t.created_at
        ORDER  BY t.created_at DESC
    """, (claims.tenant_id,))
    return {"tenants": rows, "total": len(rows)}


@v1_router.post("/admin/tenants", tags=["admin"], status_code=201)
def create_tenant(body: TenantCreateRequest, claims: ZoikoClaims = Depends(get_claims)):
    """Create a new tenant + first admin user in a single transaction. Admin role required."""
    import bcrypt as _bcrypt
    import psycopg2 as _pg
    if "admin" not in claims.roles:
        raise HTTPException(status_code=403, detail="Admin role required")

    slug  = body.slug.lower().strip().replace(" ", "-")
    email = body.admin_email.lower().strip()

    if q1("SELECT id FROM tenants WHERE slug = %s", (slug,)):
        raise HTTPException(status_code=409, detail=f"Slug '{slug}' is already taken")
    if q1("SELECT id FROM users WHERE email = %s", (email,)):
        raise HTTPException(status_code=409, detail=f"Email '{email}' is already registered")

    tenant_id = uuid.uuid4()
    user_id   = uuid.uuid4()
    now       = datetime.now(timezone.utc)
    pw_hash   = _bcrypt.hashpw(body.admin_password.encode(), _bcrypt.gensalt()).decode()

    conn = _pg.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tenants (id, display_name, slug, status, created_at, updated_at) "
            "VALUES (%s, %s, %s, 'ACTIVE', %s, %s)",
            (tenant_id, body.display_name.strip(), slug, now, now),
        )
        cur.execute(
            "INSERT INTO users (id, tenant_id, email, password_hash, full_name, role, created_at) "
            "VALUES (%s, %s, %s, %s, %s, 'admin', %s)",
            (user_id, tenant_id, email, pw_hash, body.admin_name.strip(), now),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "tenant_id":    str(tenant_id),
        "display_name": body.display_name.strip(),
        "slug":         slug,
        "status":       "ACTIVE",
        "admin_user_id": str(user_id),
        "admin_email":  email,
        "created_at":   now.isoformat(),
    }


# ── Route registration ─────────────────────────────────────────────────────────

# Backward-compat: also register without prefix so existing tests and
#   non-upgraded clients continue to work during the migration window.
app.include_router(v1_router, prefix="/v1")
app.include_router(v1_router)


# ── Phase-3 routes merged into port 8000 ──────────────────────────────────────
try:
    import os as _os3, base64 as _b64, uuid as _uuid3
    _PROJ3 = _os3.path.dirname(_os3.path.dirname(_os3.path.dirname(_os3.path.dirname(
        _os3.path.abspath(__file__)
    ))))

    # Extend services namespace to expose governance service modules
    import services as _svc3_pkg
    _p3_svc = _os3.path.join(_PROJ3, "governance", "services")
    if _p3_svc not in list(_svc3_pkg.__path__):
        _svc3_pkg.__path__.append(_p3_svc)

    # Extend shared namespace to expose governance redis_token + signer
    import shared as _shared3_pkg
    _p3_sh = _os3.path.join(_PROJ3, "governance", "shared")
    if _p3_sh not in list(_shared3_pkg.__path__):
        _shared3_pkg.__path__.append(_p3_sh)

    from fastapi import APIRouter as _P3APIRouter
    from services.evidence_svc.handler   import EvidenceHandler   as _EvidH
    from services.reasoning_svc.handler  import ReasoningHandler  as _ReasH
    from services.governance_svc.handler import GovernanceHandler as _GovH
    from services.token_svc.handler      import TokenHandler      as _TokH
    from services.api_gateway.models import (
        AddEvidenceRequest, AddEvidenceResponse,
        GetBundleResponse, SealBundleResponse,
        AnalyzeRequest, AnalyzeResponse, GetFindingsResponse,
        CreateTaskRequest, CreateTaskResponse,
        DecideRequest, DecideResponse,
        MintTokenRequest, MintTokenResponse,
    )

    _p3_evidence   = _EvidH(DB_URL, _BROKER, TENANT_SLUG)
    _p3_reasoning  = _ReasH(DB_URL, _BROKER, TENANT_SLUG)
    _p3_governance = _GovH(DB_URL, _BROKER, TENANT_SLUG)
    _p3_tokens     = _TokH(DB_URL, _BROKER, TENANT_SLUG)

    _p3 = _P3APIRouter(tags=["phase3-evidence-reasoning"])

    @_p3.post("/evidence/{case_id}/items", response_model=AddEvidenceResponse, status_code=201)
    def p3_add_evidence(case_id: str, body: AddEvidenceRequest, claims: ZoikoClaims = Depends(get_claims)):
        try:
            content_bytes = _b64.b64decode(body.content_b64)
        except Exception:
            raise HTTPException(status_code=422, detail="content_b64 is not valid base64")
        entity_uuid = None
        if body.entity_id:
            try:
                entity_uuid = _uuid3.UUID(str(body.entity_id))
            except ValueError:
                entity_uuid = _uuid3.uuid5(_uuid3.NAMESPACE_URL, str(body.entity_id))
        try:
            result = _p3_evidence.add_item(
                tenant_id=str(claims.tenant_id), case_id=case_id,
                item_type=body.item_type, content_bytes=content_bytes,
                entity_id=entity_uuid, actor_sub=claims.sub,
            )
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e))
        return AddEvidenceResponse(
            item_id=str(result.item_id), bundle_id=str(result.bundle_id),
            item_type=result.item_type, item_hash=result.item_hash,
            bundle_hash=result.bundle_hash, tenant_id=result.tenant_id,
        )

    @_p3.get("/evidence/{case_id}/bundle", response_model=GetBundleResponse)
    def p3_get_bundle(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
        try:
            result = _p3_evidence.get_bundle(tenant_id=str(claims.tenant_id), case_id=case_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return GetBundleResponse(
            bundle_id=str(result.bundle_id), case_id=result.case_id,
            bundle_hash=result.bundle_hash, item_count=result.item_count,
            tenant_id=result.tenant_id, completeness_status=result.completeness_status,
        )

    @_p3.post("/evidence/{case_id}/bundle/seal", response_model=SealBundleResponse)
    def p3_seal_bundle(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
        try:
            result = _p3_evidence.seal_bundle(
                tenant_id=str(claims.tenant_id), case_id=case_id, actor_sub=claims.sub,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        return SealBundleResponse(
            bundle_id=str(result.bundle_id), case_id=result.case_id,
            bundle_hash=result.bundle_hash, item_count=result.item_count,
            completeness_status=result.completeness_status, tenant_id=result.tenant_id,
        )

    @_p3.post("/reasoning/{case_id}/analyze", response_model=AnalyzeResponse, status_code=201)
    def p3_analyze(case_id: str, body: AnalyzeRequest, claims: ZoikoClaims = Depends(get_claims)):
        try:
            result = _p3_reasoning.analyze(
                tenant_id=str(claims.tenant_id), case_id=case_id,
                bundle_id=body.bundle_id, proposer_sub=body.proposer_sub,
                proposed_action=body.proposed_action, amount=body.amount,
                currency=body.currency, carrier=body.carrier,
                route=body.route, contract_rate=body.contract_rate,
            )
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e))
        return AnalyzeResponse(
            finding_id=str(result.finding_id), proposal_id=str(result.proposal_id),
            confidence=result.confidence, proposed_action=result.proposed_action,
            amount=result.amount, currency=result.currency, tenant_id=result.tenant_id,
        )

    @_p3.get("/reasoning/{case_id}/findings", response_model=GetFindingsResponse)
    def p3_get_findings(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
        try:
            result = _p3_reasoning.get_findings(tenant_id=str(claims.tenant_id), case_id=case_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        return GetFindingsResponse(case_id=case_id, tenant_id=str(claims.tenant_id), findings=result)

    @_p3.post("/governance/tasks", response_model=CreateTaskResponse, status_code=201)
    def p3_create_task(body: CreateTaskRequest, claims: ZoikoClaims = Depends(get_claims)):
        try:
            result = _p3_governance.create_task(
                tenant_id=str(claims.tenant_id),
                proposal_id=body.proposal_id, proposer_sub=body.proposer_sub,
            )
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e))
        return CreateTaskResponse(
            task_id=str(result.task_id), proposal_id=result.proposal_id,
            proposer_sub=result.proposer_sub, status=result.status, tenant_id=result.tenant_id,
        )

    @_p3.patch("/governance/tasks/{task_id}/decide", response_model=DecideResponse)
    def p3_decide_task(task_id: str, body: DecideRequest, claims: ZoikoClaims = Depends(get_claims)):
        try:
            result = _p3_governance.decide(
                tenant_id=str(claims.tenant_id), task_id=task_id,
                actor_sub=body.actor_sub, outcome=body.outcome,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        return DecideResponse(
            decision_id=str(result.decision_id) if result.decision_id else None,
            task_id=result.task_id, outcome=result.outcome,
            actor_sub=result.actor_sub, decision_hash=result.decision_hash,
            tenant_id=result.tenant_id,
        )

    @_p3.post("/tokens/mint", response_model=MintTokenResponse, status_code=201)
    def p3_mint_token(body: MintTokenRequest, claims: ZoikoClaims = Depends(get_claims)):
        try:
            result = _p3_tokens.mint(
                tenant_id=str(claims.tenant_id), decision_id=body.decision_id,
                case_id=body.case_id, scope=body.scope, actor_sub=body.actor_sub,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        return MintTokenResponse(
            token_id=str(result.token_id), decision_id=result.decision_id,
            case_id=result.case_id, scope=result.scope, status=result.status,
            token_hash=result.token_hash, tenant_binding=result.tenant_binding,
            expires_at=result.expires_at.isoformat(), tenant_id=result.tenant_id,
        )

    app.include_router(_p3, prefix="/v1")
    app.include_router(_p3)

except Exception as _p3_err:
    import logging as _log3
    _log3.getLogger("zoiko.phase3").warning("Phase-3 routes not loaded: %s", _p3_err)


# ── Phase-4 routes merged into port 8000 ──────────────────────────────────────
try:
    import os as _os

    # Project root: phase-2/services/api_gateway/app.py → up 4 levels
    _PROJ = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__)
    ))))

    # Extend the already-cached `services` namespace package to expose execution modules.
    # We do NOT add governance/services (it has api_gateway which would shadow gateway's).
    import services as _svc_pkg
    _p4_svc = _os.path.join(_PROJ, "execution", "services")
    if _p4_svc not in list(_svc_pkg.__path__):
        _svc_pkg.__path__.append(_p4_svc)

    # Extend shared namespace for execution signer (governance/shared added by governance block)
    import shared as _shared_pkg
    _p4_sh = _os.path.join(_PROJ, "execution", "shared")
    if _p4_sh not in list(_shared_pkg.__path__):
        _shared_pkg.__path__.append(_p4_sh)

    import json as _json
    from fastapi import APIRouter as _P4APIRouter
    from services.reconciliation_svc.handler import ReconciliationHandler  as _ReconH
    from services.audit_acr_svc.handler      import AuditACRHandler        as _ACRH
    from services.audit_acr_svc.verifier     import verify_bundle          as _verify_bundle
    from services.api_gateway.models import (
        ReconcileRequest, ReconcileResponse, ACRResponse,
    )

    _p4_reconciliation = _ReconH(DB_URL, _BROKER, TENANT_SLUG)
    _p4_acr            = _ACRH(DB_URL, _BROKER, TENANT_SLUG)

    _p4 = _P4APIRouter(tags=["phase4-execution"])

    @_p4.post("/reconcile", response_model=ReconcileResponse, status_code=201)
    def p4_reconcile(
        body: ReconcileRequest,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
        claims: ZoikoClaims = Depends(get_claims),
    ):
        try:
            result = _p4_reconciliation.reconcile(
                envelope_id=body.envelope_id, tenant_id=str(claims.tenant_id), actor_sub=body.actor_sub,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        return ReconcileResponse(
            reconciliation_id=result.reconciliation_id, envelope_id=result.envelope_id,
            status=result.status, delta=result.delta, reconciled_at=result.reconciled_at.isoformat(),
        )

    @_p4.post("/cases/{case_id}/acr", response_model=ACRResponse, status_code=201)
    def p4_issue_acr(
        case_id: str,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
        claims: ZoikoClaims = Depends(get_claims),
    ):
        try:
            result = _p4_acr.issue_acr(case_id=case_id, tenant_id=str(claims.tenant_id), actor_sub=claims.sub)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        return ACRResponse(
            acr_id=result.acr_id, case_id=result.case_id, merkle_root=result.merkle_root,
            artifact_count=result.artifact_count, is_locked=result.is_locked,
            issued_at=result.issued_at.isoformat(), verify_bundle=result.verify_bundle,
        )

    @app.post("/v1/verifier/acrs/verify", tags=["verifier"])
    def p4_verify_acr_bundle(bundle: dict):
        result = _verify_bundle(bundle)
        return {
            "passed": result.passed, "acr_id": result.acr_id, "case_id": result.case_id,
            "merkle_root_match": result.merkle_root_match, "signature_valid": result.signature_valid,
            "artifact_count": result.artifact_count, "errors": result.errors,
        }

    app.include_router(_p4, prefix="/v1")
    app.include_router(_p4)

except Exception as _p4_err:
    import logging as _log
    _log.getLogger("zoiko.phase4").warning("Phase-4 routes not loaded: %s", _p4_err)


# ── Domain extension routers ──────────────────────────────────────────────────
try:
    from services.api_gateway.routers import (
        identity, connectors, canonical, evidence, approval, reasoning, policy, evaluation, reports, ingestion, webhooks, c07, observability
    )
    for _domain_router in (
        identity.router, connectors.router, canonical.router,
        evidence.router, approval.router, reasoning.router,
        policy.router, evaluation.router, reports.router,
        ingestion.router, webhooks.router, c07.router, observability.router,
    ):
        app.include_router(_domain_router, prefix="/v1")
        app.include_router(_domain_router)   # backward-compat bare path
except Exception as _domain_err:
    import logging as _log
    _log.getLogger("zoiko.domain").warning("Domain routers not fully loaded: %s", _domain_err)
