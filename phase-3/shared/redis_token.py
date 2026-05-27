"""Redis token consumed lock — used by Phase 4 Execution Gateway.

Before Phase 4 moves money, it must atomically mark the governance token
as CONSUMED in Redis (SET NX) to prevent double-execution.

Rules:
  - mark_consumed() uses SET NX (atomic claim) — returns True only once
  - get_status()    returns 'CONSUMED' or None
  - Gracefully no-ops if Redis is unreachable — the DB-level status=CONSUMED
    update is the primary protection; Redis is a fast replay guard on top.
"""
import os
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")
_PREFIX   = "token"
_TTL      = 7 * 24 * 3600   # 7 days — matches WORM retention window

try:
    import redis as _redis_lib
    _client = _redis_lib.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=1)
    _client.ping()
    _AVAILABLE = True
except Exception:
    _client    = None
    _AVAILABLE = False


def _key(token_id: str) -> str:
    return f"{_PREFIX}:consumed:{token_id}"


def mark_consumed(token_id: str) -> bool:
    """Atomically claim the token for execution.

    Returns True  → this caller is the first to consume it (proceed).
    Returns False → token already consumed (duplicate execution blocked).
    Falls back to True if Redis unavailable (DB status=CONSUMED is authoritative).
    """
    if not _AVAILABLE:
        return True
    try:
        acquired = _client.set(_key(token_id), "CONSUMED", nx=True, ex=_TTL)
        return bool(acquired)
    except Exception:
        return True   # Redis down — safe to proceed, DB is authoritative


def get_status(token_id: str) -> str | None:
    """Return 'CONSUMED' or None if not found / Redis unavailable."""
    if not _AVAILABLE:
        return None
    try:
        return _client.get(_key(token_id))
    except Exception:
        return None
