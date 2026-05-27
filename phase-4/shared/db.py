import os
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
import psycopg2.extensions

load_dotenv()

psycopg2.extras.register_uuid()

DB_URL = os.getenv("DB_URL")


def get_conn(db_url: str = None) -> psycopg2.extensions.connection:
    conn = psycopg2.connect(db_url or DB_URL)
    conn.autocommit = False
    return conn


def q(sql: str, params=None, db_url: str = None) -> list[dict]:
    conn = psycopg2.connect(db_url or DB_URL)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def q1(sql: str, params=None, db_url: str = None) -> dict | None:
    rows = q(sql, params, db_url)
    return rows[0] if rows else None
