"""
OIDC Middleware for FastAPI.

Every incoming request must carry:
  Authorization: Bearer <JWT>
  X-Tenant-ID:   <tenant_uuid>

The middleware:
1. Extracts the Bearer token
2. Verifies the JWT signature (RS256 / ES256) using JWKS
3. Validates exp, iss, aud
4. Checks X-Tenant-ID matches the tenant_id claim (prevents cross-tenant calls)
5. Attaches TenantContext to request.state.tenant_ctx

Fail-safe: any validation failure → 401. No bypass.
Public paths (e.g. /health, /metrics) are configurable skip list.
"""
from __future__ import annotations

from typing import Callable, Awaitable, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .claims import TenantContext
from .token_verifier import TokenVerifier, TokenExpiredError, TokenInvalidError


class OIDCMiddleware(BaseHTTPMiddleware):
    """
    FastAPI/Starlette OIDC middleware.

    Usage in a FastAPI app:
        app.add_middleware(
            OIDCMiddleware,
            verifier=TokenVerifier(jwks_url="https://.../.well-known/jwks.json", audience="ingestion-svc"),
            public_paths={"/health", "/metrics"},
        )
    """

    def __init__(
        self,
        app,
        verifier: "TokenVerifier",
        public_paths: Set[str] | None = None,
        required_audience: str = "*",
    ):
        super().__init__(app)
        self._verifier  = verifier
        self._public    = public_paths or {"/health", "/metrics", "/docs", "/openapi.json"}
        self._audience  = required_audience

    async def dispatch(self, request: Request, call_next: Callable) -> Awaitable:
        if request.url.path in self._public:
            return await call_next(request)

        # Extract Bearer token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"error": "Missing Authorization header"}, status_code=401)

        token = auth_header.removeprefix("Bearer ").strip()

        # Extract X-Tenant-ID header
        header_tenant = request.headers.get("X-Tenant-ID", "")
        if not header_tenant:
            return JSONResponse({"error": "Missing X-Tenant-ID header"}, status_code=401)

        # Verify JWT
        try:
            claims = self._verifier.verify(token, expected_audience=self._audience)
        except TokenExpiredError:
            return JSONResponse({"error": "Token expired"}, status_code=401)
        except TokenInvalidError as e:
            return JSONResponse({"error": f"Invalid token: {e}"}, status_code=401)

        # Tenant binding check — header must match JWT claim
        if claims.tenant_id != header_tenant:
            return JSONResponse(
                {"error": "X-Tenant-ID does not match token tenant_id claim"},
                status_code=403,
            )

        # Attach to request state
        request.state.tenant_ctx = TenantContext(tenant_id=claims.tenant_id, claims=claims)

        return await call_next(request)


