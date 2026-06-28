"""Redis token consumed lock — prevents duplicate execution for SC-005."""
import os
from dotenv import load_dotenv
load_dotenv()
REDIS_URL = os.getenv("REDIS_URL")
_PREFIX   = "token"
_TTL      = 7 * 24 * 3600
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
    if not _AVAILABLE: return True
    try:
        acquired = _client.set(_key(token_id), "CONSUMED", nx=True, ex=_TTL)
        return bool(acquired)
    except Exception: return True
def get_status(token_id: str):
    if not _AVAILABLE: return None
    try: return _client.get(_key(token_id))
    except Exception: return None
