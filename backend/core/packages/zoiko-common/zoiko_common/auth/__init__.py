"""OIDC JWT validation middleware for Zoiko services.

Every state-changing request must carry a Bearer JWT.  The middleware:
  1. Validates the JWT signature against the OIDC provider's JWKS.
  2. Checks iss, aud, exp, iat claims.
  3. Extracts tenant_id from the `zoiko_tenant` custom claim.
  4. Raises HTTP 403 if X-Tenant-ID header != JWT tenant_id (binding check).

The full middleware wiring is done per-service in P2.  This module exposes
the shared token parsing + tenant binding logic so services don't re-implement it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ZoikoClaims:
    sub: str
    tenant_id: str
    email: str | None
    roles: list[str]

    @classmethod
    def from_jwt_payload(cls, payload: dict[str, Any]) -> "ZoikoClaims":
        return cls(
            sub=payload["sub"],
            tenant_id=payload["zoiko_tenant"],
            email=payload.get("email"),
            roles=payload.get("zoiko_roles", []),
        )


class TenantMismatchError(Exception):
    """Raised when X-Tenant-ID header does not match JWT tenant_id."""


def assert_tenant_binding(header_tenant_id: str, claims: ZoikoClaims) -> None:
    """Raise :class:`TenantMismatchError` if the header tenant differs from the JWT."""
    if header_tenant_id != claims.tenant_id:
        raise TenantMismatchError(
            f"X-Tenant-ID={header_tenant_id!r} does not match JWT tenant={claims.tenant_id!r}"
        )
