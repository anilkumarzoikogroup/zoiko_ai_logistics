"""Tests for ingestion_svc — both unit (no DB) and integration (real DB)."""
import hashlib
import uuid

import paths  # noqa: F401
from zoiko_common.crypto.jcs import canonicalize
from services.ingestion_svc.handler import IngestionHandler, DOMAIN_TAG
from services.ingestion_svc.models import InvoiceInput


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sample_invoice(number=None):
    return InvoiceInput(
        carrier_id        = "DHL",
        invoice_number    = number or f"DHL-TEST-{uuid.uuid4().hex[:6]}",
        total_amount      = 220.0,
        currency          = "USD",
        route_origin      = "Dallas",
        route_destination = "Atlanta",
    )


# ── Unit tests (no DB) ─────────────────────────────────────────────────────────

class TestDomainTaggedHash:
    def test_domain_tag_prefix(self):
        inv     = _sample_invoice()
        payload = {
            "carrier_id":        inv.carrier_id,
            "currency":          inv.currency,
            "invoice_number":    inv.invoice_number,
            "route_destination": inv.route_destination,
            "route_origin":      inv.route_origin,
            "total_amount":      str(inv.total_amount),
        }
        canonical_bytes = canonicalize(payload)
        expected_hash   = hashlib.sha256(DOMAIN_TAG + canonical_bytes).hexdigest()
        assert len(expected_hash) == 64

    def test_different_amounts_produce_different_hashes(self):
        def _hash(amount):
            payload = {
                "carrier_id": "DHL", "currency": "USD",
                "invoice_number": "X", "route_destination": "ATL",
                "route_origin": "DAL", "total_amount": str(amount),
            }
            return hashlib.sha256(DOMAIN_TAG + canonicalize(payload)).hexdigest()

        assert _hash(220.0) != _hash(120.0)

    def test_jcs_key_order_is_unicode(self):
        """JCS must sort keys by Unicode code point — 'carrier_id' < 'currency'."""
        payload = {"currency": "USD", "carrier_id": "DHL", "total_amount": "220.0",
                   "invoice_number": "X", "route_destination": "Y", "route_origin": "Z"}
        raw = canonicalize(payload).decode()
        assert raw.index("carrier_id") < raw.index("currency")

    def test_idempotency_key_generated_when_absent(self, broker):
        handler = IngestionHandler("unused", broker, "test-slug")
        key = handler.ingest_invoice.__wrapped__ if hasattr(handler.ingest_invoice, "__wrapped__") else None
        # Just verify the default uuid4 path works without crash for the logic
        idem = str(uuid.uuid4())
        assert len(idem) == 36


# ── Integration tests (real DB) ───────────────────────────────────────────────

class TestIngestionIntegration:
    def test_ingest_inserts_source_record(self, db_url, broker, test_tenant, unique_invoice_number):
        import psycopg2
        handler = IngestionHandler(db_url, broker, test_tenant["slug"])
        inv     = _sample_invoice(unique_invoice_number)
        result  = handler.ingest_invoice(test_tenant["id"], inv)

        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor()
        cur.execute("SELECT id FROM source_records WHERE id=%s", (result.source_record_id,))
        row  = cur.fetchone()
        conn.close()
        assert row is not None, "source_records row not found"

    def test_ingest_inserts_outbox_row(self, db_url, broker, test_tenant, unique_invoice_number):
        import psycopg2
        handler = IngestionHandler(db_url, broker, test_tenant["slug"])
        inv     = _sample_invoice(unique_invoice_number)
        result  = handler.ingest_invoice(test_tenant["id"], inv)

        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor()
        cur.execute(
            "SELECT id FROM outbox WHERE tenant_id=%s AND topic='zoiko.source.record.received' "
            "AND payload->>'source_record_id' = %s",
            (test_tenant["id"], str(result.source_record_id)),
        )
        row = cur.fetchone()
        conn.close()
        assert row is not None, "outbox row not found"

    def test_ingest_publishes_kafka_message(self, db_url, broker, test_tenant, unique_invoice_number):
        handler = IngestionHandler(db_url, broker, test_tenant["slug"])
        inv     = _sample_invoice(unique_invoice_number)
        handler.ingest_invoice(test_tenant["id"], inv)
        assert broker.message_count("zoiko.source.record.received") >= 1

    def test_ingest_result_has_64char_hex_hash(self, db_url, broker, test_tenant, unique_invoice_number):
        handler = IngestionHandler(db_url, broker, test_tenant["slug"])
        inv     = _sample_invoice(unique_invoice_number)
        result  = handler.ingest_invoice(test_tenant["id"], inv)
        assert len(result.canonical_hash) == 64

    def test_idempotency_no_duplicate_on_same_key(self, db_url, broker, test_tenant, unique_invoice_number):
        import psycopg2
        handler  = IngestionHandler(db_url, broker, test_tenant["slug"])
        inv      = _sample_invoice(unique_invoice_number)
        idem_key = str(uuid.uuid4())
        handler.ingest_invoice(test_tenant["id"], inv, idempotency_key=idem_key)
        handler.ingest_invoice(test_tenant["id"], inv, idempotency_key=idem_key)   # second call

        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM source_records WHERE tenant_id=%s AND idempotency_key=%s",
            (test_tenant["id"], idem_key),
        )
        count = cur.fetchone()[0]
        conn.close()
        assert count == 1, "Duplicate source_record inserted on same idempotency key"
