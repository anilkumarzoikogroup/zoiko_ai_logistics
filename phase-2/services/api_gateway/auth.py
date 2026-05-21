"""JWT verification + tenant binding + OPA authorization — FastAPI dependency."""
import os
import paths  # noqa: F401

from fastapi import Header, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from middleware.oidc.token_verifier import TokenVerifier, TokenExpiredError, TokenInvalidError
from middleware.oidc.claims import ZoikoClaims
from middleware.opa.client import OPAClient, MockOPAClient, OPAUnavailableError

DEV_SECRET = os.getenv("ZOIKO_DEV_SECRET", "zoiko-dev-secret-for-testing-only").encode()
ISSUER     = os.getenv("ZOIKO_ISSUER",     "https://auth.zoikotech.com")
DEV_MODE   = os.getenv("ZOIKO_DEV_MODE",   "false").lower() == "true"
OPA_URL    = os.getenv("OPA_URL", "")

_security = HTTPBearer(auto_error=not DEV_MODE)
_verifier = TokenVerifier(dev_secret=DEV_SECRET, issuer=ISSUER)
# Use real OPA only when OPA_URL is explicitly set; otherwise MockOPAClient (allow=True)
_opa      = OPAClient(OPA_URL) if OPA_URL else MockOPAClient()


def get_claims(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    credentials: HTTPAuthorizationCredentials = Security(_security),
) -> ZoikoClaims:
    """Validates Bearer token + tenant binding + OPA policy. Used as a FastAPI Depends."""
    if DEV_MODE:
        import time as _t
        from shared.db import q1 as _q1
        import psycopg2 as _pg, uuid as _uuid
        # Try exact match first, then fall back to any active tenant
        row = _q1(
            "SELECT id, slug FROM tenants WHERE slug=%s OR id::text=%s",
            (x_tenant_id, x_tenant_id),
        )
        if not row:
            row = _q1("SELECT id, slug FROM tenants WHERE status='ACTIVE' ORDER BY created_at LIMIT 1")
        if not row:
            # Seed a dev tenant on first run
            tid = _uuid.uuid4()
            conn = _pg.connect(os.getenv("DB_URL", "postgresql://postgres:1234@localhost/zoiko"))
            try:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO tenants (id, slug, display_name, status) VALUES (%s,%s,%s,'ACTIVE')",
                    (tid, "amazon-india", "Amazon India"),
                )
                conn.commit()
            finally:
                conn.close()
            row = {"id": str(tid), "slug": "amazon-india"}
        now = int(_t.time())
        claims = ZoikoClaims(
            sub="dev-user", iss=ISSUER, aud="zoiko-dev",
            exp=now + 86400, iat=now,
            tenant_id=str(row["id"]),
            roles=["analyst", "manager", "admin"],
            zoiko_env="dev",
        )
    else:
        try:
            claims = _verifier.verify(credentials.credentials)
        except TokenExpiredError:
            raise HTTPException(status_code=401, detail="Token expired")
        except TokenInvalidError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")

        if str(claims.tenant_id) != str(x_tenant_id):
            raise HTTPException(
                status_code=403,
                detail=f"X-Tenant-ID '{x_tenant_id}' does not match JWT tenant_id '{claims.tenant_id}'"
            )

    # OPA authorization check — fail-closed: 503 if OPA unreachable (rule 5)
    try:
        decision = _opa.check_freight_dispute({
            "sub":       claims.sub,
            "tenant_id": str(claims.tenant_id),
            "roles":     claims.roles,
            "action":    "ACCESS",
        })
    except OPAUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if decision.denied:
        raise HTTPException(status_code=403, detail=decision.reason())

    return claims
