"""Tests for canonical_truth."""
import uuid
import paths  # noqa: F401
from services.canonical_truth.handler import CanonicalHandler


def _canonical_args(tenant_id, source_record_id, inv_no):
    return dict(
        tenant_id        = tenant_id,
        source_record_id = source_record_id,
        invoice_number   = inv_no,
        carrier_id       = "DHL",
        total_amount     = 220.0,
        currency         = "USD",
        origin_city      = "Dallas",
        dest_city        = "Atlanta",
    )


def _ingest(db_url, broker, tenant, inv_no):
    from services.ingestion_svc.handler import IngestionHandler
    from services.ingestion_svc.models import InvoiceInput
    h = IngestionHandler(db_url, broker, tenant["slug"])
    return h.ingest_invoice(
        tenant["id"],
        InvoiceInput("DHL", inv_no, 220.0, "USD", "Dallas", "Atlanta"),
    )


class TestCanonicalIntegration:
    def test_canonical_invoice_inserted(self, db_url, broker, test_tenant, unique_invoice_number):
        import psycopg2
        ing = _ingest(db_url, broker, test_tenant, unique_invoice_number)
        h   = CanonicalHandler(db_url, broker, test_tenant["slug"])
        result = h.canonicalize_invoice(**_canonical_args(test_tenant["id"], ing.source_record_id, unique_invoice_number))

        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor()
        cur.execute("SELECT id FROM canonical_invoices WHERE id=%s", (result.canonical_invoice_id,))
        assert cur.fetchone() is not None
        conn.close()

    def test_canonical_shipment_inserted(self, db_url, broker, test_tenant, unique_invoice_number):
        import psycopg2
        ing = _ingest(db_url, broker, test_tenant, unique_invoice_number)
        h   = CanonicalHandler(db_url, broker, test_tenant["slug"])
        result = h.canonicalize_invoice(**_canonical_args(test_tenant["id"], ing.source_record_id, unique_invoice_number))

        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor()
        cur.execute("SELECT id FROM canonical_shipments WHERE invoice_id=%s", (result.canonical_invoice_id,))
        assert cur.fetchone() is not None
        conn.close()

    def test_canonical_hash_is_64_chars(self, db_url, broker, test_tenant, unique_invoice_number):
        ing = _ingest(db_url, broker, test_tenant, unique_invoice_number)
        h   = CanonicalHandler(db_url, broker, test_tenant["slug"])
        result = h.canonicalize_invoice(**_canonical_args(test_tenant["id"], ing.source_record_id, unique_invoice_number))
        assert len(result.canonical_hash) == 64

    def test_canonical_publishes_kafka(self, db_url, broker, test_tenant, unique_invoice_number):
        ing = _ingest(db_url, broker, test_tenant, unique_invoice_number)
        h   = CanonicalHandler(db_url, broker, test_tenant["slug"])
        h.canonicalize_invoice(**_canonical_args(test_tenant["id"], ing.source_record_id, unique_invoice_number))
        assert broker.message_count("invoice.canonical") >= 1

    def test_duplicate_invoice_number_is_idempotent(self, db_url, broker, test_tenant, unique_invoice_number):
        import psycopg2
        ing = _ingest(db_url, broker, test_tenant, unique_invoice_number)
        h   = CanonicalHandler(db_url, broker, test_tenant["slug"])
        r1  = h.canonicalize_invoice(**_canonical_args(test_tenant["id"], ing.source_record_id, unique_invoice_number))
        r2  = h.canonicalize_invoice(**_canonical_args(test_tenant["id"], ing.source_record_id, unique_invoice_number))
        # Both calls return the same canonical_invoice_id
        assert str(r1.canonical_invoice_id) == str(r2.canonical_invoice_id)

        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM canonical_invoices WHERE tenant_id=%s AND invoice_number=%s",
            (test_tenant["id"], unique_invoice_number),
        )
        assert cur.fetchone()[0] == 1
        conn.close()
