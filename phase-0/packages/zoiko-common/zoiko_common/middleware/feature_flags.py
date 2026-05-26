"""
Per-tenant feature flag system (FR-026).

Feature flags control access to experimental or restricted functionality.
The canonical flag for this project is SC_001_ENABLED — only tenants in the
allowlist can submit SC-001 freight overcharge cases.

Storage (in priority order):
  1. ZOIKO_FF_<FLAG_NAME>=tenant_id1,tenant_id2,...  (env var — always loaded)
  2. In-memory allowlist updated via register_flag() at startup

Usage (FastAPI):
  from zoiko_common.middleware.feature_flags import require_feature_flag
  @router.post("/cases/submit")
  def submit(claims=Depends(get_claims), _=Depends(require_feature_flag("SC_001_ENABLED"))):
      ...

Checking programmatically:
  from zoiko_common.middleware.feature_flags import is_enabled
  if is_enabled("SC_001_ENABLED", tenant_id):
      ...
"""
from __future__ import annotations

import os
import logging
from typing import Set

logger = logging.getLogger(__name__)

# In-memory flag store: flag_name → set of allowed tenant_ids
# Empty set = no tenants allowed; None not in store = flag unknown (defaults to allowed in dev)
_FLAGS: dict[str, Set[str]] = {}

# Wildcard sentinel — means all tenants are allowed for this flag
_ALL = "*"


def _load_env_flags() -> None:
    """Load flag allowlists from environment variables at module import time."""
    prefix = "ZOIKO_FF_"
    for key, val in os.environ.items():
        if key.startswith(prefix):
            flag_name = key[len(prefix):]
            if val.strip() == _ALL:
                _FLAGS[flag_name] = {_ALL}
            else:
                _FLAGS[flag_name] = {t.strip() for t in val.split(",") if t.strip()}
            logger.debug("Feature flag loaded: %s → %s", flag_name, _FLAGS[flag_name])


_load_env_flags()


def register_flag(flag_name: str, allowed_tenants: list[str]) -> None:
    """Register or update a feature flag allowlist at runtime."""
    _FLAGS[flag_name] = set(allowed_tenants)


def is_enabled(flag_name: str, tenant_id: str) -> bool:
    """Return True if flag_name is enabled for tenant_id."""
    if flag_name not in _FLAGS:
        # Unknown flags are allowed in dev mode, denied in prod
        dev_mode = os.getenv("ZOIKO_DEV_MODE", "false").lower() == "true"
        return dev_mode
    allowed = _FLAGS[flag_name]
    return _ALL in allowed or tenant_id in allowed


def require_feature_flag(flag_name: str):
    """
    FastAPI dependency factory. Returns a Depends()-compatible callable that
    raises HTTP 403 if the flag is not enabled for the requesting tenant.

    Usage:
      @router.post("/submit")
      def submit(claims=Depends(get_claims), _=Depends(require_feature_flag("SC_001_ENABLED"))):
          ...
    """
    def _check(x_tenant_id: str | None = None) -> None:
        from fastapi import Header as _Header, HTTPException as _HTTPException
        tenant_id = x_tenant_id or ""
        if not is_enabled(flag_name, tenant_id):
            logger.warning("Feature flag %s denied for tenant %s", flag_name, tenant_id)
            raise _HTTPException(
                status_code=403,
                detail={
                    "error": "FEATURE_FLAG_DISABLED",
                    "detail": f"Feature '{flag_name}' is not enabled for this tenant",
                },
            )
    _check.__name__ = f"require_{flag_name}"
    return _check
