"""Sync Redis idempotency helper — wraps zoiko_common.idempotency pattern.

Step 5 of the ingestion write pattern (called AFTER the DB commit):
  mark_in_progress() → False means duplicate, skip
  mark_complete()    → permanent COMPLETE flag, no TTL

Gracefully no-ops if Redis is unreachable — the DB-level ON CONFLICT guard
is the primary idempotency protection; Redis is a fast replay cache on top.
"""
import os
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")
_PREFIX   = "idempotency"
_TTL      = 86_400   # 24 h

try:
    import redis as _redis_lib
    _client = _redis_lib.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=1)
    _client.ping()
    _AVAILABLE = True
except Exception:
    _client    = None
    _AVAILABLE = False


def _key(tenant_id: str, idem_key: str) -> str:
    return f"{_PREFIX}:{tenant_id}:{idem_key}"


def mark_in_progress(tenant_id: str, idem_key: str) -> bool:
    """Try to claim the idempotency key.

    Returns True  → key acquired (first request, proceed normally).
    Returns False → key already exists (duplicate, caller should short-circuit).
    Falls back to True if Redis is unavailable (DB-level guard still protects).
    """
    if not _AVAILABLE:
        return True
    try:
        acquired = _client.set(_key(tenant_id, idem_key), "IN_PROGRESS", nx=True, ex=_TTL)
        return bool(acquired)
    except Exception:
        return True   # Redis down — safe to proceed, DB is authoritative


def mark_complete(tenant_id: str, idem_key: str) -> None:
    """Permanently mark the key COMPLETE (no TTL — survives forever)."""
    if not _AVAILABLE:
        return
    try:
        _client.set(_key(tenant_id, idem_key), "COMPLETE")
    except Exception:
        pass   # Redis down — safe, DB record is source of truth


def get_status(tenant_id: str, idem_key: str) -> str | None:
    """Return 'IN_PROGRESS', 'COMPLETE', or None if not found / Redis unavailable."""
    if not _AVAILABLE:
        return None
    try:
        return _client.get(_key(tenant_id, idem_key))
    except Exception:
        return None
