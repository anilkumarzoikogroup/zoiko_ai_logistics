"""Phase 4 test fixtures — mirrors phase-2/conftest.py pattern."""
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import os
import uuid
import pytest
from dotenv import load_dotenv
import paths  # noqa: F401

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
        pytest.skip("PostgreSQL not reachable")
    return DB_URL


@pytest.fixture(scope="session")
def test_tenant(db_url):
    import psycopg2, psycopg2.extras
    psycopg2.extras.register_uuid()
    conn = psycopg2.connect(db_url)
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    slug = f"p4-test-{uuid.uuid4().hex[:6]}"
    tid  = uuid.uuid4()
    cur.execute(
        "INSERT INTO tenants (id, slug, display_name, created_at) "
        "VALUES (%s, %s, %s, NOW()) ON CONFLICT (slug) DO NOTHING",
        (tid, slug, f"Phase 4 Test {slug}"),
    )
    conn.commit()
    cur.execute("SELECT id, slug FROM tenants WHERE slug=%s LIMIT 1", (slug,))
    row = cur.fetchone()
    conn.close()
    return {"id": str(row["id"]), "slug": row["slug"]}


@pytest.fixture(scope="session")
def broker():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "platform"))
    from kafka.mock_kafka import MockKafkaBroker
    return MockKafkaBroker()
