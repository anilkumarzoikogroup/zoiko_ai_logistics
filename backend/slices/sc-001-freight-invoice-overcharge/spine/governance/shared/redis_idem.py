"""Sync Redis idempotency helper — same pattern as Phase 2.

Gracefully no-ops if Redis is unreachable — DB-level ON CONFLICT guard
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
    if not _AVAILABLE:
        return True
    try:
        acquired = _client.set(_key(tenant_id, idem_key), "IN_PROGRESS", nx=True, ex=_TTL)
        return bool(acquired)
    except Exception:
        return True


def mark_complete(tenant_id: str, idem_key: str) -> None:
    if not _AVAILABLE:
        return
    try:
        _client.set(_key(tenant_id, idem_key), "COMPLETE")
    except Exception:
        pass


def get_status(tenant_id: str, idem_key: str) -> str | None:
    if not _AVAILABLE:
        return None
    try:
        return _client.get(_key(tenant_id, idem_key))
    except Exception:
        return None
