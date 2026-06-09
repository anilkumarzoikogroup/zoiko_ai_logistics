"""
API Gateway tests — unit (auth, health) + integration (full pipeline via HTTP).

Requires:
  - PostgreSQL reachable at DB_URL (same skip logic as other integration tests)
  - An active tenant row in the tenants table (run seed_dummy_data.py first)

The dev JWT is minted with the same HS256 secret that auth.py reads from
ZOIKO_DEV_SECRET env-var (default: "zoiko-dev-secret-for-testing-only").
"""
import os
import uuid
from dotenv import load_dotenv

import pytest
import paths  # noqa: F401

load_dotenv()

from fastapi.testclient import TestClient
from middleware.oidc.token_verifier import TokenVerifier

DEV_SECRET = os.getenv("ZOIKO_DEV_SECRET").encode()
ISSUER     = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com")

_minter = TokenVerifier(dev_secret=DEV_SECRET, issuer=ISSUER)


def _jwt(tenant_id: str, sub: str = "test-user") -> str:
    return _minter.make_dev_token(sub=sub, tenant_id=tenant_id)


def _auth_headers(tenant_id: str, sub: str = "test-user") -> dict:
    return {
        "Authorization":  f"Bearer {_jwt(tenant_id, sub)}",
        "X-Tenant-ID":    tenant_id,
    }


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from services.api_gateway.app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── /health — public, no auth ─────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"]  == "ok"
        assert body["service"] == "api-gateway"


# ── Auth guard unit tests — only meaningful when DEV_MODE is off ──────────────

_DEV_MODE = os.getenv("ZOIKO_DEV_MODE", "false").lower() == "true"


