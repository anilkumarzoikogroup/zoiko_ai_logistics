"""Shared pytest fixtures for Phase 2."""
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import pytest
import os
import uuid
from dotenv import load_dotenv

import paths  # noqa: F401 — sets up sys.path for Phase 0 + Phase 1

load_dotenv()

DB_URL = os.getenv("DB_URL")


def _db_available() -> bool:
    try:
        import psycopg2
        conn = psycopg2.connect(DB_URL, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def db_url():
    if not _db_available():
        pytest.skip("PostgreSQL not reachable — skipping integration test")
    return DB_URL


@pytest.fixture(scope="session")
def test_tenant(db_url):
    import psycopg2, psycopg2.extras
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, slug FROM tenants WHERE status='ACTIVE' ORDER BY created_at LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        pytest.skip("No active tenant in DB — run seed_dummy_data.py first")
    return {"id": str(row["id"]), "slug": row["slug"]}


@pytest.fixture
def broker():
    from kafka.mock_kafka import MockKafkaBroker
    return MockKafkaBroker()


@pytest.fixture
def unique_invoice_number():
    return f"TEST-{uuid.uuid4().hex[:8].upper()}"
