"""JWT verification + tenant binding — FastAPI dependency."""
import os
import paths  # noqa: F401

from fastapi import Header, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from middleware.oidc.token_verifier import TokenVerifier, TokenExpiredError, TokenInvalidError
from middleware.oidc.claims import ZoikoClaims

DEV_SECRET = os.getenv("ZOIKO_DEV_SECRET", "zoiko-dev-secret-for-testing-only").encode()
ISSUER     = os.getenv("ZOIKO_ISSUER",     "https://auth.zoikotech.com")

_security = HTTPBearer()
_verifier = TokenVerifier(dev_secret=DEV_SECRET, issuer=ISSUER)


def get_claims(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    credentials: HTTPAuthorizationCredentials = Security(_security),
) -> ZoikoClaims:
    """Validates Bearer token + tenant binding. Used as a FastAPI Depends."""
    try:
        claims = _verifier.verify(credentials.credentials)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Token expired")
    except TokenInvalidError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")

    # Key rule #9: X-Tenant-ID header must match the JWT tenant_id
    if str(claims.tenant_id) != str(x_tenant_id):
        raise HTTPException(
            status_code=403,
            detail=f"X-Tenant-ID '{x_tenant_id}' does not match JWT tenant_id '{claims.tenant_id}'"
        )
    return claims
