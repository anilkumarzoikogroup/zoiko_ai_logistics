"""
Stub Service tests.

TestSanctions       (3 tests) — fail-closed behaviour
TestFXLock          (3 tests) — acquire + validate + SC-001 determinism
TestGLJournal       (2 tests) — post + list
TestApprovalQueue   (5 tests) — create, get, SoD, approve, reject
TestHTTPRoutes      (6 tests) — FastAPI TestClient
"""
import sys, os
_SVC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SVC not in sys.path:
    sys.path.insert(0, _SVC)

import pytest


# ── Sanctions ─────────────────────────────────────────────────────────────────

class TestSanctions:
    def test_normal_actor_cleared(self):
        from services.stub_svc.sanctions import screen
        r = screen("ramu@amazon.com", "tenant-1")
        assert r.cleared is True

    def test_blocked_actor_not_cleared(self, monkeypatch):
        monkeypatch.setenv("SANCTIONS_BLOCKED_ACTORS", "bad-actor@ofac.gov")
        # Reload module to pick up env change
        import importlib, services.stub_svc.sanctions as m
        importlib.reload(m)
        r = m.screen("bad-actor@ofac.gov", "tenant-1")
        assert r.cleared is False
        importlib.reload(m)   # restore

    def test_unavailable_api_fails_closed(self, monkeypatch):
        monkeypatch.setenv("SANCTIONS_API_URL", "http://127.0.0.1:19999")
        import importlib, services.stub_svc.sanctions as m
        importlib.reload(m)
        r = m.screen("anyone@test.com", "tenant-1")
        assert r.cleared is False
        monkeypatch.delenv("SANCTIONS_API_URL", raising=False)
        importlib.reload(m)


# ── FX Lock ───────────────────────────────────────────────────────────────────

class TestFXLock:
    def test_sc001_inr_4500_locks_usd_220(self):
        from services.stub_svc.fx_lock import acquire
        r = acquire(4500.0, "INR", "env-001")
        assert r.acquired is True
        assert r.locked_amount_usd == 220.0

    def test_usd_locks_same_amount(self):
        from services.stub_svc.fx_lock import acquire
        r = acquire(100.0, "USD", "env-002")
        assert r.acquired is True
        assert r.locked_amount_usd == 100.0

    def test_lock_validate_within_tolerance(self):
        from services.stub_svc.fx_lock import acquire, validate
        r = acquire(4500.0, "INR", "env-003")
        assert validate(r.lock_id, 220.0) is True
        # 10% off = outside 5% tolerance
        assert validate(r.lock_id, 200.0) is False


# ── GL Journal ────────────────────────────────────────────────────────────────

class TestGLJournal:
    def test_post_entry(self):
        from services.stub_svc.gl_journal import post_entry
        r = post_entry("env-gl-001", "tenant-1", 220.0, "test credit")
        assert r.posted is True
        assert r.entry_id != ""

    def test_list_entries(self):
        from services.stub_svc.gl_journal import post_entry, get_entries
        post_entry("env-gl-list", "tenant-list", 50.0, "list test")
        entries = get_entries("tenant-list")
        assert any(e.envelope_id == "env-gl-list" for e in entries)


# ── Approval Queue ────────────────────────────────────────────────────────────

class TestApprovalQueue:
    def test_create_task(self):
        from services.stub_svc.approval_queue import create_task
        t = create_task("env-aq-001", "tenant-1", "ramu@amazon.com", 220.0)
        assert t.state == "PENDING"
        assert t.proposer_sub == "ramu@amazon.com"

    def test_get_task(self):
        from services.stub_svc.approval_queue import create_task, get_task
        t = create_task("env-aq-get", "tenant-1", "ramu@amazon.com", 100.0)
        got = get_task(t.task_id)
        assert got is not None
        assert got.task_id == t.task_id

    def test_sod_violation_raises(self):
        from services.stub_svc.approval_queue import create_task, approve, SoDViolationError
        t = create_task("env-aq-sod", "tenant-1", "ramu@amazon.com", 100.0)
        with pytest.raises(SoDViolationError):
            approve(t.task_id, "ramu@amazon.com", "APPROVED")

    def test_approve_different_actor(self):
        from services.stub_svc.approval_queue import create_task, approve
        t = create_task("env-aq-app", "tenant-1", "ramu@amazon.com", 100.0)
        r = approve(t.task_id, "manager@amazon.com", "APPROVED")
        assert r.decision == "APPROVED"

    def test_reject_task(self):
        from services.stub_svc.approval_queue import create_task, approve
        t = create_task("env-aq-rej", "tenant-1", "ramu@amazon.com", 100.0)
        r = approve(t.task_id, "manager@amazon.com", "REJECTED", reason="amount too high")
        assert r.decision == "REJECTED"


# ── HTTP Routes ───────────────────────────────────────────────────────────────

class TestHTTPRoutes:
    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient
        from services.stub_svc.app import app
        return TestClient(app, raise_server_exceptions=False)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "stub-service"

    def test_sanctions_screen_cleared(self, client):
        r = client.post("/v1/sanctions/screen", json={"actor_sub": "good@amazon.com", "tenant_id": "t1"})
        assert r.status_code == 200
        assert r.json()["cleared"] is True

    def test_fx_lock_sc001(self, client):
        r = client.post("/v1/fx/lock", json={"amount": 4500.0, "currency": "INR", "envelope_id": "http-env-001"})
        assert r.status_code == 200
        assert r.json()["locked_amount_usd"] == 220.0

    def test_gl_journal_post(self, client):
        r = client.post(
            "/v1/gl/journal",
            json={"envelope_id": "http-env-gl", "tenant_id": "t1", "amount_usd": 220.0},
            headers={"Idempotency-Key": "gl-001"},
        )
        assert r.status_code == 201
        assert r.json()["posted"] is True

    def test_approval_create_and_decide_sod(self, client):
        # Create
        r = client.post(
            "/v1/approval/tasks",
            json={"envelope_id": "http-env-aq", "tenant_id": "t1",
                  "proposer_sub": "ramu@amazon.com", "amount_usd": 220.0},
            headers={"Idempotency-Key": "aq-001"},
        )
        assert r.status_code == 201
        task_id = r.json()["task_id"]

        # SoD violation
        r2 = client.post(
            f"/v1/approval/tasks/{task_id}/decide",
            json={"actor_sub": "ramu@amazon.com", "decision": "APPROVED"},
            headers={"Idempotency-Key": "aq-decide-001"},
        )
        assert r2.status_code == 409

    def test_approval_decide_ok(self, client):
        r = client.post(
            "/v1/approval/tasks",
            json={"envelope_id": "http-env-aq2", "tenant_id": "t1",
                  "proposer_sub": "ramu@amazon.com", "amount_usd": 100.0},
            headers={"Idempotency-Key": "aq-002"},
        )
        task_id = r.json()["task_id"]

        r2 = client.post(
            f"/v1/approval/tasks/{task_id}/decide",
            json={"actor_sub": "manager@amazon.com", "decision": "APPROVED"},
            headers={"Idempotency-Key": "aq-decide-002"},
        )
        assert r2.status_code == 200
        assert r2.json()["decision"] == "APPROVED"
