"""
Connector Hub tests.

TestCircuitBreaker   (4 tests) — pure logic, no I/O
TestRegistry         (3 tests) — in-memory, no I/O
TestClaimHandler     (4 tests) — handler with no DB (db_url=None)
TestHTTPRoutes       (4 tests) — FastAPI TestClient, no DB
"""
import sys
import os
import pytest

# Ensure connector-hub is on sys.path
_HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HUB not in sys.path:
    sys.path.insert(0, _HUB)


# ── Circuit Breaker ───────────────────────────────────────────────────────────

class TestCircuitBreaker:
    def _make(self, threshold=3, recovery=30.0):
        from services.connector_hub.circuit_breaker import CircuitBreaker
        return CircuitBreaker("test", failure_threshold=threshold, recovery_timeout_s=recovery)

    def test_starts_closed(self):
        cb = self._make()
        assert cb.state == "CLOSED"

    def test_opens_after_threshold_failures(self):
        from services.connector_hub.circuit_breaker import CircuitOpenError
        cb = self._make(threshold=3)
        for _ in range(3):
            try:
                cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
            except RuntimeError:
                pass
        assert cb.state == "OPEN"

    def test_open_raises_circuit_open_error(self):
        from services.connector_hub.circuit_breaker import CircuitBreaker, CircuitOpenError
        cb = CircuitBreaker("t", failure_threshold=1, recovery_timeout_s=999)
        try:
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        except RuntimeError:
            pass
        with pytest.raises(CircuitOpenError):
            cb.call(lambda: "ok")

    def test_reset_closes_circuit(self):
        from services.connector_hub.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker("t", failure_threshold=1, recovery_timeout_s=999)
        try:
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        except RuntimeError:
            pass
        cb.reset()
        assert cb.state == "CLOSED"


# ── Registry ─────────────────────────────────────────────────────────────────

class TestRegistry:
    def test_precertified_carriers_active(self):
        from services.connector_hub.registry import ConnectorRegistry
        reg = ConnectorRegistry()
        assert reg.is_active("BlueDart")
        assert reg.is_active("DHL")
        assert reg.is_active("mock-carrier")

    def test_sc001_fx_rate_deterministic(self):
        from services.connector_hub.registry import ConnectorRegistry
        reg = ConnectorRegistry()
        usd = reg.to_usd(4500.0, "INR")
        assert usd == 220.0, f"Expected USD 220.00, got {usd}"

    def test_certify_and_suspend(self):
        from services.connector_hub.registry import ConnectorRegistry
        reg = ConnectorRegistry()
        reg.certify("NewCarrier", "admin@test.com")
        assert reg.is_active("NewCarrier")
        reg.suspend("NewCarrier", "admin@test.com")
        assert not reg.is_active("NewCarrier")


# ── Claim Handler ─────────────────────────────────────────────────────────────

class TestClaimHandler:
    def _handler(self):
        from services.connector_hub.handler import ConnectorHubHandler
        return ConnectorHubHandler(db_url=None)

    def _req(self, carrier_id="BlueDart", amount=4500.0, currency="INR"):
        from services.connector_hub.models import ClaimRequest
        return ClaimRequest(
            carrier_id="BlueDart" if carrier_id == "BlueDart" else carrier_id,
            envelope_id="00000000-0000-0000-0000-000000000001",
            tenant_id="11111111-1111-1111-1111-111111111111",
            claimed_amount=amount,
            currency=currency,
            invoice_ref="INV-001",
            actor_sub="ramu@amazon.com",
            idempotency_key="key-001",
        )

    def test_sc001_bluedart_inr_4500_returns_usd_220(self):
        h = self._handler()
        r = h.submit_claim(self._req("BlueDart", 4500.0, "INR"))
        assert r.accepted is True
        assert r.accepted_amount == 220.0
        assert r.status == "ACCEPTED"
        assert r.original_currency == "INR"

    def test_usd_claim_passes_through(self):
        h = self._handler()
        r = h.submit_claim(self._req("DHL", 100.0, "USD"))
        assert r.accepted is True
        assert r.accepted_amount == 100.0

    def test_inactive_carrier_rejected(self):
        from services.connector_hub.registry import get_registry
        reg = get_registry()
        reg.certify("TempCarrier", "admin")
        reg.suspend("TempCarrier", "admin")
        h = self._handler()
        r = h.submit_claim(self._req("TempCarrier", 100.0, "USD"))
        assert r.accepted is False
        assert r.status == "REJECTED"
        # re-certify to clean up
        reg.certify("TempCarrier", "admin")

    def test_deterministic_repeated_claims(self):
        h = self._handler()
        results = [h.submit_claim(self._req("BlueDart", 4500.0, "INR")) for _ in range(10)]
        assert all(r.accepted_amount == 220.0 for r in results)


# ── HTTP Routes ───────────────────────────────────────────────────────────────

class TestHTTPRoutes:
    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient
        from services.connector_hub.app import app
        return TestClient(app, raise_server_exceptions=False)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["version"] == "1.0.0"

    def test_submit_claim_sc001(self, client):
        r = client.post(
            "/v1/connectors/BlueDart/claims",
            json={
                "envelope_id": "00000000-0000-0000-0000-000000000001",
                "tenant_id":   "11111111-1111-1111-1111-111111111111",
                "claimed_amount": 4500.0,
                "currency": "INR",
                "invoice_ref": "INV-SC001",
                "actor_sub": "ramu@amazon.com",
            },
            headers={
                "Idempotency-Key": "http-test-001",
                "X-Tenant-ID": "11111111-1111-1111-1111-111111111111",
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["accepted"] is True
        assert body["accepted_amount"] == 220.0
        assert body["status"] == "ACCEPTED"

    def test_connector_status_active(self, client):
        r = client.get("/v1/connectors/BlueDart/status")
        assert r.status_code == 200
        assert r.json()["status"] == "ACTIVE"
        assert r.json()["circuit_state"] == "CLOSED"

    def test_unknown_connector_status_404(self, client):
        r = client.get("/v1/connectors/UnknownCarrierXYZ/status")
        assert r.status_code == 404
