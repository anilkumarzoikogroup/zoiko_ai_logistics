"""Shared pytest fixtures for Phase 3."""
import pytest
import os
import uuid

import paths  # noqa: F401 — sets up sys.path for Phase 0 + Phase 1


DB_URL = os.getenv("DB_URL", "postgresql://postgres:1234@localhost/zoiko")


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


@pytest.fixture(scope="session")
def test_case(db_url, test_tenant):
    """Returns a case in EVIDENCE_GATHERING state (creates one from a canonical invoice)."""
    import psycopg2, psycopg2.extras
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT id FROM cases WHERE tenant_id=%s AND state='EVIDENCE_GATHERING' LIMIT 1",
        (test_tenant["id"],),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        pytest.skip("No EVIDENCE_GATHERING case found — run Phase 2 pipeline first")
    return {"id": str(row["id"]), "tenant_id": test_tenant["id"]}


@pytest.fixture
def broker():
    from kafka.mock_kafka import MockKafkaBroker
    return MockKafkaBroker()
