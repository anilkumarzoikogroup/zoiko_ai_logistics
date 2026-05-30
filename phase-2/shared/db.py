import os, threading
from contextlib import contextmanager
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
import psycopg2.extensions
import psycopg2.pool

load_dotenv()

psycopg2.extras.register_uuid()

DB_URL   = os.getenv("DB_URL")
POOL_MIN = int(os.getenv("DB_POOL_MIN", "2"))
POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_lock = threading.Lock()


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        with _lock:
            if _pool is None or _pool.closed:
                _pool = psycopg2.pool.ThreadedConnectionPool(POOL_MIN, POOL_MAX, DB_URL)
    return _pool


@contextmanager
def get_conn(db_url: str = None):
    """Context manager — checks out a connection and returns it to the pool on exit."""
    if db_url and db_url != DB_URL:
        # Non-default URL: open a direct connection (migration scripts etc.)
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        try:
            yield conn
        finally:
            conn.close()
        return

    pool = _get_pool()
    conn = pool.getconn()
    conn.autocommit = False
    try:
        yield conn
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
