"""
FastAPI dependency helpers for tenant context.

Usage in a FastAPI route:
    @router.get("/cases")
    async def list_cases(ctx: TenantContext = Depends(require_tenant)):
        # ctx.tenant_id is guaranteed to be set and verified
        return db.query(Case).filter_by(tenant_id=ctx.tenant_id).all()
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from .claims import TenantContext


def get_tenant_ctx(request: Request) -> TenantContext:
    """
    FastAPI dependency — returns the TenantContext set by OIDCMiddleware.
    Raises 401 if middleware didn't attach it (should never happen in production).
    """
    ctx = getattr(request.state, "tenant_ctx", None)
    if ctx is None:
        raise HTTPException(status_code=401, detail="No tenant context — is OIDCMiddleware loaded?")
    return ctx


def require_tenant(ctx: TenantContext = Depends(get_tenant_ctx)) -> TenantContext:
    """Alias for get_tenant_ctx — makes route intent explicit."""
    return ctx


def require_role(role: str):
    """
    FastAPI dependency factory — ensures the caller has a specific role.

    Usage:
        @router.post("/approve")
        async def approve(ctx: TenantContext = Depends(require_role("manager"))):
            ...
    """
    def _check(ctx: TenantContext = Depends(require_tenant)) -> TenantContext:
        if not ctx.claims.has_role(role):
            raise HTTPException(
                status_code=403,
                detail=f"Role '{role}' required. Your roles: {ctx.roles}",
            )
        return ctx
    return _check
