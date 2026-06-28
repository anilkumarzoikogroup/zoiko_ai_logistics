"""JWT auth for SC-004 execution gateway — mirrors SC-003 execution auth."""
import os
import jwt
from fastapi import Header, HTTPException, status
from dotenv import load_dotenv

load_dotenv()

_DEV_MODE   = os.getenv("ZOIKO_DEV_MODE", "false").lower() == "true"
_DEV_SECRET = os.getenv("ZOIKO_DEV_SECRET", "zoiko-dev-secret-for-testing-only")
_ISSUER     = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com")
_ALGORITHMS  = ["HS256"]


def require_auth(
    authorization: str = Header(...),
    x_tenant_id:   str = Header(...),
) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        if _DEV_MODE:
            claims = jwt.decode(token, _DEV_SECRET, algorithms=_ALGORITHMS, options={"verify_exp": False})
        else:
            claims = jwt.decode(token, _DEV_SECRET, algorithms=_ALGORITHMS, issuer=_ISSUER)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return {**claims, "tenant_id": x_tenant_id}
