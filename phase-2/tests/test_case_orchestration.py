"""Tests for case_orchestration."""
import uuid
import pytest
import paths  # noqa: F401
from services.case_orchestration.handler import CaseHandler


def _setup_canonical(db_url, broker, tenant, inv_no):
    """Run ingestion + canonical_truth to get a canonical_invoice_id."""
    from services.ingestion_svc.handler import IngestionHandler
    from services.ingestion_svc.models import InvoiceInput
    from services.canonical_truth.handler import CanonicalHandler

    ing = IngestionHandler(db_url, broker, tenant["slug"]).ingest_invoice(
        tenant["id"],
        InvoiceInput("DHL", inv_no, 220.0, "USD", "Dallas", "Atlanta"),
    )
    result = CanonicalHandler(db_url, broker, tenant["slug"]).canonicalize_invoice(
        tenant_id=tenant["id"], source_record_id=ing.source_record_id,
        invoice_number=inv_no, carrier_id="DHL",
        total_amount=220.0, currency="USD",
        origin_city="Dallas", dest_city="Atlanta",
    )
    return result.canonical_invoice_id


class TestCaseOrchestrationIntegration:
    def test_open_case_inserts_row(self, db_url, broker, test_tenant, unique_invoice_number):
        import psycopg2
        inv_id = _setup_canonical(db_url, broker, test_tenant, unique_invoice_number)
        h      = CaseHandler(db_url, broker)
        result = h.open_case(test_tenant["id"], inv_id)

        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor()
        cur.execute("SELECT state FROM cases WHERE id=%s", (result.case_id,))
        row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "NEW"

    def test_case_event_appended_on_open(self, db_url, broker, test_tenant, unique_invoice_number):
        import psycopg2
        inv_id = _setup_canonical(db_url, broker, test_tenant, unique_invoice_number)
        h      = CaseHandler(db_url, broker)
        result = h.open_case(test_tenant["id"], inv_id)

        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor()
        cur.execute(
            "SELECT event_type, to_state FROM case_events WHERE case_id=%s",
            (result.case_id,),
        )
        rows = cur.fetchall()
        conn.close()
        assert any(r[0] == "CASE_OPENED" and r[1] == "NEW" for r in rows)

    def test_transition_updates_state(self, db_url, broker, test_tenant, unique_invoice_number):
        import psycopg2
        inv_id = _setup_canonical(db_url, broker, test_tenant, unique_invoice_number)
        h      = CaseHandler(db_url, broker)
        result = h.open_case(test_tenant["id"], inv_id)
        h.transition_state(test_tenant["id"], result.case_id, "EVIDENCE_PENDING", "system")

        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor()
        cur.execute("SELECT state FROM cases WHERE id=%s", (result.case_id,))
        assert cur.fetchone()[0] == "EVIDENCE_PENDING"
        conn.close()

    def test_transition_appends_case_event(self, db_url, broker, test_tenant, unique_invoice_number):
        import psycopg2
        inv_id = _setup_canonical(db_url, broker, test_tenant, unique_invoice_number)
        h      = CaseHandler(db_url, broker)
        result = h.open_case(test_tenant["id"], inv_id)
        h.transition_state(test_tenant["id"], result.case_id, "EVIDENCE_PENDING", "alice@zoikotech.com")

        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor()
        cur.execute(
            "SELECT from_state, to_state, actor_sub FROM case_events "
            "WHERE case_id=%s AND event_type='TRANSITION_EVIDENCE_PENDING'",
            (result.case_id,),
        )
        row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "NEW"
        assert row[1] == "EVIDENCE_PENDING"
        assert row[2] == "alice@zoikotech.com"

    def test_invalid_transition_raises(self, db_url, broker, test_tenant, unique_invoice_number):
        inv_id = _setup_canonical(db_url, broker, test_tenant, unique_invoice_number)
        h      = CaseHandler(db_url, broker)
        result = h.open_case(test_tenant["id"], inv_id)
        with pytest.raises(ValueError, match="Invalid transition"):
            h.transition_state(test_tenant["id"], result.case_id, "CLOSED", "system")

    def test_open_case_idempotent(self, db_url, broker, test_tenant, unique_invoice_number):
        import psycopg2
        inv_id = _setup_canonical(db_url, broker, test_tenant, unique_invoice_number)
        h      = CaseHandler(db_url, broker)
        r1     = h.open_case(test_tenant["id"], inv_id)
        r2     = h.open_case(test_tenant["id"], inv_id)   # second call
        assert str(r1.case_id) == str(r2.case_id)
        assert r2.is_new is False

        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM cases WHERE tenant_id=%s AND invoice_id=%s",
            (test_tenant["id"], inv_id),
        )
        assert cur.fetchone()[0] == 1
        conn.close()

    def test_case_opened_published_to_kafka(self, db_url, broker, test_tenant, unique_invoice_number):
        inv_id = _setup_canonical(db_url, broker, test_tenant, unique_invoice_number)
        h      = CaseHandler(db_url, broker)
        h.open_case(test_tenant["id"], inv_id)
        assert broker.message_count("zoiko.case.opened") >= 1
