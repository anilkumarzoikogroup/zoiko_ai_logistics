"""Shared pytest fixtures for Phase 3."""
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


@pytest.fixture(scope="session")
def test_case(db_url, test_tenant):
    """Returns any open case for the tenant, or creates a fresh one via Phase 2 pipeline."""
    import psycopg2, psycopg2.extras
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    # Prefer cases that Phase 3 hasn't fully processed yet
    cur.execute(
        """SELECT id FROM cases WHERE tenant_id=%s
           AND state IN ('NEW','EVIDENCE_PENDING','FINDING_GENERATED','APPROVAL_PENDING')
           ORDER BY opened_at DESC LIMIT 1""",
        (test_tenant["id"],),
    )
    row = cur.fetchone()
    if not row:
        # No usable case — create one via Phase 2 pipeline
        import sys, os, uuid as _uuid
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "gateway"))
        from services.ingestion_svc.handler   import IngestionHandler
        from services.ingestion_svc.models    import InvoiceInput
        from services.canonical_truth.handler import CanonicalHandler
        from services.case_orchestration.handler import CaseHandler
        from kafka.mock_kafka import MockKafkaBroker
        broker = MockKafkaBroker()
        slug   = test_tenant["slug"]
        tid    = test_tenant["id"]
        inv    = InvoiceInput(carrier_id="TestCarrier", invoice_number=f"TEST-{_uuid.uuid4().hex[:6].upper()}",
                              total_amount=10000.0, currency="INR",
                              route_origin="Test City", route_destination="Other City", weight_lbs=0.0)
        ing_r  = IngestionHandler(db_url, broker, slug).ingest_invoice(tid, inv, str(_uuid.uuid4()))
        can_r  = CanonicalHandler(db_url, broker, slug).canonicalize_invoice(
                     tid, ing_r.source_record_id, inv.invoice_number,
                     inv.carrier_id, inv.total_amount, inv.currency,
                     inv.route_origin, inv.route_destination, 0.0)
        case_r = CaseHandler(db_url, broker).open_case(tid, can_r.canonical_invoice_id, "test-setup")
        conn.close()
        return {"id": str(case_r.case_id), "tenant_id": tid}
    conn.close()
    return {"id": str(row["id"]), "tenant_id": test_tenant["id"]}


@pytest.fixture
def broker():
    from kafka.mock_kafka import MockKafkaBroker
    return MockKafkaBroker()
