"""JWT verification for SC-005 execution gateway."""
import os
from dotenv import load_dotenv
import paths  # noqa: F401
load_dotenv()
from typing import Optional
from fastapi import Header, HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from middleware.oidc.token_verifier import TokenVerifier, TokenExpiredError, TokenInvalidError
from middleware.oidc.claims import ZoikoClaims
from middleware.opa.client import OPAUnavailableError, resolve_opa_client
DEV_SECRET = os.getenv("ZOIKO_DEV_SECRET", "").encode()
ISSUER = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com")
OPA_URL = os.getenv("OPA_URL", "")
ZOIKO_DEV_MODE = os.getenv("ZOIKO_DEV_MODE", "false").lower() == "true"
_security = HTTPBearer(auto_error=False)
_verifier = TokenVerifier(dev_secret=DEV_SECRET, issuer=ISSUER)
_opa = resolve_opa_client(OPA_URL, ZOIKO_DEV_MODE)
def _extract_token(request, credentials):
    if credentials: return credentials.credentials
    token = request.cookies.get("zoiko_jwt")
    if token: return token
    raise HTTPException(status_code=401, detail="Authentication required")
def get_claims(request: Request, x_tenant_id: str = Header(..., alias="X-Tenant-ID"), credentials: Optional[HTTPAuthorizationCredentials] = Security(_security)) -> ZoikoClaims:
    token = _extract_token(request, credentials)
    try: claims = _verifier.verify(token)
    except TokenExpiredError: raise HTTPException(status_code=401, detail="Token expired.")
    except TokenInvalidError as e: raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    except Exception as e: raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")
    if str(claims.tenant_id) != str(x_tenant_id): raise HTTPException(status_code=403, detail="X-Tenant-ID does not match token tenant.")
    try:
        decision = _opa.check_freight_dispute({"sub": claims.sub, "tenant_id": str(claims.tenant_id), "roles": claims.roles, "action": "ACCESS"})
    except OPAUnavailableError as exc: raise HTTPException(status_code=503, detail=str(exc))
    if decision.denied: raise HTTPException(status_code=403, detail=decision.reason())
    return claims
