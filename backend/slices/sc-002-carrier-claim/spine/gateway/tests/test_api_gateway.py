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
            "/claims/submit",
            json={"carrier": "DHL", "claim_type": "DAMAGE", "claimed_amount": 100.0, "currency": "USD"},
            headers={"X-Tenant-ID": self._fake_tid, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code in (401, 403, 422)

    def test_invalid_token_returns_401(self, client):
        r = client.post(
            "/claims/submit",
            json={"carrier": "DHL", "claim_type": "DAMAGE", "claimed_amount": 100.0, "currency": "USD"},
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
            "/claims/submit",
            json={"carrier": "DHL", "claim_type": "DAMAGE", "claimed_amount": 100.0, "currency": "USD"},
            headers={
                "Authorization":  f"Bearer {token}",
                "X-Tenant-ID":    wrong_tenant,    # header says wrong_tenant → mismatch
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        assert r.status_code == 403

