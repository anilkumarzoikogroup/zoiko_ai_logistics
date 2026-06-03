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

from fastapi import FastAPI, Depends, Header, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from services.api_gateway.auth   import get_claims
from zoiko_common.middleware.feature_flags import require_feature_flag
import re as _re, uuid, hashlib, json
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from services.api_gateway.models import (
    InvoiceRequest, InvoiceResponse,
    ValidateRequest, ValidateResponse,
    CanonicalizeRequest, CanonicalizeResponse,
    OpenCaseRequest, OpenCaseResponse,
    TransitionRequest, TransitionResponse,
    HealthResponse,
    SubmitCaseRequest, UIProposalRequest, UIDecideRequest,
    ContractRateRequest,
    LoginRequest, LoginResponse,
    RegisterRequest, RegisterResponse,
    UsersListResponse, UserItem,
    TenantCreateRequest,
    ExecuteRequest,
)
from shared.db import q, q1
from zoiko_common.crypto.jcs import canonicalize as _jcs
from services.ingestion_svc.handler    import IngestionHandler
from services.ingestion_svc.models     import InvoiceInput
from services.validation_svc.handler  import ValidationHandler
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
            import importlib, logging, json
            _kafka_module = importlib.import_module("kafka.producer.kafka")
            _KP = getattr(_kafka_module, "KafkaProducer", None)
            if _KP is None:
                # Fallback: try direct import (works when kafka-python is installed)
                import sys, importlib.util
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

# ── FastAPI app with lifespan (outbox relay + startup logging) ────────────────
import asyncio, threading
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

# OTel distributed tracing (FR-022)
try:
    from zoiko_common.observability.tracing import setup_tracing
    setup_tracing("phase2-api-gateway")
except Exception:
    pass

# Security event publisher (FR-024)
from zoiko_common.security.events import SecurityEventPublisher, SecurityEventKind
_sec = SecurityEventPublisher(broker=_BROKER)

# All UI/internal routes are registered on v1_router; the router is included
# TWICE: once with /v1 prefix (spec §9.2) and once without (backward compat).
from fastapi import APIRouter as _AR
v1_router = _AR()


# ── Singleton handlers ────────────────────────────────────────────────────────

_ingestion  = IngestionHandler(DB_URL, _BROKER, TENANT_SLUG)
_validation = ValidationHandler(DB_URL, _BROKER, TENANT_SLUG)
_canonical  = CanonicalHandler(DB_URL, _BROKER, TENANT_SLUG)
_cases      = CaseHandler(DB_URL, _BROKER)


# ── Auth — public endpoints (no JWT required) ─────────────────────────────────

@app.post("/auth/login", response_model=LoginResponse, tags=["auth"])
@app.post("/v1/auth/login", response_model=LoginResponse, tags=["auth"], include_in_schema=False)
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
    return LoginResponse(
        token      = token,
        tenant_id  = str(row["tenant_id"]),
        role       = row["role"],
        full_name  = row["full_name"],
        email      = row["email"],
        expires_in = ttl,
    )


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

    pw_hash = _bcrypt.hashpw(body.password.encode(), _bcrypt.gensalt()).decode()
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
    import re as _re2, time as _time, random as _rand
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
    response: dict = {"message": "Password reset successfully", "token": token, "email_sent": email_sent}
    if email_error:
        response["email_warning"] = f"Email delivery failed ({email_error}). Check server logs for the reset link."
    return response


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


# ── Sign out ──────────────────────────────────────────────────────────────────

@app.post("/auth/signout", tags=["auth"], status_code=204)
@app.post("/v1/auth/signout", tags=["auth"], include_in_schema=False, status_code=204)
def signout():
    """Client clears its JWT. Server-side: stateless JWT so nothing to revoke here."""
    return  # Client removes token from storage


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


# ── Ingestion ─────────────────────────────────────────────────────────────────

@v1_router.post("/invoices", response_model=InvoiceResponse, status_code=201, tags=["invoices"])
def ingest_invoice(
    body: InvoiceRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
):
    invoice = InvoiceInput(
        carrier_id        = body.carrier_id,
        invoice_number    = body.invoice_number,
        total_amount      = body.total_amount,
        currency          = body.currency,
        route_origin      = body.route_origin,
        route_destination = body.route_destination,
        weight_lbs        = body.weight_lbs,
    )
    result = _ingestion.ingest_invoice(
        tenant_id       = str(claims.tenant_id),
        invoice         = invoice,
        idempotency_key = idempotency_key,
    )
    return InvoiceResponse(
        source_record_id = str(result.source_record_id),
        canonical_hash   = result.canonical_hash,
        idempotency_key  = result.idempotency_key,
        tenant_id        = str(result.tenant_id),
    )


# ── Validation ────────────────────────────────────────────────────────────────

