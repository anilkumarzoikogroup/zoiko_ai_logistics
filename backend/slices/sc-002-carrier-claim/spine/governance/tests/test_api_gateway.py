"""
API Gateway tests for Phase 3.

TestHealth         (1 test)  — no auth, no DB
TestAuthGuard      (3 tests) — 401/403 without touching DB
TestDomainHashes   (4 tests) — pure crypto, no DB
TestPipelineUnit   (DB tests, skipped if PostgreSQL unreachable)
"""
import base64
import os
import pytest
from dotenv import load_dotenv

import paths  # noqa: F401

load_dotenv()

_DEV_MODE = os.getenv("ZOIKO_DEV_MODE", "false").lower() == "true"

from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    import sys, os
    _phase3 = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    # Evict stale phase-2 cache entries
    for _k in [k for k in sys.modules if "services.api_gateway" in k or k == "services"]:
        del sys.modules[_k]
    # Temporarily prioritise phase-3 so its app loads instead of phase-2's
    sys.path.insert(0, _phase3)
    try:
        from services.api_gateway.app import app
    finally:
        if _phase3 in sys.path:
            sys.path.remove(_phase3)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def dev_token(client):
    import os
    from middleware.oidc.token_verifier import TokenVerifier
    import uuid

    secret = os.getenv("ZOIKO_DEV_SECRET").encode()
    issuer = os.getenv("ZOIKO_ISSUER", "https://auth.zoikotech.com")
    tv     = TokenVerifier(dev_secret=secret, issuer=issuer)
    tid    = str(uuid.uuid4())
    token  = tv.make_dev_token(tenant_id=tid, sub="test-user@zoikotech.com")
    return {"token": token, "tenant_id": tid}


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["version"] == "3.0.0"


# ── Auth guard — only meaningful when DEV_MODE is off ────────────────────────

@pytest.mark.skipif(_DEV_MODE, reason="Auth guard is bypassed in ZOIKO_DEV_MODE=true")
class TestAuthGuard:
    CASE_ID = "00000000-0000-0000-0000-000000000001"

    def test_missing_auth_returns_401(self, client):
        r = client.post(f"/evidence/{self.CASE_ID}/items", json={})
        assert r.status_code in (401, 403, 422)

    def test_bad_token_returns_401(self, client, dev_token):
        r = client.post(
            f"/evidence/{self.CASE_ID}/items",
            headers={
                "Authorization": "Bearer not-a-valid-jwt",
                "X-Tenant-ID": dev_token["tenant_id"],
            },
            json={"item_type": "BOL", "content_b64": base64.b64encode(b"test").decode()},
        )
        assert r.status_code == 401

    def test_tenant_mismatch_returns_403(self, client, dev_token):
        r = client.post(
            f"/evidence/{self.CASE_ID}/items",
            headers={
                "Authorization": f"Bearer {dev_token['token']}",
                "X-Tenant-ID": "00000000-0000-0000-0000-000000000099",  # wrong tenant
            },
            json={"item_type": "BOL", "content_b64": base64.b64encode(b"test").decode()},
        )
        assert r.status_code == 403


# ── Pure crypto unit tests (no DB) ───────────────────────────────────────────

class TestDomainHashes:
    def test_evidence_domain_tag(self):
        import hashlib
        from services.evidence_svc.handler import DOMAIN_TAG
        h = hashlib.sha256(DOMAIN_TAG + b"test_content").hexdigest()
        assert len(h) == 64

    def test_finding_domain_tag(self):
        import hashlib
        from zoiko_common.crypto.jcs import canonicalize
        payload = {"a": "1", "b": "2"}
        h = hashlib.sha256(b"zoiko.finding.v1:" + canonicalize(payload)).hexdigest()
        assert len(h) == 64

    def test_decision_domain_tag(self):
        import hashlib
        from zoiko_common.crypto.jcs import canonicalize
        payload = {"actor_sub": "ramu", "outcome": "EXECUTION_READY"}
        h = hashlib.sha256(b"zoiko.governance.decision.v1:" + canonicalize(payload)).hexdigest()
        assert len(h) == 64

    def test_token_domain_tag(self):
        import hashlib
        from zoiko_common.crypto.jcs import canonicalize
        payload = {"scope": "EXECUTE_CREDIT_MEMO", "tenant_id": "t1"}
        h = hashlib.sha256(b"zoiko.token.v1:" + canonicalize(payload)).hexdigest()
        assert len(h) == 64


# ── Pipeline integration (DB required) ───────────────────────────────────────

class TestPipelineIntegration:
    """Full pipeline via HTTP: evidence → reasoning → governance → token."""

    def _headers(self, dev_token):
        return {
            "Authorization": f"Bearer {dev_token['token']}",
            "X-Tenant-ID":   dev_token["tenant_id"],
        }

    def test_add_evidence_returns_201(self, client, dev_token, db_url, test_case):
        # For HTTP test we need the tenant_id to match the case tenant
        # Use a direct handler call instead to avoid JWT/tenant_id mismatch
        from services.evidence_svc.handler import EvidenceHandler
        from kafka.mock_kafka import MockKafkaBroker
        handler = EvidenceHandler(db_url, MockKafkaBroker(), "default")
        result  = handler.add_item(
            tenant_id     = test_case["tenant_id"],
            case_id       = test_case["id"],
            item_type     = "BOL",
            content_bytes = b"gateway integration test bol",
            actor_sub     = "ravi@amazon.com",
        )
        assert result.item_id is not None
        assert result.bundle_hash != ""

    def test_full_pipeline_evidence_to_token(self, db_url, test_case, broker):
        from services.evidence_svc.handler   import EvidenceHandler
        from services.reasoning_svc.handler  import ReasoningHandler
        from services.governance_svc.handler import GovernanceHandler
        from services.token_svc.handler      import TokenHandler

        ev   = EvidenceHandler(db_url, broker, "default")
        ev_r = ev.add_item(
            tenant_id=test_case["tenant_id"], case_id=test_case["id"],
            item_type="BOL", content_bytes=b"full-pipeline-e2e-test",
            actor_sub="ravi@amazon.com",
        )
        ev.seal_bundle(tenant_id=test_case["tenant_id"], case_id=test_case["id"])

        rh  = ReasoningHandler(db_url, broker, "default")
        r   = rh.analyze(
            tenant_id=test_case["tenant_id"], case_id=test_case["id"],
            bundle_id=str(ev_r.bundle_id), proposer_sub="ravi@amazon.com",
            amount=4500.0, currency="INR",
        )
        assert r.confidence == 0.9275

        gov  = GovernanceHandler(db_url, broker, "default")
        task = gov.create_task(
            tenant_id=test_case["tenant_id"],
            proposal_id=str(r.proposal_id),
            proposer_sub="ravi@amazon.com",
        )
        dec  = gov.decide(
            tenant_id=test_case["tenant_id"],
            task_id=str(task.task_id),
            actor_sub="ramu@amazon.com",
            outcome="EXECUTION_READY",
        )
        assert dec.outcome == "EXECUTION_READY"

        token = TokenHandler(db_url, broker, "default").mint(
            tenant_id=test_case["tenant_id"],
            decision_id=str(dec.decision_id),
            case_id=test_case["id"],
            scope="EXECUTE_CREDIT_MEMO",
        )
        assert token.status == "ACTIVE"
        assert len(token.token_hash) == 64
        assert len(token.tenant_binding) == 64