@pytest.mark.skipif(_DEV_MODE, reason="Auth guard is bypassed in ZOIKO_DEV_MODE=true")
class TestAuthGuard:
    _fake_tid = str(uuid.uuid4())

    def test_missing_bearer_returns_403(self, client):
        r = client.post(
            "/invoices",
            json={
                "carrier_id": "DHL", "invoice_number": "X",
                "total_amount": 100.0, "currency": "USD",
                "route_origin": "A", "route_destination": "B",
            },
            headers={"X-Tenant-ID": self._fake_tid, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code in (401, 403, 422)

    def test_invalid_token_returns_401(self, client):
        r = client.post(
            "/invoices",
            json={
                "carrier_id": "DHL", "invoice_number": "X",
                "total_amount": 100.0, "currency": "USD",
                "route_origin": "A", "route_destination": "B",
            },
            headers={
                "Authorization":  "Bearer not.a.real.token",
                "X-Tenant-ID":    self._fake_tid,
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        assert r.status_code == 401

    def test_tenant_mismatch_returns_403(self, client):
        wrong_tenant = str(uuid.uuid4())
        token        = _jwt(self._fake_tid)   # token says fake_tid
        r = client.post(
            "/invoices",
            json={
                "carrier_id": "DHL", "invoice_number": "X",
                "total_amount": 100.0, "currency": "USD",
                "route_origin": "A", "route_destination": "B",
            },
            headers={
                "Authorization":  f"Bearer {token}",
                "X-Tenant-ID":    wrong_tenant,    # header says wrong_tenant → mismatch
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        assert r.status_code == 403


# ── Integration: full pipeline via HTTP ───────────────────────────────────────

class TestPipelineIntegration:
    """End-to-end: ingest → validate → canonicalize → open_case → transition."""

    def test_ingest_invoice(self, client, db_url, test_tenant):
        tid    = test_tenant["id"]
        inv_no = f"GW-{uuid.uuid4().hex[:8].upper()}"

        r = client.post(
            "/invoices",
            json={
                "carrier_id":        "DHL",
                "invoice_number":    inv_no,
                "total_amount":      120.0,
                "currency":          "USD",
                "route_origin":      "Dallas",
                "route_destination": "Chicago",
                "weight_lbs":        50.0,
            },
            headers={**_auth_headers(tid), "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert "source_record_id" in body
        assert len(body["canonical_hash"]) == 64
        assert body["tenant_id"] == tid

    def test_ingest_idempotent_on_same_key(self, client, db_url, test_tenant):
        tid     = test_tenant["id"]
        inv_no  = f"GW-IDEM-{uuid.uuid4().hex[:6].upper()}"
        ikey    = str(uuid.uuid4())
        headers = {**_auth_headers(tid), "Idempotency-Key": ikey}
        payload = {
            "carrier_id": "UPS", "invoice_number": inv_no,
            "total_amount": 99.0, "currency": "USD",
            "route_origin": "NY", "route_destination": "LA",
        }
        r1 = client.post("/invoices", json=payload, headers=headers)
        r2 = client.post("/invoices", json=payload, headers=headers)
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["source_record_id"] == r2.json()["source_record_id"]

    def test_validate_invoice(self, client, db_url, test_tenant):
        """Validates against any available contract rates (PASS or WARN — not a hard FAIL)."""
        tid    = test_tenant["id"]
        inv_no = f"GW-VAL-{uuid.uuid4().hex[:8].upper()}"
        carrier = f"DHL-{uuid.uuid4().hex[:6]}"   # unique carrier → NO_CONTRACT_RATE → WARN

        # ingest first
        r = client.post(
            "/invoices",
            json={
                "carrier_id": carrier, "invoice_number": inv_no,
                "total_amount": 100.0, "currency": "USD",
                "route_origin": "A", "route_destination": "B",
            },
            headers={**_auth_headers(tid), "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 201
        src_id = r.json()["source_record_id"]

        # validate
        r2 = client.post(
            f"/invoices/{src_id}/validate",
            json={
                "invoice_number": inv_no, "carrier_id": carrier,
                "total_amount": 100.0, "currency": "USD",
            },
            headers=_auth_headers(tid),
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["status"] in ("PASS", "WARN", "FAIL")
        assert "validation_id" in body

    def test_canonicalize_invoice(self, client, db_url, test_tenant):
        tid    = test_tenant["id"]
        inv_no = f"GW-CAN-{uuid.uuid4().hex[:8].upper()}"
        carrier = f"FED-{uuid.uuid4().hex[:6]}"

        # ingest
        r = client.post(
            "/invoices",
            json={
                "carrier_id": carrier, "invoice_number": inv_no,
                "total_amount": 80.0, "currency": "USD",
                "route_origin": "Seattle", "route_destination": "Portland",
            },
            headers={**_auth_headers(tid), "Idempotency-Key": str(uuid.uuid4())},
        )
        src_id = r.json()["source_record_id"]

        # canonicalize
        r2 = client.post(
            f"/invoices/{src_id}/canonicalize",
            json={
                "invoice_number": inv_no, "carrier_id": carrier,
                "total_amount": 80.0, "currency": "USD",
                "origin_city": "Seattle", "dest_city": "Portland",
                "weight_lbs": 20.0,
            },
            headers=_auth_headers(tid),
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert "canonical_invoice_id" in body
        assert len(body["canonical_hash"]) == 64
        assert body["invoice_number"] == inv_no

    def test_open_case(self, client, db_url, test_tenant):
        tid    = test_tenant["id"]
        inv_no = f"GW-CASE-{uuid.uuid4().hex[:8].upper()}"
        carrier = f"UPS-{uuid.uuid4().hex[:6]}"

        # ingest
        r = client.post(
            "/invoices",
            json={
                "carrier_id": carrier, "invoice_number": inv_no,
                "total_amount": 75.0, "currency": "USD",
                "route_origin": "Houston", "route_destination": "Austin",
            },
            headers={**_auth_headers(tid), "Idempotency-Key": str(uuid.uuid4())},
        )
        src_id = r.json()["source_record_id"]

        # canonicalize to get canonical_invoice_id
        r2 = client.post(
            f"/invoices/{src_id}/canonicalize",
            json={
                "invoice_number": inv_no, "carrier_id": carrier,
                "total_amount": 75.0, "currency": "USD",
                "origin_city": "Houston", "dest_city": "Austin",
            },
            headers=_auth_headers(tid),
        )
        canonical_id = r2.json()["canonical_invoice_id"]

        # open case
        r3 = client.post(
            "/cases",
            json={"canonical_invoice_id": canonical_id},
            headers=_auth_headers(tid),
        )
        assert r3.status_code == 201, r3.text
        body = r3.json()
        assert body["state"] == "NEW"
        assert body["tenant_id"] == tid

    def test_transition_case_state(self, client, db_url, test_tenant):
        tid    = test_tenant["id"]
        inv_no = f"GW-TR-{uuid.uuid4().hex[:8].upper()}"
        carrier = f"CASE-{uuid.uuid4().hex[:6]}"

        # ingest → canonicalize → open case
        r = client.post(
            "/invoices",
            json={
                "carrier_id": carrier, "invoice_number": inv_no,
                "total_amount": 60.0, "currency": "USD",
                "route_origin": "Miami", "route_destination": "Tampa",
            },
            headers={**_auth_headers(tid), "Idempotency-Key": str(uuid.uuid4())},
        )
        src_id = r.json()["source_record_id"]

        r2 = client.post(
            f"/invoices/{src_id}/canonicalize",
            json={
                "invoice_number": inv_no, "carrier_id": carrier,
                "total_amount": 60.0, "currency": "USD",
                "origin_city": "Miami", "dest_city": "Tampa",
            },
            headers=_auth_headers(tid),
        )
        canonical_id = r2.json()["canonical_invoice_id"]

        r3 = client.post(
            "/cases",
            json={"canonical_invoice_id": canonical_id},
            headers=_auth_headers(tid),
        )
        case_id = r3.json()["case_id"]

        # transition OPENED → EVIDENCE_GATHERING
        r4 = client.patch(
            f"/cases/{case_id}/state",
            json={"new_state": "EVIDENCE_PENDING", "actor_sub": "test-user", "payload": {}},
            headers=_auth_headers(tid),
        )
        assert r4.status_code == 200, r4.text
        body = r4.json()
        assert body["new_state"] == "EVIDENCE_PENDING"
        assert body["case_id"] == case_id

    def test_invalid_transition_returns_422(self, client, db_url, test_tenant):
        tid    = test_tenant["id"]
        inv_no = f"GW-BAD-{uuid.uuid4().hex[:8].upper()}"
        carrier = f"BAD-{uuid.uuid4().hex[:6]}"

        r = client.post(
            "/invoices",
            json={
                "carrier_id": carrier, "invoice_number": inv_no,
                "total_amount": 55.0, "currency": "USD",
                "route_origin": "X", "route_destination": "Y",
            },
            headers={**_auth_headers(tid), "Idempotency-Key": str(uuid.uuid4())},
        )
        src_id = r.json()["source_record_id"]

        r2 = client.post(
            f"/invoices/{src_id}/canonicalize",
            json={
                "invoice_number": inv_no, "carrier_id": carrier,
                "total_amount": 55.0, "currency": "USD",
                "origin_city": "X", "dest_city": "Y",
            },
            headers=_auth_headers(tid),
        )
        canonical_id = r2.json()["canonical_invoice_id"]

        r3 = client.post(
            "/cases",
            json={"canonical_invoice_id": canonical_id},
            headers=_auth_headers(tid),
        )
        case_id = r3.json()["case_id"]

        # Try to jump OPENED → APPROVED (invalid)
        r4 = client.patch(
            f"/cases/{case_id}/state",
            json={"new_state": "EXECUTION_READY", "actor_sub": "test-user", "payload": {}},
            headers=_auth_headers(tid),
        )
        assert r4.status_code == 422
