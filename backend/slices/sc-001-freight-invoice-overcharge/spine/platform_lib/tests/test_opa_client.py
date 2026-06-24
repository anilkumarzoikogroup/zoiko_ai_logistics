"""Tests for OPA client, MockOPAClient, and fail-closed behaviour."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from middleware.opa.client import (
    OPAClient, MockOPAClient, OPADecision, OPAUnavailableError,
    FailClosedOPAClient, resolve_opa_client,
)

TENANT_ID = "tenant-abc-123"


@pytest.fixture
def mock_opa():
    return MockOPAClient()


class TestOPADecision:

    def test_allow_true(self):
        d = OPADecision(allow=True)
        assert d.allow
        assert not d.denied
        assert d.reason() == "Allowed"

    def test_allow_false_with_violations(self):
        d = OPADecision(allow=False, violations=["SoD violation"])
        assert d.denied
        assert "SoD" in d.reason()

    def test_deny_without_violations(self):
        d = OPADecision(allow=False)
        assert "Denied" in d.reason()


class TestMockOPAClient:

    def test_default_allow(self, mock_opa):
        d = mock_opa.evaluate("zoiko/freight_dispute", {"action": "READ_CASE"})
        assert d.allow

    def test_set_denial(self, mock_opa):
        mock_opa.set_decision("zoiko/freight_dispute", OPADecision(allow=False, violations=["Role required: manager"]))
        d = mock_opa.evaluate("zoiko/freight_dispute", {"action": "APPROVE_PROPOSAL"})
        assert d.denied
        assert "manager" in d.violations[0]

    def test_call_count_tracked(self, mock_opa):
        mock_opa.evaluate("zoiko/freight_dispute", {})
        mock_opa.evaluate("zoiko/tenant_isolation", {})
        assert mock_opa.call_count == 2

    def test_last_input_correct(self, mock_opa):
        inp = {"action": "PROPOSE_RECOVERY", "roles": ["analyst"], "tenant_id": TENANT_ID}
        mock_opa.evaluate("zoiko/freight_dispute", inp)
        assert mock_opa.last_input()["action"] == "PROPOSE_RECOVERY"

    def test_last_input_by_policy(self, mock_opa):
        mock_opa.evaluate("zoiko/freight_dispute",   {"action": "A"})
        mock_opa.evaluate("zoiko/tenant_isolation",  {"action": "B"})
        assert mock_opa.last_input("zoiko/tenant_isolation")["action"] == "B"


class TestOPAFreightDisputeLogic:
    """
    These tests simulate what OPA would decide if running locally.
    They validate the *input shape* that our code would send to OPA.
    """

    def test_analyst_can_propose(self, mock_opa):
        mock_opa.set_decision("zoiko/freight_dispute", OPADecision(allow=True))
        d = mock_opa.check_freight_dispute({
            "action":          "PROPOSE_RECOVERY",
            "roles":           ["analyst"],
            "tenant_id":       TENANT_ID,
            "claim_tenant_id": TENANT_ID,
        })
        assert d.allow

    def test_sod_violation_blocked(self, mock_opa):
        mock_opa.set_decision(
            "zoiko/freight_dispute",
            OPADecision(allow=False, violations=["SoD violation: proposer and approver are the same person"])
        )
        d = mock_opa.check_freight_dispute({
            "action":       "APPROVE_PROPOSAL",
            "roles":        ["manager"],
            "proposer_sub": "alice@zoikotech.com",
            "actor_sub":    "alice@zoikotech.com",   # same person!
            "tenant_id":    TENANT_ID,
        })
        assert d.denied
        assert any("SoD" in v for v in d.violations)

    def test_tenant_isolation_same_tenant_allowed(self, mock_opa):
        d = mock_opa.check_tenant_isolation(
            claim_tenant    = TENANT_ID,
            resource_tenant = TENANT_ID,
            roles           = ["analyst"],
        )
        assert d.allow

    def test_tenant_isolation_cross_tenant_denied(self, mock_opa):
        mock_opa.set_decision("zoiko/tenant_isolation", OPADecision(
            allow=False, violations=["Tenant isolation violation"]
        ))
        d = mock_opa.check_tenant_isolation(
            claim_tenant    = TENANT_ID,
            resource_tenant = "tenant-other-999",
            roles           = ["analyst"],
        )
        assert d.denied


class TestOPAUnavailable:

    def test_real_client_unreachable_raises(self):
        """OPA on port 19999 does not exist — must raise OPAUnavailableError (fail-closed)."""
        client = OPAClient(opa_url="http://localhost:19999", timeout=0.5)
        with pytest.raises(OPAUnavailableError):
            client.evaluate("zoiko/freight_dispute", {})

    def test_real_client_health_false_when_down(self):
        client = OPAClient(opa_url="http://localhost:19999", timeout=0.5)
        assert client.health() is False


class TestFailClosedOPAClient:
    """No real OPA configured in production must never silently allow."""

    def test_evaluate_raises(self):
        client = FailClosedOPAClient()
        with pytest.raises(OPAUnavailableError):
            client.evaluate("zoiko/freight_dispute", {})

    def test_check_freight_dispute_raises(self):
        client = FailClosedOPAClient()
        with pytest.raises(OPAUnavailableError):
            client.check_freight_dispute({"action": "APPROVE_PROPOSAL"})

    def test_health_false(self):
        assert FailClosedOPAClient().health() is False


class TestResolveOPAClient:
    """Single source of truth for client selection — this is the regression
    guard for the bug where production (OPA_URL unset, dev_mode=False) used
    to silently resolve to MockOPAClient(allow=True)."""

    def test_opa_url_set_uses_real_client_regardless_of_dev_mode(self):
        client = resolve_opa_client("http://localhost:8181", dev_mode=False)
        assert isinstance(client, OPAClient)
        assert not isinstance(client, (MockOPAClient, FailClosedOPAClient))

    def test_no_url_and_dev_mode_uses_mock(self):
        client = resolve_opa_client("", dev_mode=True)
        assert isinstance(client, MockOPAClient)

    def test_no_url_and_not_dev_mode_fails_closed(self):
        """The production-default case: no OPA_URL, ZOIKO_DEV_MODE=false."""
        client = resolve_opa_client("", dev_mode=False)
        assert isinstance(client, FailClosedOPAClient)
        with pytest.raises(OPAUnavailableError):
            client.check_freight_dispute({"action": "ACCESS"})
