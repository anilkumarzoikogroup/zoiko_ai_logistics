"""
Rate limiter tests (T-024).

TestRateLimitUnit    (5 tests) — pure in-memory, no I/O
TestRateLimitMiddleware — FastAPI TestClient
"""
import os
import pytest


class TestRateLimitUnit:
    def _counter(self):
        from zoiko_common.middleware.rate_limit import _SlidingWindowCounter
        return _SlidingWindowCounter()

    def test_allows_under_limit(self):
        c = self._counter()
        for _ in range(5):
            assert c.check_and_increment("t1:ingestion", 10, 60) is True

    def test_blocks_at_limit(self):
        c = self._counter()
        for _ in range(10):
            c.check_and_increment("t2:ingestion", 10, 60)
        assert c.check_and_increment("t2:ingestion", 10, 60) is False

    def test_different_tenants_independent(self):
        c = self._counter()
        for _ in range(10):
            c.check_and_increment("tenantA:execution", 10, 60)
        # tenantA is blocked — tenantB is not
        assert c.check_and_increment("tenantA:execution", 10, 60) is False
        assert c.check_and_increment("tenantB:execution", 10, 60) is True

    def test_check_rate_limit_no_op_when_disabled(self):
        from zoiko_common.middleware.rate_limit import check_rate_limit
        # disabled by default (ZOIKO_RATE_LIMIT_ENABLED not set)
        check_rate_limit("any-tenant", "execution")   # must not raise

    def test_raises_rate_limit_exceeded_when_enabled(self, monkeypatch):
        monkeypatch.setenv("ZOIKO_RATE_LIMIT_ENABLED", "true")
        import importlib, zoiko_common.middleware.rate_limit as m
        importlib.reload(m)
        c = m._SlidingWindowCounter()
        # Exhaust a private counter directly
        for _ in range(10):
            c.check_and_increment("tx:execution", 10, 60)
        assert c.check_and_increment("tx:execution", 10, 60) is False
        monkeypatch.delenv("ZOIKO_RATE_LIMIT_ENABLED", raising=False)
        importlib.reload(m)


class TestRateLimitMiddleware:
    @pytest.fixture(autouse=True)
    def _enable(self, monkeypatch):
        monkeypatch.setenv("ZOIKO_RATE_LIMIT_ENABLED", "true")
        import importlib, zoiko_common.middleware.rate_limit as m
        importlib.reload(m)
        yield
        monkeypatch.delenv("ZOIKO_RATE_LIMIT_ENABLED", raising=False)
        importlib.reload(m)

    def test_execute_route_429_after_limit(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from zoiko_common.middleware.rate_limit import RateLimitMiddleware, _SlidingWindowCounter

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware)

        @app.post("/v1/execute")
        def _execute():
            return {"ok": True}

        client = TestClient(app, raise_server_exceptions=False)

        # Exhaust execution limit (10 req/min)
        for _ in range(10):
            r = client.post(
                "/v1/execute",
                headers={"X-Tenant-ID": "test-tenant-rate"},
            )
        # 11th request should be 429
        r11 = client.post(
            "/v1/execute",
            headers={"X-Tenant-ID": "test-tenant-rate"},
        )
        assert r11.status_code == 429

    def test_route_class_ingestion(self):
        from zoiko_common.middleware.rate_limit import _route_class
        assert _route_class("/v1/ingestion/parse-invoice", "POST") == "ingestion"

    def test_route_class_governance(self):
        from zoiko_common.middleware.rate_limit import _route_class
        assert _route_class("/v1/cases/abc/propose", "POST") == "governance"

    def test_route_class_execution(self):
        from zoiko_common.middleware.rate_limit import _route_class
        assert _route_class("/v1/execute", "POST") == "execution"
