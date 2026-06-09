"""
OPA FastAPI middleware — fail-closed on every state-changing request.

Rule 5 (non-negotiable):
  OPA unreachable → 503 Service Unavailable
  Never permit when policy engine is down.

This middleware runs AFTER OIDCMiddleware (tenant context must be attached).
It evaluates zoiko.tenant_isolation for every request.
Individual routes call OPAClient directly for action-specific policies.
"""
from __future__ import annotations

from typing import Callable, Awaitable, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .client import OPAClient, OPAUnavailableError


class OPAMiddleware(BaseHTTPMiddleware):
    """
    Checks tenant isolation on every non-public request.

    Usage:
        app.add_middleware(OIDCMiddleware, ...)  # must come first
        app.add_middleware(OPAMiddleware, opa=OPAClient())
    """

    def __init__(
        self,
        app,
        opa:          OPAClient,
        public_paths: Set[str] | None = None,
        read_methods: Set[str] | None = None,
    ):
        super().__init__(app)
        self._opa     = opa
        self._public  = public_paths or {"/health", "/metrics", "/docs", "/openapi.json"}
        self._reads   = read_methods or {"GET", "HEAD", "OPTIONS"}

    async def dispatch(self, request: Request, call_next: Callable) -> Awaitable:
        if request.url.path in self._public:
            return await call_next(request)

        ctx = getattr(request.state, "tenant_ctx", None)
        if ctx is None:
            return JSONResponse({"error": "No tenant context — OIDCMiddleware required"}, status_code=401)

        # Extract resource tenant from path param or header
        resource_tenant = (
            request.path_params.get("tenant_id")
            or request.headers.get("X-Tenant-ID", "")
        )

        try:
            decision = self._opa.check_tenant_isolation(
                claim_tenant    = ctx.tenant_id,
                resource_tenant = resource_tenant or ctx.tenant_id,
                roles           = ctx.roles,
            )
        except OPAUnavailableError as e:
            return JSONResponse(
                {"error": "Policy engine unavailable — request blocked", "detail": str(e)},
                status_code=503,
            )

        if decision.denied:
            return JSONResponse(
                {"error": "Access denied", "violations": decision.violations},
                status_code=403,
            )

        return await call_next(request)
