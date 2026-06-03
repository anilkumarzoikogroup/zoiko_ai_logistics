import os, threading
from contextlib import contextmanager
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
import psycopg2.extensions
import psycopg2.pool

load_dotenv(override=True)  # .env always wins over shell env vars

psycopg2.extras.register_uuid()

DB_URL   = os.getenv("DB_URL")
POOL_MIN = int(os.getenv("DB_POOL_MIN", "2"))
POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_lock = threading.Lock()


def _make_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Create pool with TCP keepalives so Neon never silently drops idle connections."""
    # Neon serverless closes idle connections after ~300s.
    # keepalives_idle=60 sends the first probe after 60s of silence,
    # well before Neon's timeout, keeping the connection alive indefinitely.
    return psycopg2.pool.ThreadedConnectionPool(
        POOL_MIN, POOL_MAX, DB_URL,
        keepalives=1,
        keepalives_idle=60,
        keepalives_interval=10,
        keepalives_count=5,
    )


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        with _lock:
            if _pool is None or _pool.closed:
                _pool = _make_pool()
    return _pool


def _reset_pool() -> None:
    """Force-recreate the connection pool (called when connections are found broken)."""
    global _pool
    with _lock:
        if _pool and not _pool.closed:
            try:
                _pool.closeall()
            except Exception:
                pass
        _pool = _make_pool()


@contextmanager
def get_conn(db_url: str = None):
    """Checkout a connection; heals stale pool connections automatically."""
    if db_url and db_url != DB_URL:
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        try:
            yield conn
        finally:
            conn.close()
        return

    pool = _get_pool()
    conn = pool.getconn()

    # Ping the connection; replace it if Neon closed it while idle
    try:
        if conn.closed:
            raise psycopg2.OperationalError("connection closed")
        conn.cursor().execute("SELECT 1")
    except Exception:
        pool.putconn(conn, close=True)
        try:
            conn = pool.getconn()
            conn.cursor().execute("SELECT 1")
        except Exception:
            # Whole pool is dead — recreate it
            _reset_pool()
            pool = _get_pool()
            conn = pool.getconn()

    conn.autocommit = False
    try:
        yield conn
    except Exception:
        # Roll back any open transaction before returning to pool
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        pool.putconn(conn)


def q(sql: str, params=None, db_url: str = None) -> list[dict]:
    with get_conn(db_url) as conn:
        conn.autocommit = True
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.autocommit = False
    return [dict(r) for r in rows]


def q1(sql: str, params=None, db_url: str = None) -> dict | None:
    rows = q(sql, params, db_url)
    return rows[0] if rows else None
