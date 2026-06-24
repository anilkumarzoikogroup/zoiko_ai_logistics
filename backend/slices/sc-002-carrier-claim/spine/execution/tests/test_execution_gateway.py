"""
Phase 4 — Execution Gateway tests.

Tests cover:
  T-001  Expired token rejected at Gate 2
  T-002  Scope validation — unknown scope blocked at Gate 5
  T-003  Gate results list has exactly 8 entries
  T-004  Full end-to-end via HTTP (integration, skipped if no DB)
"""
import uuid
import pytest
import paths  # noqa: F401

from services.execution_gateway.handler import ExecutionGateway
from services.execution_gateway.models  import ExecutionRequest, GateResult


class TestGateValidation:
    """Unit tests for individual gate logic — no DB required."""

    def _gw(self):
        from kafka.mock_kafka import MockKafkaBroker
        return ExecutionGateway("unused-url", MockKafkaBroker())

    def _make_token(self, **overrides) -> dict:
        from datetime import datetime, timezone, timedelta
        base = {
            "id":            str(uuid.uuid4()),
            "tenant_id":     "11111111-1111-1111-1111-111111111111",
            "decision_id":   str(uuid.uuid4()),
            "scope":         "EXECUTE_CREDIT_MEMO",
            "tenant_binding": b"\x00" * 32,
            "status":        "ACTIVE",
            "expires_at":    datetime.now(timezone.utc) + timedelta(minutes=10),
            "token_hash":    b"\x00" * 32,
            "token_hash_hex": "0" * 64,
            "signature":     b"\x00" * 64,
            "kid":           "test-kid",
            "amount":        4500.0,
            "currency":      "INR",
            "case_id":       str(uuid.uuid4()),
        }
        base.update(overrides)
        return base

    def test_gate2_rejects_expired_token(self, monkeypatch):
        from datetime import datetime, timezone, timedelta
        monkeypatch.delenv("ZOIKO_DEV_MODE", raising=False)
        gw    = self._gw()
        token = self._make_token(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        result = gw._gate2_expiry(token)
        assert result.passed is False
        assert result.gate == 2

    def test_gate2_passes_valid_token(self):
        from datetime import datetime, timezone, timedelta
        gw    = self._gw()
        token = self._make_token(expires_at=datetime.now(timezone.utc) + timedelta(minutes=5))
        result = gw._gate2_expiry(token)
        assert result.passed is True

    def test_gate5_rejects_unknown_scope(self):
        gw    = self._gw()
        token = self._make_token(scope="UNKNOWN_SCOPE")
        result = gw._gate5_scope(token)
        assert result.passed is False
        assert result.gate == 5

    def test_gate5_accepts_credit_memo(self):
        gw    = self._gw()
        token = self._make_token(scope="EXECUTE_CREDIT_MEMO")
        result = gw._gate5_scope(token)
        assert result.passed is True

    def test_gate3_rejects_consumed_token(self):
        gw    = self._gw()
        token = self._make_token(status="CONSUMED")
        result = gw._gate3_consumed(token)
        assert result.passed is False
        assert result.gate == 3

    def test_run_gates_returns_8_results(self):
        import os, hashlib
        tenant_id   = "11111111-1111-1111-1111-111111111111"
        decision_id = str(uuid.uuid4())
        binding     = hashlib.sha256(tenant_id.encode() + decision_id.encode()).digest()
        token = self._make_token(
            tenant_id      = tenant_id,
            decision_id    = decision_id,
            tenant_binding = binding,
        )
        req = ExecutionRequest(
            token_id  = token["id"],
            tenant_id = token["tenant_id"],
            actor_sub = "test-user",
        )
        _prev = os.environ.get("ZOIKO_DEV_MODE")
        os.environ["ZOIKO_DEV_MODE"] = "true"
        try:
            gw      = self._gw()
            results = gw._run_gates(token, req)
        finally:
            if _prev is None:
                os.environ.pop("ZOIKO_DEV_MODE", None)
            else:
                os.environ["ZOIKO_DEV_MODE"] = _prev
        assert len(results) == 8
        for r in results:
            assert isinstance(r, GateResult)
            assert 1 <= r.gate <= 8


class TestExecutionGatewayIntegration:
    """Full end-to-end tests — skipped if PostgreSQL not reachable."""

    @pytest.mark.skipif(True, reason="Requires fully populated DB from Phases 2+3 demo")
    def test_execute_live_token(self, db_url, test_tenant, broker):
        gw = ExecutionGateway(db_url, broker, test_tenant["slug"])
        # This test requires an ACTIVE token from a completed Phase 3 flow.
        # Run demo_phase2.py + demo_phase3.py first to populate the DB.
        rows = __import__("shared.db", fromlist=["q"]).q(
            "SELECT id FROM governance_tokens WHERE tenant_id=%s::uuid AND status='ACTIVE' LIMIT 1",
            (test_tenant["id"],),
            db_url=db_url,
        )
        if not rows:
            pytest.skip("No ACTIVE token in DB — run Phase 2+3 demo first")
        token_id = str(rows[0]["id"])
        req = ExecutionRequest(token_id=token_id, tenant_id=test_tenant["id"], actor_sub="test-user")
        result = gw.execute(req)
        assert result.status == "DISPATCHED"
        assert result.token_id == token_id
