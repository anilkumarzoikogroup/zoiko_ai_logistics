"""Tests for validation_svc."""
import uuid
import paths  # noqa: F401
from services.validation_svc.handler import ValidationHandler
from services.validation_svc.models import ValidationResult


class TestValidationIntegration:
    def _ingest(self, db_url, broker, tenant, inv_no):
        from services.ingestion_svc.handler import IngestionHandler
        from services.ingestion_svc.models import InvoiceInput
        h = IngestionHandler(db_url, broker, tenant["slug"])
        inv = InvoiceInput(
            carrier_id="DHL", invoice_number=inv_no,
            total_amount=220.0, currency="USD",
            route_origin="Dallas", route_destination="Atlanta",
        )
        return h.ingest_invoice(tenant["id"], inv)

    def test_sc001_overcharge_detected(self, db_url, broker, test_tenant):
        import psycopg2
        # Use a per-run unique carrier_id so accumulated runs don't stack rates
        carrier_id = f"DHL-SC001-{uuid.uuid4().hex[:8]}"
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO contract_rates
                (tenant_id, carrier_id, rate_type, rate_value, currency, effective_on)
            VALUES (%s, %s, 'FUEL_CHARGE', 120.0, 'USD', '2020-01-01')
        """, (test_tenant["id"], carrier_id))
        conn.close()

        from services.ingestion_svc.handler import IngestionHandler
        from services.ingestion_svc.models import InvoiceInput
        ing = IngestionHandler(db_url, broker, test_tenant["slug"]).ingest_invoice(
            test_tenant["id"],
            InvoiceInput(carrier_id, f"INV-{uuid.uuid4().hex[:6]}", 220.0, "USD", "Dallas", "Atlanta"),
        )
        h = ValidationHandler(db_url, broker, test_tenant["slug"])
        result = h.validate(
            test_tenant["id"], ing.source_record_id,
            ing.idempotency_key, carrier_id, 220.0,
        )
        assert result.status == "FAIL", f"Expected FAIL, got {result.status}"
        assert result.overcharge_amount == 100.0
        assert len(result.rule_violations) >= 1
        assert result.rule_violations[0].delta == 100.0

    def test_validation_result_in_db(self, db_url, broker, test_tenant, unique_invoice_number):
        import psycopg2
        ing = self._ingest(db_url, broker, test_tenant, unique_invoice_number)
        h   = ValidationHandler(db_url, broker, test_tenant["slug"])
        result = h.validate(
            test_tenant["id"], ing.source_record_id,
            unique_invoice_number, "DHL", 220.0,
        )
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor()
        cur.execute("SELECT id FROM validation_results WHERE id=%s", (result.validation_id,))
        assert cur.fetchone() is not None
        conn.close()

    def test_validation_publishes_kafka(self, db_url, broker, test_tenant, unique_invoice_number):
        ing = self._ingest(db_url, broker, test_tenant, unique_invoice_number)
        h   = ValidationHandler(db_url, broker, test_tenant["slug"])
        h.validate(test_tenant["id"], ing.source_record_id, unique_invoice_number, "DHL", 220.0)
        assert broker.message_count("zoiko.source.record.validated") >= 1

    def test_pass_when_amount_matches_contract(self, db_url, broker, test_tenant):
        import psycopg2
        carrier_id = f"TC-PASS-{uuid.uuid4().hex[:8]}"
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO contract_rates
                (tenant_id, carrier_id, rate_type, rate_value, currency, effective_on)
            VALUES (%s, %s, 'FUEL_CHARGE', 120.0, 'USD', '2020-01-01')
        """, (test_tenant["id"], carrier_id))
        conn.close()

        from services.ingestion_svc.handler import IngestionHandler
        from services.ingestion_svc.models import InvoiceInput
        ing = IngestionHandler(db_url, broker, test_tenant["slug"]).ingest_invoice(
            test_tenant["id"],
            InvoiceInput(carrier_id, f"TC-{uuid.uuid4().hex[:6]}", 120.0, "USD", "X", "Y"),
        )
        h = ValidationHandler(db_url, broker, test_tenant["slug"])
        result = h.validate(test_tenant["id"], ing.source_record_id, ing.idempotency_key, carrier_id, 120.0)
        assert result.status == "PASS"
        assert result.overcharge_amount == 0.0

    def test_no_violations_on_pass(self, db_url, broker, test_tenant):
        import psycopg2
        carrier_id = f"TC-NOV-{uuid.uuid4().hex[:8]}"
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO contract_rates
                (tenant_id, carrier_id, rate_type, rate_value, currency, effective_on)
            VALUES (%s, %s, 'FUEL_CHARGE', 120.0, 'USD', '2020-01-01')
        """, (test_tenant["id"], carrier_id))
        conn.close()

        from services.ingestion_svc.handler import IngestionHandler
        from services.ingestion_svc.models import InvoiceInput
        ing = IngestionHandler(db_url, broker, test_tenant["slug"]).ingest_invoice(
            test_tenant["id"],
            InvoiceInput(carrier_id, f"TC-{uuid.uuid4().hex[:6]}", 120.0, "USD", "X", "Y"),
        )
        h = ValidationHandler(db_url, broker, test_tenant["slug"])
        result = h.validate(test_tenant["id"], ing.source_record_id, ing.idempotency_key, carrier_id, 120.0)
        assert result.status == "PASS"
        assert result.rule_violations == []

    def test_warn_when_no_contract_rate(self, db_url, broker, test_tenant, unique_invoice_number):
        from services.ingestion_svc.handler import IngestionHandler
        from services.ingestion_svc.models import InvoiceInput
        ing = IngestionHandler(db_url, broker, test_tenant["slug"]).ingest_invoice(
            test_tenant["id"],
            InvoiceInput("UNKNOWN-CARRIER", f"UK-{uuid.uuid4().hex[:6]}", 500.0, "USD", "A", "B"),
        )
        h = ValidationHandler(db_url, broker, test_tenant["slug"])
        result = h.validate(test_tenant["id"], ing.source_record_id, ing.idempotency_key, "UNKNOWN-CARRIER", 500.0)
        assert result.status == "WARN"
        assert any(v.rule == "R003_NO_CONTRACT_RATE" for v in result.rule_violations)
