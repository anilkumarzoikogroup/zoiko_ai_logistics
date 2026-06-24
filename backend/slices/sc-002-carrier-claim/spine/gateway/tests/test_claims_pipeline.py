"""
SC-002 carrier claims — integration tests via HTTP (mirrors test_api_gateway.py's
TestPipelineIntegration pattern). Exercises the real spine: submit-async → evidence
→ AI reasoning → propose → SoD-enforced decide → 8-gate execute → ACR.

Requires PostgreSQL reachable at DB_URL and an active tenant (same skip logic as
the existing gateway tests).
"""
import os
import time
import uuid

import pytest
import paths  # noqa: F401

from dotenv import load_dotenv
load_dotenv()

from fastapi.testclient import TestClient
from middleware.oidc.token_verifier import TokenVerifier

DEV_SECRET = os.getenv("ZOIKO_DEV_SECRET").encode()
ISSUER     = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com")

_minter = TokenVerifier(dev_secret=DEV_SECRET, issuer=ISSUER)


def _jwt(tenant_id: str, sub: str, roles: list[str]) -> str:
    return _minter.make_dev_token(sub=sub, tenant_id=tenant_id, roles=roles)


def _headers(tenant_id: str, sub: str, roles: list[str], idem: str | None = None) -> dict:
    h = {
        "Authorization": f"Bearer {_jwt(tenant_id, sub, roles)}",
        "X-Tenant-ID":   tenant_id,
    }
    if idem:
        h["Idempotency-Key"] = idem
    return h


@pytest.fixture(scope="module")
def client():
    from services.api_gateway.app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _submit_claim(client, tid, sub, claim_reference=None, amount=2500, carrier="TestCarrier"):
    """Submit a claim via the real async pattern, poll to completion, return the resulting case dict."""
    body = {
        "carrier": carrier, "claim_type": "DAMAGE",
        "claimed_amount": amount, "currency": "INR",
        "description": "pytest claim",
    }
    if claim_reference:
        body["claim_reference"] = claim_reference

    r = client.post(
        "/v1/claims/submit-async", json=body,
        headers=_headers(tid, sub, ["analyst"], idem=str(uuid.uuid4())),
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]

    for _ in range(30):
        time.sleep(1)
        s = client.get(
            f"/v1/claims/submit-status/{job_id}",
            headers=_headers(tid, sub, ["analyst"]),
        )
        assert s.status_code == 200
        body = s.json()
        if body["status"] == "done":
            return body["case"]
        if body["status"] == "error":
            pytest.fail(f"Claim submission failed: {body['error']}")
    pytest.fail("Timed out waiting for claim submission to complete")


class TestClaimsSubmission:
    def test_submit_claim_scores_sc002_confidence(self, client, db_url, test_tenant):
        tid = test_tenant["id"]
        case = _submit_claim(client, tid, "pytest-analyst-1", carrier="BlueDart")

        assert case["case_type"] == "CARRIER_CLAIM"
        assert case["state"] == "FINDING_GENERATED"
        # SC002_CONFIDENCE = 0.95*0.55 + 0.90*0.45 — deterministic, must never drift
        assert case["confidence"] == pytest.approx(0.9275, abs=1e-6)
        assert case["duplicate"] is False

    def test_duplicate_claim_reference_is_detected(self, client, db_url, test_tenant):
        tid = test_tenant["id"]
        ref = f"PYTEST-DUP-{uuid.uuid4().hex[:8].upper()}"

        first  = _submit_claim(client, tid, "pytest-analyst-2", claim_reference=ref)
        second = _submit_claim(client, tid, "pytest-analyst-2", claim_reference=ref)

        assert first["duplicate"] is False
        assert second["duplicate"] is True
        assert second["id"] == first["id"]
        assert second["deduplication_outcome"] == "DUPLICATE_OF"

    def test_claims_list_endpoint_returns_submitted_claim(self, client, db_url, test_tenant):
        tid = test_tenant["id"]
        case = _submit_claim(client, tid, "pytest-analyst-3", carrier="PytestCarrierList")

        r = client.get(
            "/v1/claims", params={"page_size": 50},
            headers=_headers(tid, "pytest-analyst-3", ["analyst"]),
        )
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()["claims"]]
        assert case["id"] in ids

    def test_claim_detail_endpoint(self, client, db_url, test_tenant):
        tid = test_tenant["id"]
        case = _submit_claim(client, tid, "pytest-analyst-4")

        r = client.get(
            f"/v1/claims/{case['id']}",
            headers=_headers(tid, "pytest-analyst-4", ["analyst"]),
        )
        assert r.status_code == 200
        assert r.json()["case_type"] == "CARRIER_CLAIM"


class TestClaimsGovernanceFlow:
    """Propose -> SoD-enforced decide -> 8-gate execute -> ACR, end to end."""

    def test_self_approval_is_blocked_by_sod(self, client, db_url, test_tenant):
        tid  = test_tenant["id"]
        case = _submit_claim(client, tid, "pytest-sod-analyst", amount=1200)

        prop = client.post(
            f"/v1/cases/{case['id']}/proposal",
            json={"action": "SETTLE_CLAIM", "amount": 1200, "currency": "INR"},
            headers=_headers(tid, "pytest-sod-analyst", ["analyst"]),
        )
        assert prop.status_code == 201, prop.text

        # Same actor tries to approve their own proposal — must be rejected.
        decide = client.post(
            f"/v1/cases/{case['id']}/decide",
            json={"decision": "EXECUTION_READY"},
            headers=_headers(tid, "pytest-sod-analyst", ["analyst"]),
        )
        assert decide.status_code == 422
        assert "Separation of Duties" in decide.text

    def test_full_propose_approve_execute_dispatches(self, client, db_url, test_tenant):
        tid  = test_tenant["id"]
        case = _submit_claim(client, tid, "pytest-flow-analyst", amount=4400, carrier="DHL")
        case_id = case["id"]

        prop = client.post(
            f"/v1/cases/{case_id}/proposal",
            json={"action": "SETTLE_CLAIM", "amount": 4400, "currency": "INR"},
            headers=_headers(tid, "pytest-flow-analyst", ["analyst"]),
        )
        assert prop.status_code == 201, prop.text

        decide = client.post(
            f"/v1/cases/{case_id}/decide",
            json={"decision": "EXECUTION_READY"},
            headers=_headers(tid, "pytest-flow-manager", ["manager"]),
        )
        assert decide.status_code == 200, decide.text
        token_id = decide.json()["token_id"]
        assert token_id

        execute = client.post(
            "/v1/execute",
            json={"token_id": token_id, "case_id": case_id, "amount": 4400, "currency": "INR"},
            headers=_headers(tid, "pytest-flow-manager", ["manager"]),
        )
        assert execute.status_code == 200, execute.text
        body = execute.json()
        assert body["status"] == "DISPATCHED"
        assert body["gates_passed"] == 8

        # ACR issuance must also work for a claim case (case_type-branched artifact collection).
        acr = client.post(
            f"/v1/cases/{case_id}/acr",
            json={},
            headers=_headers(tid, "pytest-flow-manager", ["manager"], idem=str(uuid.uuid4())),
        )
        assert acr.status_code == 201, acr.text
        assert acr.json()["artifact_count"] == 8
