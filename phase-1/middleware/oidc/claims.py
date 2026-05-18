"""
JWT claims model for Zoiko OIDC tokens.

Every service-to-service and user-to-service call carries a JWT with these claims.
The tenant_id claim is the single source of truth for RLS row filtering.

Standard claims (RFC 7519):  sub, iss, aud, exp, iat, jti
Zoiko custom claims:         tenant_id, roles, zoiko_env
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class ZoikoClaims:
    """Decoded, validated JWT claims for a Zoiko request."""
    sub:        str                  # Subject — user or service account ID
    iss:        str                  # Issuer  — OIDC provider URL
    aud:        str                  # Audience — target service name
    exp:        int                  # Expiry  — Unix timestamp
    iat:        int                  # Issued at
    tenant_id:  str                  # Zoiko tenant UUID (custom claim)
    roles:      List[str] = field(default_factory=list)  # e.g. ["analyst", "manager"]
    zoiko_env:  str = "dev"          # dev | staging | prod
    jti:        Optional[str] = None # JWT ID for replay detection

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc).timestamp() > self.exp

    @property
    def is_analyst(self) -> bool:
        return "analyst" in self.roles

    @property
    def is_manager(self) -> bool:
        return "manager" in self.roles

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles

    def has_role(self, role: str) -> bool:
        return role in self.roles

    @classmethod
    def from_dict(cls, payload: dict) -> "ZoikoClaims":
        """Build ZoikoClaims from a decoded JWT payload dict."""
        required = {"sub", "iss", "aud", "exp", "iat", "tenant_id"}
        missing  = required - payload.keys()
        if missing:
            raise ValueError(f"JWT missing required claims: {missing}")
        return cls(
            sub       = payload["sub"],
            iss       = payload["iss"],
            aud       = payload["aud"],
            exp       = int(payload["exp"]),
            iat       = int(payload["iat"]),
            tenant_id = payload["tenant_id"],
            roles     = payload.get("roles", []),
            zoiko_env = payload.get("zoiko_env", "dev"),
            jti       = payload.get("jti"),
        )


@dataclass
class TenantContext:
    """Request-scoped tenant context — injected by OIDCMiddleware into every request."""
    tenant_id:  str
    claims:     ZoikoClaims

    @property
    def sub(self) -> str:
        return self.claims.sub

    @property
    def roles(self) -> list[str]:
        return self.claims.roles