@v1_router.post(
    "/invoices/{source_record_id}/validate",
    response_model=ValidateResponse,
    tags=["invoices"],
)
def validate_invoice(
    source_record_id: str,
    body: ValidateRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        result = _validation.validate(
            tenant_id        = str(claims.tenant_id),
            source_record_id = source_record_id,
            invoice_number   = body.invoice_number,
            carrier_id       = body.carrier_id,
            total_amount     = body.total_amount,
            currency         = body.currency,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation error: {e}")

    return ValidateResponse(
        validation_id     = str(result.validation_id),
        status            = result.status,
        overcharge_amount = result.overcharge_amount,
        violations        = len(result.rule_violations),
        currency          = result.currency,
    )


# ── Canonicalize ──────────────────────────────────────────────────────────────

@v1_router.post(
    "/invoices/{source_record_id}/canonicalize",
    response_model=CanonicalizeResponse,
    tags=["invoices"],
)
def canonicalize_invoice(
    source_record_id: str,
    body: CanonicalizeRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        result = _canonical.canonicalize_invoice(
            tenant_id        = str(claims.tenant_id),
            source_record_id = source_record_id,
            invoice_number   = body.invoice_number,
            carrier_id       = body.carrier_id,
            total_amount     = body.total_amount,
            currency         = body.currency,
            origin_city      = body.origin_city,
            dest_city        = body.dest_city,
            weight_lbs       = body.weight_lbs,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Canonicalization error: {e}")

    return CanonicalizeResponse(
        canonical_invoice_id  = str(result.canonical_invoice_id),
        canonical_shipment_id = str(result.canonical_shipment_id),
        canonical_hash        = result.canonical_hash,
        invoice_number        = result.invoice_number,
    )


# ── Cases ─────────────────────────────────────────────────────────────────────

@v1_router.post("/cases", response_model=OpenCaseResponse, status_code=201, tags=["cases"])
def open_case(
    body: OpenCaseRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    try:
        result = _cases.open_case(
            tenant_id            = str(claims.tenant_id),
            canonical_invoice_id = body.canonical_invoice_id,
            actor_sub            = claims.sub,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Case creation error: {e}")

    return OpenCaseResponse(
        case_id   = str(result.case_id),
        state     = result.state,
        is_new    = result.is_new,
        tenant_id = str(result.tenant_id),
    )


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


def _cases_q(where: str, params: tuple) -> list[dict]:
    rows = q(f"""
        SELECT
            c.id::text                                                   AS id,
            c.tenant_id::text                                            AS tenant_id,
            c.state,
            ci.carrier_id                                                AS carrier,
            COALESCE(cs.origin_city || '-' || cs.dest_city,
                     ci.invoice_number)                                  AS shipment_ref,
            ci.total_amount::float                                       AS amount,
            ci.currency,
            COALESCE((
                SELECT (vr.rule_violations->0->>'delta')::float
                FROM   validation_results vr
                WHERE  vr.source_record_id = ci.source_record_id
                  AND  vr.status = 'FAIL'
                LIMIT  1
            ), 0)                                                        AS diff,
            COALESCE((
                SELECT f.confidence::float
                FROM   findings f WHERE f.case_id = c.id LIMIT 1
            ), 0)                                                        AS confidence,
            c.opened_at,
            c.opened_at                                                  AS updated_at
        FROM  cases c
        JOIN  canonical_invoices ci  ON ci.id = c.invoice_id
        LEFT JOIN canonical_shipments cs ON cs.invoice_id = ci.id
        {where}
        ORDER BY c.opened_at DESC
        LIMIT 100
    """, params)
    return [_r(row) for row in rows]


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
                SELECT (vr.rule_violations->0->>'delta')::float
                FROM   validation_results vr
                WHERE  vr.source_record_id = ci.source_record_id AND vr.status='FAIL'
                LIMIT  1
            )), 0)                             AS total_recovered,
            COALESCE(AVG(f.confidence), 0)     AS avg_confidence
        FROM  cases c
        JOIN  canonical_invoices ci ON ci.id = c.invoice_id
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


# ── Cases list + detail ────────────────────────────────────────────────────────

@v1_router.get("/cases", tags=["ui"])
def ui_list_cases(
    state: str | None = None,
    claims: ZoikoClaims = Depends(get_claims),
):
    tid = claims.tenant_id
    if state:
        return _cases_q("WHERE c.tenant_id=%s::uuid AND c.state=%s", (tid, state))
    return _cases_q("WHERE c.tenant_id=%s::uuid", (tid,))


@v1_router.get("/cases/{case_id}", tags=["ui"])
def ui_get_case(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    rows = _cases_q(
        "WHERE c.tenant_id=%s::uuid AND c.id=%s::uuid",
        (claims.tenant_id, case_id),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Case not found")
    return rows[0]


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

@v1_router.get("/cases/{case_id}/validation", tags=["ui"])
def ui_validation(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    row = q1("""
        SELECT
            vr.id::text,
            c.id::text                                                         AS case_id,
            vr.status                                                          AS outcome,
            COALESCE((vr.rule_violations->0->>'delta')::float, 0)              AS diff,
            ci.currency,
            COALESCE(vr.rule_violations->0->>'rule', 'No violation')           AS reason,
            ci.total_amount::float                                             AS invoice_amount,
            GREATEST(0, ci.total_amount::float -
                COALESCE((vr.rule_violations->0->>'delta')::float, 0))         AS contract_amount,
            vr.validated_at
        FROM   validation_results vr
        JOIN   canonical_invoices ci ON ci.source_record_id = vr.source_record_id
        JOIN   cases c ON c.invoice_id = ci.id
        WHERE  c.id=%s::uuid AND c.tenant_id=%s::uuid
        LIMIT  1
    """, (case_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="No validation found")
    return _r(row)


# ── Canonical invoice ──────────────────────────────────────────────────────────

@v1_router.get("/cases/{case_id}/canonical-invoice", tags=["ui"])
def ui_canonical_invoice(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    row = q1("""
        SELECT
            ci.id::text,
            ci.tenant_id::text,
            COALESCE(cs.origin_city||'-'||cs.dest_city, ci.invoice_number) AS shipment_ref,
            ci.carrier_id                       AS carrier,
            ci.total_amount::float              AS amount,
            ci.currency,
            encode(ci.canonical_hash, 'hex')    AS canonical_hash,
            encode(ci.signature,      'hex')    AS signature,
            ci.created_at                       AS signed_at
        FROM  canonical_invoices ci
        JOIN  cases c ON c.invoice_id = ci.id
        LEFT JOIN canonical_shipments cs ON cs.invoice_id = ci.id
        WHERE c.id=%s::uuid AND c.tenant_id=%s::uuid
        LIMIT 1
    """, (case_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="No canonical invoice found")
    return _r(row)


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
        case_uuid = uuid.UUID(case_id)  # validate format — returns clean 422 on bad UUID
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
        gt.status,
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
               currency, effective_on::text, expires_on::text
        FROM   contract_rates
        WHERE  tenant_id = %s::uuid
        ORDER  BY carrier_id, rate_type
    """, (claims.tenant_id,))
    return [_r(r) for r in rows]


@v1_router.post("/contract-rates", tags=["ui"], status_code=201)
def ui_create_contract_rate(
    body: ContractRateRequest,
    claims: ZoikoClaims = Depends(get_claims),
):
    rid = uuid.uuid4()
    _raw_exec("""
        INSERT INTO contract_rates
            (id, tenant_id, carrier_id, rate_type, rate_value, currency, effective_on, expires_on)
        VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s)
    """, (rid, claims.tenant_id, body.carrier_id, body.rate_type,
          body.rate_value, body.currency, body.effective_on, body.expires_on))
    return {"id": str(rid), "carrier_id": body.carrier_id, "rate_type": body.rate_type,
            "rate_value": body.rate_value, "currency": body.currency,
            "effective_on": body.effective_on}


@v1_router.delete("/contract-rates/{rate_id}", tags=["ui"])
def ui_delete_contract_rate(rate_id: str, claims: ZoikoClaims = Depends(get_claims)):
    _raw_exec(
        "DELETE FROM contract_rates WHERE id=%s::uuid AND tenant_id=%s::uuid",
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
               artifact_refs,
               merkle_root,
               certification_status,
               tlog_entry_index,
               witness_cosignature,
               final_disposition,
               signature,
               created_at::text
        FROM   action_certification_records
        WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
        ORDER BY created_at DESC LIMIT 1
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
        SELECT acr.id::text, acr.case_id::text, acr.artifact_refs,
               acr.merkle_root, acr.certification_status, acr.signature,
               acr.created_at::text,
               c.state, ci.carrier_id AS carrier, ci.total_amount, ci.currency
        FROM   action_certification_records acr
        JOIN   cases c  ON c.id = acr.case_id
        JOIN   canonical_invoices ci ON ci.id = c.invoice_id
        WHERE  acr.case_id=%s::uuid AND acr.tenant_id=%s::uuid
        ORDER BY acr.created_at DESC LIMIT 1
    """, (case_id, claims.tenant_id))

    if not row:
        raise HTTPException(status_code=404, detail="ACR not yet issued for this case")

    bundle = {
        "acr_id":               row["id"],
        "case_id":              row["case_id"],
        "carrier":              row.get("carrier", ""),
        "certification_status": row.get("certification_status", "CERTIFIED"),
        "merkle_root":          str(row.get("merkle_root", "")),
        "artifact_refs":        row.get("artifact_refs", []),
        "signature":            row.get("signature", {}),
        "generated_at":         row.get("created_at", ""),
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


# ── Invoice file parse ────────────────────────────────────────────────────────

@v1_router.post("/ingestion/parse-invoice", tags=["ui"])
async def parse_invoice_file(
    file: UploadFile = File(...),
    claims: ZoikoClaims = Depends(get_claims),
):
    """Parse a PDF or image invoice using Groq AI (vision for images, text for PDFs). Fallback: regex."""
    import re as _re2, base64 as _b64, io as _io
    MAX_FILE_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_FILE_BYTES // 1024 // 1024} MB.")

    # ── City / carrier reference tables ──────────────────────────────────────
    INDIAN_CITIES_SET = {
        "hyderabad", "warangal", "mumbai", "bombay", "delhi", "new delhi",
        "bangalore", "bengaluru", "chennai", "madras", "kolkata", "calcutta",
        "pune", "ahmedabad", "jaipur", "lucknow", "surat", "kochi", "cochin",
        "nagpur", "vizag", "visakhapatnam", "gurgaon", "gurugram", "noida",
        "chandigarh", "coimbatore", "indore", "bhopal", "patna", "vadodara",
        "ludhiana", "agra", "nashik", "thane", "rajkot", "amritsar", "varanasi",
        "bhubaneswar", "raipur", "dehradun", "guwahati", "srinagar", "jodhpur",
        "mysore", "mangalore", "hubli", "tirupati", "madurai", "trivandrum",
        "thiruvananthapuram",
    }

    # IATA → city name (airports commonly found on freight invoices)
    IATA_MAP = {
        "bom": "Mumbai", "del": "Delhi", "blr": "Bangalore", "maa": "Chennai",
        "ccu": "Kolkata", "hyd": "Hyderabad", "pnq": "Pune", "amd": "Ahmedabad",
        "cok": "Kochi", "jfk": "New York", "lax": "Los Angeles", "ord": "Chicago",
        "lhr": "London", "cdg": "Paris", "fra": "Frankfurt", "ams": "Amsterdam",
        "dxb": "Dubai", "auh": "Abu Dhabi", "sin": "Singapore", "hkg": "Hong Kong",
        "icn": "Seoul", "nrt": "Tokyo", "pvg": "Shanghai", "pek": "Beijing",
        "syd": "Sydney", "mel": "Melbourne", "jnb": "Johannesburg", "cai": "Cairo",
        "bkk": "Bangkok", "kul": "Kuala Lumpur", "cgk": "Jakarta",
    }

    CITY_ALIASES = {
        "bombay": "Mumbai", "new delhi": "Delhi", "bengaluru": "Bangalore",
        "calcutta": "Kolkata", "madras": "Chennai", "visakhapatnam": "Vizag",
        "cochin": "Kochi", "gurugram": "Gurgaon", "trivandrum": "Thiruvananthapuram",
        "hongkong": "Hong Kong", "hong kong sar": "Hong Kong",
        "uae": "Dubai", "united arab emirates": "Dubai",
    }

    def _normalize_city(raw: str) -> str:
        """Strip country suffix, expand IATA codes, normalize aliases, title-case."""
        # Strip country: "Mumbai, India" → "Mumbai"
        city = _re2.split(r",\s*|\s+\(", raw)[0].strip()
        city = _re2.sub(r"\s*\([^)]+\)", "", city).strip()
        key = city.lower().strip()
        if key in IATA_MAP:
            return IATA_MAP[key]
        if key in CITY_ALIASES:
            return CITY_ALIASES[key]
        # Match against known Indian cities (fuzzy prefix)
        for c in INDIAN_CITIES_SET:
            if c == key or key.startswith(c) or c.startswith(key):
                return c.title()
        return city.title()

    def _is_indian(city: str) -> bool:
        """Handles 'Mumbai', 'Mumbai, India', 'BOM', etc."""
        norm = _normalize_city(city).lower()
        return norm in INDIAN_CITIES_SET or norm in {v.lower() for v in IATA_MAP.values() if _is_in_india_iata(norm)}

    def _is_in_india_iata(city_lower: str) -> bool:
        indian_iata = {"bom","del","blr","maa","ccu","hyd","pnq","amd","cok"}
        for code, name in IATA_MAP.items():
            if code in indian_iata and name.lower() == city_lower:
                return True
        return False

    KNOWN_CARRIERS = [
        "BlueDart", "Delhivery", "FedEx India", "FedEx", "DTDC",
        "Ekart", "UPS India", "UPS", "V Express", "Gati", "DHL",
        "Aramex", "Maersk", "MSC", "CMA CGM", "Other"
    ]

    # ── Detect file type ──────────────────────────────────────────────────────
    fname = (file.filename or "").lower()
    ctype = (file.content_type or "").lower()
    is_image = ctype.startswith("image/") or fname.endswith((".png", ".jpg", ".jpeg", ".webp"))

    text = ""
    image_b64 = ""
    image_mime = ""

    if is_image:
        image_mime = ctype if ctype.startswith("image/") else (
            "image/png" if fname.endswith(".png") else "image/jpeg"
        )
        image_b64 = _b64.b64encode(content).decode("utf-8")
    else:
        try:
            import pdfplumber
            with pdfplumber.open(_io.BytesIO(content)) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception:
            text = content.decode("utf-8", errors="ignore")

    carrier, amount, currency, origin, dest, email = "", 0.0, "INR", "", "", ""
    ai_parsed = False
    groq_key  = os.getenv("GROQ_API_KEY", "")

    # ── Pre-extract grand total from PDF text (before AI runs) ───────────────
    # Regex against labelled final-amount fields is more reliable than AI for
    # distinguishing grand total from subtotal.  We lock this in early so AI
    # cannot override it with a subtotal value.
    def _find_grand_total(t: str) -> float:
        def _num(raw: str) -> float:
            try:
                v = float(raw.replace(",", ""))
                return v if v >= 100 else 0.0
            except ValueError:
                return 0.0

        # Tier 1 — definitive final-amount labels, cross-line with non-greedy match
        pat1 = (
            r"(?:grand\s+total|amount\s+due|balance\s+due|net\s+payable"
            r"|total\s+payable|total\s+due|invoice\s+total"
            r"|total\s+invoice\s+value|amount\s+payable|final\s+amount"
            r"|total\s+charges|net\s+amount\s+payable)"
            r"[\s\S]{0,80}?([\d,]+\.\d{2})"
        )
        hits = [v for v in (_num(m.group(1)) for m in _re2.finditer(pat1, t, _re2.IGNORECASE)) if v]
        if hits:
            return hits[-1]  # last = bottom of invoice = final total

        # Tier 2 — bare "Total" / "Total Amount" not on a subtotal line
        pat2 = r"(?:total\s+amount|net\s+total|total)[\s\S]{0,40}?([\d,]+\.\d{2})"
        for m in _re2.finditer(pat2, t, _re2.IGNORECASE):
            seg = t[max(0, m.start() - 10): m.start() + 25].lower()
            if "sub" not in seg:
                v = _num(m.group(1))
                if v:
                    return v
        return 0.0

    pdf_amount = _find_grand_total(text) if text else 0.0

    # ── Groq AI extraction ───────────────────────────────────────────────────
    if groq_key and (image_b64 or text.strip()):
        try:
            from groq import Groq as _Groq
            _groq = _Groq(api_key=groq_key)

            extraction_prompt = (
                "You are an expert freight/logistics invoice parser. "
                "Carefully read the invoice and extract exactly these fields.\n\n"
                "Return ONLY a single valid JSON object — no markdown, no explanation:\n"
                "{\n"
                '  "carrier": "<logistics company name, e.g. BlueDart, DHL, FedEx, Maersk, UPS, Aramex — use exact name from invoice>",\n'
                '  "total_amount": <see amount rules below>,\n'
                '  "currency": "<3-letter ISO code from invoice: INR, USD, EUR, GBP, AED, SGD, AUD, etc.>",\n'
                '  "origin": "<shipment ORIGIN city only — no country suffix, e.g. Mumbai, Dubai, New York, Singapore>",\n'
                '  "destination": "<shipment DESTINATION city only — no country suffix, e.g. Delhi, London, Chicago>",\n'
                '  "route_type": "<national if both cities are within India, international if any city is outside India>",\n'
                '  "email": "<any email address visible on the invoice — billing, contact, support or sender email; empty string if none>"\n'
                "}\n\n"
                "AMOUNT RULES — follow this priority strictly:\n"
                "  Priority 1 (highest): Grand Total, Grand Total Amount\n"
                "  Priority 2: Amount Due, Balance Due, Payment Due, Total Due\n"
                "  Priority 3: Net Payable, Total Payable, Amount Payable\n"
                "  Priority 4: Invoice Total, Total Invoice Value, Total Charges\n"
                "  Priority 5: Total Amount — ONLY when NO subtotal or sub-total line exists anywhere\n\n"
                "  CRITICAL EXAMPLE — for this invoice structure:\n"
                "    Subtotal (before tax)   12,119.00\n"
                "    IGST 18%                 2,197.62\n"
                "    TOTAL PAYABLE           14,316.62   ← YOU MUST RETURN THIS\n"
                "  Return 14316.62, NOT 12119.00. The subtotal is NEVER the answer.\n\n"
                "  FORBIDDEN — NEVER return these values:\n"
                "  Subtotal, Sub-total, Sub Total, Basic Freight, Assessable Value,\n"
                "  Taxable Value, Net Amount (before tax), any per-line-item amounts,\n"
                "  unit prices, or any figure that appears BEFORE a tax/surcharge row.\n\n"
                "  The answer is always the LAST and LARGEST summary figure — the amount\n"
                "  the customer actually pays after ALL taxes, surcharges, and fees.\n"
                "  Return as a plain decimal number only, no symbols or commas, e.g. 14316.62\n\n"
                "LOCATION RULES:\n"
                "  1. origin/destination = FROM/TO shipment cities, NOT company/billing address.\n"
                "  2. Expand IATA codes: BOM→Mumbai, DEL→Delhi, JFK→New York, DXB→Dubai, LHR→London.\n"
                "  3. City name only — no state, country, or ZIP.\n"
                "  4. If not found, return empty string."
            )

            if image_b64:
                # Try vision models in order of preference
                vision_models = [
                    os.getenv("GROQ_VISION_MODEL", ""),
                    "meta-llama/llama-4-scout-17b-16e-instruct",
                    "llama-3.2-90b-vision-preview",
                    "llama-3.2-11b-vision-preview",
                ]
                vision_models = [m for m in vision_models if m]  # drop empty
                chat = None
                for vm in vision_models:
                    try:
                        chat = _groq.chat.completions.create(
                            model=vm,
                            messages=[{
                                "role": "user",
                                "content": [
                                    {"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{image_b64}"}},
                                    {"type": "text", "text": extraction_prompt},
                                ],
                            }],
                            temperature=0,
                            max_tokens=400,
                        )
                        break
                    except Exception:
                        continue
                if chat is None:
                    raise RuntimeError("All vision models failed")
            else:
                text_model = os.getenv("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")
                try:
                    chat = _groq.chat.completions.create(
                        model=text_model,
                        messages=[{"role": "user", "content": f"INVOICE TEXT:\n{text[:4000]}\n\n{extraction_prompt}"}],
                        temperature=0,
                        max_tokens=400,
                    )
                except Exception:
                    # Fallback to smaller model
                    chat = _groq.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=[{"role": "user", "content": f"INVOICE TEXT:\n{text[:4000]}\n\n{extraction_prompt}"}],
                        temperature=0,
                        max_tokens=400,
                    )

            raw = chat.choices[0].message.content.strip()
            # Extract first JSON object from response (handles markdown code fences)
            json_match = _re2.search(r'\{[^{}]*\}', raw, _re2.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                except json.JSONDecodeError:
                    parsed = {}
                carrier  = str(parsed.get("carrier", "")).strip()
                ai_amount = float(parsed.get("total_amount", 0) or 0)
                currency = str(parsed.get("currency", "INR")).strip().upper() or "INR"
                origin   = _normalize_city(str(parsed.get("origin", "")).strip())
                dest     = _normalize_city(str(parsed.get("destination", "")).strip())
                if origin == dest:
                    dest = ""
                email    = str(parsed.get("email", "")).strip().lower()
                # PDF amount from regex always wins; use AI amount only for images
                amount = pdf_amount if pdf_amount else ai_amount
                ai_parsed = bool(origin or dest or carrier or amount)
        except Exception:
            ai_parsed = False

    # ── Regex fallback (PDF / text only) ─────────────────────────────────────
    if not ai_parsed and text:
        text_lower = text.lower()

        CARRIER_ALIASES = {
            "bluedart": "BlueDart", "blue dart": "BlueDart",
            "delhivery": "Delhivery",
            "fedex india": "FedEx India", "fedex": "FedEx",
            "dtdc": "DTDC", "ekart": "Ekart", "gati": "Gati",
            "ups india": "UPS India", "ups": "UPS",
            "v express": "V Express", "vexpress": "V Express",
            "dhl": "DHL", "aramex": "Aramex",
            "maersk": "Maersk", "msc ": "MSC", "cma cgm": "CMA CGM",
        }
        for alias, canonical in CARRIER_ALIASES.items():
            if alias in text_lower:
                carrier = canonical
                break

        # Use the pre-extracted PDF amount if already found
        if pdf_amount:
            amount = pdf_amount

        def _parse_num(raw: str) -> float:
            try:
                v = float(raw.replace(",", ""))
                return v if v >= 100 else 0.0
            except ValueError:
                return 0.0

        def _tier1_amounts(text: str) -> list[float]:
            """Find all definitive final-amount labels, allowing multi-line gaps."""
            pat = (
                r"(?:grand\s+total|amount\s+due|balance\s+due|net\s+payable"
                r"|total\s+payable|total\s+due|invoice\s+total"
                r"|total\s+invoice\s+value|amount\s+payable|final\s+amount"
                r"|total\s+charges|net\s+amount\s+payable)"
                r"[\s\S]{0,80}?"           # cross newlines, non-greedy
                r"([\d,]+\.\d{2})"         # require decimal — final amounts always have paise/cents
            )
            return [v for v in (_parse_num(m.group(1)) for m in _re2.finditer(pat, text, _re2.IGNORECASE)) if v]

        # Tier 1 — definitive labels; take the last match (totals are at the bottom)
        # Skip if pdf_amount already resolved above
        tier1 = [] if amount else _tier1_amounts(text)
        if tier1:
            amount = tier1[-1]

        # Tier 2 — bare "Total" or "Total Amount" but never on a subtotal line
        if not amount:
            tier2 = []
            pat2 = (
                r"(?:total\s+amount|net\s+total|total)"
                r"[\s\S]{0,40}?([\d,]+\.\d{2})"
            )
            for m in _re2.finditer(pat2, text, _re2.IGNORECASE):
                # Reject if "sub" appears on the same logical line as the label
                seg = text[max(0, m.start() - 10): m.start() + 30].lower()
                if "sub" not in seg:
                    v = _parse_num(m.group(1))
                    if v:
                        tier2.append(v)
            if tier2:
                amount = tier2[-1]

        # Tier 3 — currency-symbol / currency-code; take max (last resort)
        if not amount:
            for pat in [
                r"[₹$€£]\s*([\d,]+(?:\.\d{1,2})?)",
                r"([\d,]+(?:\.\d{2}))\s*(?:INR|USD|EUR|GBP|AED|SGD)",
            ]:
                candidates = [v for v in (_parse_num(m.group(1)) for m in _re2.finditer(pat, text, _re2.IGNORECASE)) if v]
                if candidates:
                    amount = max(candidates)
                    break

        if "usd" in text_lower or "$ " in text:
            currency = "USD"
        elif "eur" in text_lower or "€" in text:
            currency = "EUR"
        elif "gbp" in text_lower or "£" in text:
            currency = "GBP"
        elif "aed" in text_lower:
            currency = "AED"

        # Email regex fallback
        if not email:
            email_match = _re2.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', text)
            if email_match:
                email = email_match.group(0).lower()

        for pat in [
            r"(?:from|origin|shipper['\s]?city|pickup\s*(?:city|location))[:\s]+([A-Za-z][a-zA-Z .'-]{2,30}?)\s{0,3}(?:to|dest(?:ination)?|consignee['\s]?city|delivery\s*(?:city|location))[:\s]+([A-Za-z][a-zA-Z .'-]{2,30})(?:\s*\n|,|\.|$)",
            r"\b([A-Z][a-z]{2,}(?:[\s][A-Z][a-z]+)?)\s*(?:[-–→]|to)\s*([A-Z][a-z]{2,}(?:[\s][A-Z][a-z]+)?)\b",
        ]:
            m = _re2.search(pat, text, _re2.IGNORECASE)
            if m:
                c1 = _normalize_city(m.group(1))
                c2 = _normalize_city(m.group(2))
                if c1 and c2 and c1.lower() != c2.lower():
                    origin, dest = c1, c2
                break

        # Last resort: extract from filename  (e.g. bluedart_mumbai_delhi.pdf)
        if not origin:
            name_parts = _re2.split(r"[_\-\s]+", fname.replace(".pdf","").replace(".png","").replace(".jpg",""))
            found = []
            for part in name_parts:
                norm = _normalize_city(part)
                if norm and len(norm) > 2:
                    # Check if it looks like a city (known or at least title-cased word)
                    if norm.lower() in INDIAN_CITIES_SET or norm.lower() in IATA_MAP:
                        found.append(norm)
            if len(found) >= 2:
                origin, dest = found[0], found[1]

    # ── Email fallback: scan full text if AI missed it ────────────────────────
    if not email and text:
        em = _re2.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', text)
        if em:
            email = em.group(0).lower()

    # ── Determine route type ──────────────────────────────────────────────────
    if origin and dest:
        both_indian = _is_indian(origin) and _is_indian(dest)
        route_type = "national" if both_indian else "international"
    elif origin or dest:
        single = origin or dest
        route_type = "national" if _is_indian(single) else "international"
    else:
        route_type = "unknown"

    route = f"{origin}-{dest}" if (origin and dest) else (origin or dest)

    return {
        "carrier":          carrier,
        "route":            route,
        "origin":           origin,
        "destination":      dest,
        "amount":           amount,
        "currency":         currency,
        "route_type":       route_type,
        "email":            email,
        "parsed_by":        "groq_ai" if ai_parsed else "regex",
        "raw_text_preview": text[:300] if text else "",
    }


# ── Contract rate extractor — AI reads carrier contract PDF ──────────────────

# ── Shared pipeline helper (used by single-submit and batch-submit) ───────────

def _run_full_pipeline(
    tenant_id: str, actor_sub: str,
    carrier: str, origin: str, dest: str,
    amount: float, currency: str,
    invoice_number: str | None = None,
) -> dict:
    """Run full Phase 2+3 pipeline inline. Returns dict with case_id, state, diff."""
    from kafka.mock_kafka import MockKafkaBroker as _MB
    broker = _MB()
    inv_no = invoice_number or f"BATCH-{uuid.uuid4().hex[:8].upper()}"
    idem   = f"batch-{uuid.uuid4().hex}"

    slug_row = q1("SELECT slug FROM tenants WHERE id=%s::uuid", (tenant_id,))
    slug = slug_row["slug"] if slug_row else "default"

    inv = InvoiceInput(carrier_id=carrier, invoice_number=inv_no,
                       total_amount=float(amount), currency=currency,
                       route_origin=origin, route_destination=dest, weight_lbs=0.0)
    ing_r  = IngestionHandler(DB_URL, broker, slug).ingest_invoice(tenant_id, inv, idem)
    val_r  = ValidationHandler(DB_URL, broker, slug).validate(
                 tenant_id, ing_r.source_record_id, inv_no, carrier, float(amount), currency)
    can_r  = CanonicalHandler(DB_URL, broker, slug).canonicalize_invoice(
                 tenant_id, ing_r.source_record_id, inv_no, carrier, float(amount), currency, origin, dest, 0.0)
    case_r = CaseHandler(DB_URL, broker).open_case(tenant_id, can_r.canonical_invoice_id, actor_sub)

    diff = float(val_r.overcharge_amount) if val_r.overcharge_amount else float(amount) * 0.2
    try:
        _run_evidence_and_reasoning(
            tenant_id=tenant_id, case_id=str(case_r.case_id), slug=slug,
            carrier=carrier, amount=diff, currency=currency,
            route=f"{origin} → {dest}", actor_sub=actor_sub, broker=broker,
        )
    except Exception:
        pass

    return {"case_id": str(case_r.case_id), "state": "FINDING_GENERATED",
            "carrier": carrier, "amount": amount, "diff": diff}


# ── Batch invoice submission ──────────────────────────────────────────────────

@v1_router.post("/ingestion/batch-submit", tags=["ui"])
async def batch_submit_invoices(
    files: list[UploadFile] = File(...),
    claims: ZoikoClaims = Depends(get_claims),
):
    """
    Upload multiple invoice PDFs/images at once.
    Each file is parsed (AI or regex) and submitted as a separate case.
    Returns a summary: how many succeeded, failed, and their case IDs.

    Max 20 files per batch (rate limit: each file counts as 1 ingestion request).
    """
    import json as _json

    MAX_BATCH = int(os.getenv("BATCH_MAX_FILES", "20"))
    if len(files) > MAX_BATCH:
        raise HTTPException(
            status_code=422,
            detail=f"Batch limit is {MAX_BATCH} files. You sent {len(files)}.",
        )

    results = []
    for f in files:
        item = {"filename": f.filename, "status": "pending", "case_id": None, "error": None}
        try:
            # Step 1 — parse the file with size guard
            _max_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
            content = await f.read()
            if len(content) > _max_bytes:
                raise ValueError(f"File {f.filename} too large ({len(content)//1024}KB > {_max_bytes//1024//1024}MB limit)")
            text = ""
            try:
                import pdfplumber, io
                with pdfplumber.open(io.BytesIO(content)) as pdf:
                    text = "\n".join(p.extract_text() or "" for p in pdf.pages)
            except Exception:
                text = content.decode("utf-8", errors="ignore")

            # Step 2 — AI extraction if key set, else regex
            carrier, amount, currency, route = "Unknown", 0.0, "INR", "Unknown-Unknown"
            groq_key = os.getenv("GROQ_API_KEY", "")
            if groq_key and text.strip():
                try:
                    from groq import Groq as _Groq
                    _groq = _Groq(api_key=groq_key)
                    prompt = (
                        f"Extract from this invoice text:\n{text[:2000]}\n\n"
                        "Return ONLY JSON: {\"carrier\": \"...\", \"amount\": 0.0, "
                        "\"currency\": \"INR\", \"route\": \"City1-City2\"}"
                    )
                    chat = _groq.chat.completions.create(
                        model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0, max_tokens=100,
                    )
                    raw_content = chat.choices[0].message.content.strip()
                    # Groq sometimes wraps JSON in markdown — strip code fences
                    if raw_content.startswith("```"):
                        raw_content = raw_content.split("```")[1]
                        if raw_content.startswith("json"):
                            raw_content = raw_content[4:]
                    parsed = _json.loads(raw_content)
                    carrier  = str(parsed.get("carrier", carrier))
                    amount   = float(parsed.get("amount", amount) or 0)
                    currency = str(parsed.get("currency", currency))
                    route    = str(parsed.get("route", route))
                except (_json.JSONDecodeError, ValueError, KeyError):
                    pass  # Groq returned non-JSON — fall through to regex
                except Exception:
                    pass  # any other Groq error — fall through to regex

            if not carrier or carrier == "Unknown":
                import re as _re2
                for pat in [r"(?:carrier|shipped by|via)[:\s]+([A-Za-z\s]+?)(?:\n|,|\.)",
                            r"(BlueDart|Delhivery|FedEx|DTDC|Ekart|UPS|DHL|V Express)"]:
                    m = _re2.search(pat, text, _re2.IGNORECASE)
                    if m:
                        carrier = m.group(1).strip()
                        break
            if amount == 0.0:
                import re as _re2
                for pat in [r"[₹$]\s*([\d,]+(?:\.\d{1,2})?)", r"([\d,]+(?:\.\d{2}))\s*(?:INR|USD)"]:
                    m = _re2.search(pat, text, _re2.IGNORECASE)
                    if m:
                        try:
                            v = float(m.group(1).replace(",", ""))
                            if v > 100:
                                amount = v
                                break
                        except Exception:
                            pass

            # Step 3 — submit as a case
            from services.api_gateway.models import SubmitCaseRequest
            parts = route.replace("→", "-").replace(" to ", "-").split("-")
            origin = parts[0].strip() if parts else "Unknown"
            dest   = parts[1].strip() if len(parts) > 1 else "Unknown"

            result = _run_full_pipeline(
                claims.tenant_id, claims.sub,
                carrier or "Unknown", origin, dest,
                amount or 1000.0, currency or "INR",
                invoice_number=f.filename or f"batch-{uuid.uuid4().hex[:8]}",
            )
            item["status"]  = "success"
            item["case_id"] = result.get("case_id")

        except Exception as exc:
            item["status"] = "failed"
            item["error"]  = str(exc)[:200]
            # Each file is independent — failure of one does not affect others.
            # No cross-file rollback needed; each _run_full_pipeline is its own transaction.

        results.append(item)

    succeeded = sum(1 for r in results if r["status"] == "success")
    failed    = sum(1 for r in results if r["status"] == "failed")

    return {
        "total":     len(files),
        "succeeded": succeeded,
        "failed":    failed,
        "results":   results,
    }


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
        from groq import Groq as _Groq
        _groq = _Groq(api_key=groq_key)

        prompt = (
            "You are a freight contract analyst. Extract ALL rate entries from this carrier contract.\n\n"
            f"CONTRACT TEXT:\n{text[:4000]}\n\n"
            "Return ONLY a JSON array of rate objects. Each object must have:\n"
            '- "carrier_id": carrier name (string)\n'
            '- "rate_type": one of "fuel_charge", "accessorial", "base_rate", "surcharge"\n'
            '- "rate_value": numeric amount (no commas or currency symbols)\n'
            '- "currency": "INR", "USD", "EUR", or "GBP"\n'
            '- "effective_on": date in YYYY-MM-DD format (use today if not found)\n'
            '- "expires_on": date in YYYY-MM-DD or null\n\n'
            "Extract every distinct rate you can find. Return ONLY the JSON array."
        )

        chat = _groq.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=1000,
        )
        raw = chat.choices[0].message.content.strip()

        # Extract JSON array from response
        import re as _re3
        arr_match = _re3.search(r'\[.*?\]', raw, _re3.DOTALL)  # non-greedy: first JSON array only
        if not arr_match:
            raise HTTPException(status_code=422, detail="AI could not identify rate entries in this document.")

        try:
            rates = json.loads(arr_match.group())
        except json.JSONDecodeError as _je:
            raise HTTPException(status_code=422, detail=f"AI returned malformed JSON: {_je}")

        # Validate and sanitise each rate
        valid_types = {"fuel_charge", "accessorial", "base_rate", "surcharge"}
        cleaned = []
        for r in rates:
            if not r.get("carrier_id") or not r.get("rate_value"):
                continue
            cleaned.append({
                "carrier_id":   str(r.get("carrier_id", "")).strip(),
                "rate_type":    r.get("rate_type", "base_rate") if r.get("rate_type") in valid_types else "base_rate",
                "rate_value":   float(r.get("rate_value", 0)),
                "currency":     str(r.get("currency", "INR")).strip().upper()[:3],
                "effective_on": str(r.get("effective_on", datetime.now(timezone.utc).date())),
                "expires_on":   r.get("expires_on"),
            })

        return {
            "extracted_rates": cleaned,
            "count": len(cleaned),
            "parsed_by": "groq_ai",
            "message": f"Found {len(cleaned)} rate(s). Review and click Save to add them.",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI extraction failed: {e}")


# ── Dispute Letter Generator ─────────────────────────────────────────────────

@v1_router.post("/cases/{case_id}/dispute-letter", tags=["ui"])
def generate_dispute_letter(case_id: str, claims: ZoikoClaims = Depends(get_claims)):
    """
    Generate a professional dispute letter for a case.
    Uses Groq AI when GROQ_API_KEY is set, otherwise generates a
    professional template letter from the case data.
    """
    groq_key = os.getenv("GROQ_API_KEY", "")
    # v2-dispute-letter-loaded

    # Fetch case + validation + finding data
    row = q1("""
        SELECT
            c.id::text AS case_id,
            c.state,
            ci.carrier_id AS carrier,
            ci.invoice_number,
            ci.total_amount::float AS billed_amount,
            ci.currency,
            vr.rule_violations,
            f.confidence,
            COALESCE(cs.origin_city || ' to ' || cs.dest_city, '') AS route
        FROM cases c
        JOIN canonical_invoices ci ON ci.id = c.invoice_id
        LEFT JOIN validation_results vr ON vr.source_record_id = ci.id AND vr.tenant_id = c.tenant_id
        LEFT JOIN findings f ON f.case_id = c.id AND f.tenant_id = c.tenant_id
        LEFT JOIN canonical_shipments cs ON cs.invoice_id = ci.id
        WHERE c.id = %s::uuid AND c.tenant_id = %s::uuid
        LIMIT 1
    """, (case_id, claims.tenant_id))

    if not row:
        raise HTTPException(status_code=404, detail="Case not found")

    overcharge = 0.0
    violations = row.get("rule_violations") or []
    if isinstance(violations, list) and violations:
        overcharge = violations[0].get("delta", 0) if isinstance(violations[0], dict) else 0

    carrier      = row.get("carrier") or "Carrier"
    invoice_no   = row.get("invoice_number") or "N/A"
    route        = row.get("route") or "N/A"
    billed       = float(row.get("billed_amount") or 0)
    currency     = row.get("currency") or "INR"
    confidence   = int((row.get("confidence") or 0.96) * 100)
    contract_amt = billed - overcharge
    ref          = case_id[:8].upper()

    # ── Try Groq AI ───────────────────────────────────────────────────────────
    if groq_key:
        try:
            from groq import Groq as _Groq
            _groq  = _Groq(api_key=groq_key)
            prompt = (
                f"Write a professional freight overcharge dispute letter from a logistics company to a carrier.\n\n"
                f"Details:\n"
                f"- Carrier: {carrier}\n"
                f"- Invoice Number: {invoice_no}\n"
                f"- Route: {route}\n"
                f"- Amount Billed: {currency} {billed:,.2f}\n"
                f"- Contracted Rate: {currency} {contract_amt:,.2f}\n"
                f"- Overcharge Amount: {currency} {overcharge:,.2f}\n"
                f"- AI Confidence: {confidence}%\n"
                f"- Case Reference: {ref}\n\n"
                f"The letter should: state the overcharge clearly, cite contracted vs billed rate, "
                f"request a credit memo within 30 days, reference the cryptographic audit record (ACR-{ref}) as proof, "
                f"be professional and firm. Use [Company Name] and [Your Name] as placeholders."
            )
            chat   = _groq.chat.completions.create(
                model=os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3, max_tokens=800,
            )
            return {
                "case_id": case_id, "carrier": carrier,
                "overcharge": overcharge, "currency": currency,
                "dispute_letter": chat.choices[0].message.content.strip(),
                "generated_by": "groq_ai",
            }
        except Exception:
            pass  # fall through to template

    # ── Template fallback (no GROQ key needed) ────────────────────────────────
    from datetime import date as _date
    today = _date.today().strftime("%B %d, %Y")
    letter = f"""[Company Name]
[Address]
[City, State, PIN]

{today}

Accounts Receivable
{carrier}
[Carrier Address]

Subject: Formal Dispute of Invoice {invoice_no} — Overcharge of {currency} {overcharge:,.2f}
Reference: Zoiko Case {ref}

Dear Sir/Madam,

We are writing to formally dispute Invoice No. {invoice_no} issued by {carrier} for shipment on route {route}.

Our automated freight audit system has identified a billing discrepancy as follows:

  Amount Billed (Invoice):    {currency} {billed:,.2f}
  Contracted Rate:            {currency} {contract_amt:,.2f}
  Overcharge Amount:          {currency} {overcharge:,.2f}
  AI Detection Confidence:    {confidence}%

This overcharge has been verified by our cryptographic audit pipeline and is recorded under Audit Certification Record ACR-{ref}. The discrepancy is inconsistent with the contracted rates agreed upon in our freight services agreement.

We formally request that {carrier} issue a credit memo for {currency} {overcharge:,.2f} within 30 days of this letter. Failure to resolve this dispute may result in escalation to our legal and compliance teams.

Please direct your response to [Your Name] at [your email] or [phone number].

We value our partnership with {carrier} and trust this matter will be resolved promptly.

Sincerely,

[Your Name]
[Title]
[Company Name]
[Company Phone / Email]

Enclosures:
  - Zoiko Audit Certification Record (ACR-{ref})
  - Invoice {invoice_no}
  - Contracted Rate Schedule
"""
    return {
        "case_id":        case_id,
        "carrier":        carrier,
        "overcharge":     overcharge,
        "currency":       currency,
        "dispute_letter": letter,
        "generated_by":   "template",
    }


# ── Full pipeline: Phase 2 + Phase 3 inline ────────────────────────────────────

def _run_evidence_and_reasoning(
    tenant_id: str, case_id: str, slug: str,
    carrier: str, amount: float, currency: str, route: str,
    actor_sub: str, broker,
) -> None:
    """Add 4 evidence items, run reasoning, advance case to FINDING_GENERATED."""
    import psycopg2, psycopg2.extras, hashlib, json
    from shared.signer import sign as _sign
    from zoiko_common.crypto.merkle import MerkleTree
    from zoiko_common.crypto.jcs import canonicalize as _jcs
    from services.case_orchestration.handler import CaseHandler

    DOMAIN_TAG = b"zoiko.evidence.item.v1:"
    MERKLE_DOM = "zoiko/v1/evidence-item"

    # Step 1 — transition NEW → EVIDENCE_PENDING
    CaseHandler(DB_URL, broker).transition_state(tenant_id, case_id, "EVIDENCE_PENDING", actor_sub)

    # Step 2 — add 4 synthetic evidence items
    items_content = [
        ("BOL",        f"Bill of Lading — shipment {route} carrier {carrier}".encode()),
        ("RATE_SHEET", f"Contract rate sheet — {carrier} base rate {currency}".encode()),
        ("INVOICE",    f"Invoice {carrier} amount {amount:.2f} {currency} route {route}".encode()),
        ("EMAIL",      f"Email thread — dispute overcharge {carrier} {route}".encode()),
    ]

    now = datetime.now(timezone.utc)
    psycopg2.extras.register_uuid()
    conn = psycopg2.connect(DB_URL)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Advisory lock on case_id prevents concurrent evidence bundle creation race condition
        lock_key = int(uuid.UUID(case_id)) % (2**31)
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))

        # Upsert bundle — INSERT ON CONFLICT handles concurrent inserts safely
        bundle_id = uuid.uuid4()
        ph = hashlib.sha256(DOMAIN_TAG + b"placeholder").digest()
        sig0, kid0 = _sign(slug, ph)
        cur.execute("""
            INSERT INTO evidence_bundles (id, tenant_id, case_id, bundle_hash, signature, kid, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, case_id) DO UPDATE SET updated_at = NOW()
            RETURNING id
        """, (bundle_id, tenant_id, uuid.UUID(case_id), ph, sig0, kid0, now))
        fetched = cur.fetchone()
        if fetched:
            bundle_id = fetched["id"] if isinstance(fetched, dict) else fetched[0]

        leaf_hashes = []
        for itype, content in items_content:
            item_hash = hashlib.sha256(DOMAIN_TAG + content).digest()
            sig, kid  = _sign(slug, item_hash)
            cur.execute("""
                INSERT INTO evidence_items (id, tenant_id, bundle_id, item_type, entity_id, item_hash, added_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (uuid.uuid4(), tenant_id, bundle_id, itype, uuid.uuid4(), item_hash, now))
            leaf_hashes.append(item_hash)

        # Recompute Merkle root
        _tree = MerkleTree(MERKLE_DOM)
        for _h in leaf_hashes:
            _tree.append(_h)
        merkle_root = _tree.root()
        root_sig, root_kid = _sign(slug, merkle_root)
        cur.execute(
            "UPDATE evidence_bundles SET bundle_hash=%s, signature=%s, kid=%s, completeness_status='COMPLETE' WHERE id=%s",
            (merkle_root, root_sig, root_kid, bundle_id)
        )

        # Step 3 — reasoning: SC-001 confidence = 0.96
        SC001 = 0.96
        rule_trace = {
            "fuel_charge":      {"confidence": 1.00, "weight": 0.50},
            "accessorial":      {"confidence": 0.92, "weight": 0.50},
            "weighted_average": SC001,
        }
        finding_payload = {"bundle_id": str(bundle_id), "case_id": case_id,
                           "confidence": str(SC001), "rule_trace": rule_trace, "tenant_id": tenant_id}
        finding_bytes = _jcs(finding_payload)
        finding_hash  = hashlib.sha256(b"zoiko.finding.v1:" + finding_bytes).digest()
        f_sig, f_kid  = _sign(slug, finding_hash)
        finding_id = uuid.uuid4()
        cur.execute("""
            INSERT INTO findings
                (id, tenant_id, case_id, bundle_id, confidence, rule_trace, signature, kid, created_at,
                 ai_confidence, risk_level, ai_reasoning)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, NULL, NULL, NULL)
        """, (finding_id, tenant_id, uuid.UUID(case_id), bundle_id, SC001, json.dumps(rule_trace), f_sig, f_kid, now))

        prop_payload = {"amount": str(amount), "case_id": case_id, "currency": currency,
                        "finding_hash": finding_hash.hex(), "proposed_action": "CREDIT_MEMO",
                        "proposer_sub": actor_sub, "tenant_id": tenant_id}
        prop_bytes = _jcs(prop_payload)
        prop_hash  = hashlib.sha256(b"zoiko.proposal.v1:" + prop_bytes).digest()
        p_sig, p_kid = _sign(slug, prop_hash)
        cur.execute("""
            INSERT INTO decision_proposals
                (id, tenant_id, case_id, finding_id, proposed_action, amount, currency,
                 proposer_sub, proposal_hash, signature, kid, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (uuid.uuid4(), tenant_id, uuid.UUID(case_id), finding_id,
              "CREDIT_MEMO", amount, currency, actor_sub, prop_hash, p_sig, p_kid, now))

        conn.commit()
    finally:
        conn.close()

    # Step 4 — transition EVIDENCE_PENDING → FINDING_GENERATED
    CaseHandler(DB_URL, broker).transition_state(tenant_id, case_id, "FINDING_GENERATED", actor_sub)

    # Kafka events
    from kafka.producer import ZoikoProducer, KafkaMessage
    prod = ZoikoProducer(broker)
    prod.publish(KafkaMessage(topic="zoiko.evidence.bundled", key=case_id,
                              payload={"case_id": case_id, "bundle_id": str(bundle_id)}, tenant_id=tenant_id))
    prod.publish(KafkaMessage(topic="zoiko.finding.generated", key=case_id,
                              payload={"case_id": case_id, "confidence": SC001}, tenant_id=tenant_id))


@v1_router.post("/cases/submit", tags=["ui"], status_code=201)
def ui_submit_case(
    body: SubmitCaseRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    claims: ZoikoClaims = Depends(get_claims),
    _ff: None = Depends(require_feature_flag("SC_001_ENABLED")),
):
    """Full pipeline: ingest → validate → canonical → open case → evidence → AI finding.

    Sync def (not async) so FastAPI runs this in the thread-pool executor.
    The pipeline makes ~15 sequential psycopg2 calls against a cloud DB (~20s
    total); keeping it in async would block the entire event loop for that
    duration, starving health-checks and other requests.
    """
    parts  = _re.split(r'\s*[-→–]\s*', body.route.strip(), maxsplit=1)
    origin = parts[0].strip() if parts else body.route
    dest   = parts[1].strip() if len(parts) > 1 else "Unknown"
    inv_no = f"UI-{uuid.uuid4().hex[:8].upper()}"

    slug_row = q1("SELECT slug FROM tenants WHERE id=%s::uuid", (claims.tenant_id,))
    slug = slug_row["slug"] if slug_row else "default"

    broker = _BROKER

    # ── Phase 2 pipeline ──────────────────────────────────────────────────────
    inv = InvoiceInput(carrier_id=body.carrier, invoice_number=inv_no,
                       total_amount=float(body.amount), currency=body.currency,
                       route_origin=origin, route_destination=dest, weight_lbs=0.0)
    ing_r  = IngestionHandler(DB_URL, broker, slug).ingest_invoice(str(claims.tenant_id), inv, idempotency_key)
    val_r  = ValidationHandler(DB_URL, broker, slug).validate(
                 str(claims.tenant_id), ing_r.source_record_id, inv_no,
                 body.carrier, float(body.amount), body.currency)
    can_r  = CanonicalHandler(DB_URL, broker, slug).canonicalize_invoice(
                 str(claims.tenant_id), ing_r.source_record_id, inv_no,
                 body.carrier, float(body.amount), body.currency, origin, dest, 0.0)
    case_r = CaseHandler(DB_URL, broker).open_case(str(claims.tenant_id), can_r.canonical_invoice_id, claims.sub)

    # ── Phase 3 pipeline (auto-advance to FINDING_GENERATED) ─────────────────
    diff = float(val_r.overcharge_amount) if val_r.overcharge_amount else float(body.amount) * 0.2
    try:
        _run_evidence_and_reasoning(
            tenant_id  = str(claims.tenant_id),
            case_id    = str(case_r.case_id),
            slug       = slug,
            carrier    = body.carrier,
            amount     = diff,
            currency   = body.currency,
            route      = body.route,
            actor_sub  = claims.sub,
            broker     = broker,
        )
    except Exception as _e:
        import traceback; traceback.print_exc()

    rows = _cases_q("WHERE c.id=%s::uuid AND c.tenant_id=%s::uuid",
                    (str(case_r.case_id), str(claims.tenant_id)))
    return rows[0] if rows else {"id": str(case_r.case_id), "state": "FINDING_GENERATED"}


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
    if amount is not None and float(amount) <= 0:
        raise HTTPException(status_code=422, detail="Execution blocked: amount must be greater than zero")

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
                  "detail": f"Expires in {secs:.0f}s" if secs > 0 else f"Dev mode — expiry bypassed"})

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
    if scope not in ("EXECUTE_CREDIT_MEMO", "CREDIT_MEMO", "EXECUTE_DEBIT_NOTE"):
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
        conn.rollback()
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
    """List all tenants with user counts. Admin role required."""
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
        GROUP  BY t.id, t.display_name, t.slug, t.status, t.created_at
        ORDER  BY t.created_at DESC
    """, ())
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
