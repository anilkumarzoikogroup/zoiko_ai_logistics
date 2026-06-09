"""JWT verification + tenant binding + OPA authorization — FastAPI dependency."""
import os
from dotenv import load_dotenv
import paths  # noqa: F401

load_dotenv()

from fastapi import Header, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from middleware.oidc.token_verifier import TokenVerifier, TokenExpiredError, TokenInvalidError
from middleware.oidc.claims import ZoikoClaims
from middleware.opa.client import OPAClient, MockOPAClient, OPAUnavailableError

DEV_SECRET = os.getenv("ZOIKO_DEV_SECRET", "").encode()
ISSUER     = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com")
OPA_URL    = os.getenv("OPA_URL", "")

_security = HTTPBearer(auto_error=True)
_verifier = TokenVerifier(dev_secret=DEV_SECRET, issuer=ISSUER)
_opa      = OPAClient(OPA_URL) if OPA_URL else MockOPAClient()


def get_claims(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    credentials: HTTPAuthorizationCredentials = Security(_security),
) -> ZoikoClaims:
    """Validates Bearer token + tenant binding + OPA policy."""
    try:
        claims = _verifier.verify(credentials.credentials)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Token expired. Please log in again.")
    except TokenInvalidError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")

    if str(claims.tenant_id) != str(x_tenant_id):
        raise HTTPException(status_code=403, detail="X-Tenant-ID does not match token tenant.")

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
