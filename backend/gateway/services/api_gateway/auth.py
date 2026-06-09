"""JWT verification + tenant binding + OPA authorization — FastAPI dependency."""
import os
from dotenv import load_dotenv
import paths  # noqa: F401

load_dotenv()

from typing import Optional
from fastapi import Header, HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from middleware.oidc.token_verifier import TokenVerifier, TokenExpiredError, TokenInvalidError
from middleware.oidc.claims import ZoikoClaims
from middleware.opa.client import OPAClient, MockOPAClient, OPAUnavailableError

DEV_SECRET = os.getenv("ZOIKO_DEV_SECRET", "").encode()
ISSUER     = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com")
OPA_URL    = os.getenv("OPA_URL", "")

# auto_error=False so we can fall back to the HttpOnly cookie when no Bearer header is sent
_security = HTTPBearer(auto_error=False)
_verifier = TokenVerifier(dev_secret=DEV_SECRET, issuer=ISSUER)
_opa      = OPAClient(OPA_URL) if OPA_URL else MockOPAClient()


def _extract_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> str:
    """Bearer header takes priority; falls back to HttpOnly cookie."""
    if credentials:
        return credentials.credentials
    token = request.cookies.get("zoiko_jwt")
    if token:
        return token
    raise HTTPException(status_code=401, detail="Authentication required")


def get_claims(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_security),
) -> ZoikoClaims:
    """Validates Bearer token (or HttpOnly cookie) + tenant binding + OPA policy."""
    token = _extract_token(request, credentials)
    try:
        claims = _verifier.verify(token)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Token expired. Please log in again.")
    except TokenInvalidError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")

    if str(claims.tenant_id) != str(x_tenant_id):
        raise HTTPException(
            status_code=403,
            detail="X-Tenant-ID does not match token tenant."
        )

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


def get_claims_by_cookie(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_security),
) -> ZoikoClaims:
    """For /auth/me only: verify token from cookie or Bearer header — no X-Tenant-ID or OPA check.
    Used for session restoration when the frontend doesn't yet know the tenant ID."""
    token = _extract_token(request, credentials)
    try:
        return _verifier.verify(token)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Token expired. Please log in again.")
    except TokenInvalidError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")
