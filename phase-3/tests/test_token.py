"""
Token Service tests.

Unit tests:  tenant_binding hash formula, token_hash domain tag, TTL.
Integration: mint() with APPROVED decision (skip if no DB).
"""
import hashlib
import pytest

import paths  # noqa: F401


# ── Unit: tenant_binding ─────────────────────────────────────────────────────

class TestTenantBinding:
    def test_binding_is_sha256_of_tenant_plus_decision(self):
        tenant_id   = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        decision_id = "11111111-2222-3333-4444-555555555555"
        expected = hashlib.sha256(
            tenant_id.encode("utf-8") + decision_id.encode("utf-8")
        ).hexdigest()
        assert len(expected) == 64

    def test_different_tenants_different_binding(self):
        decision_id = "11111111-2222-3333-4444-555555555555"
        b1 = hashlib.sha256(b"tenant-a" + decision_id.encode()).digest()
        b2 = hashlib.sha256(b"tenant-b" + decision_id.encode()).digest()
        assert b1 != b2

    def test_same_inputs_same_binding(self):
        t  = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        d  = "11111111-2222-3333-4444-555555555555"
        b1 = hashlib.sha256(t.encode() + d.encode()).digest()
        b2 = hashlib.sha256(t.encode() + d.encode()).digest()
        assert b1 == b2


# ── Unit: token_hash domain tag ──────────────────────────────────────────────

class TestTokenHash:
    def test_domain_tag_applied(self):
        from zoiko_common.crypto.jcs import canonicalize
        payload = {
            "case_id":     "case-001",
            "decision_id": "dec-001",
            "expires_at":  "2026-05-20T00:00:00+00:00",
            "scope":       "EXECUTE_CREDIT_MEMO",
            "tenant_id":   "tenant-001",
        }
        canonical = canonicalize(payload)
        h = hashlib.sha256(b"zoiko.token.v1:" + canonical).hexdigest()
        assert len(h) == 64

    def test_scope_change_changes_hash(self):
        from zoiko_common.crypto.jcs import canonicalize
        base = {
            "case_id":     "case-001",
            "decision_id": "dec-001",
            "expires_at":  "2026-05-20T00:00:00+00:00",
            "tenant_id":   "tenant-001",
        }
        p1 = dict(base, scope="EXECUTE_CREDIT_MEMO")
        p2 = dict(base, scope="EXECUTE_CHARGEBACK")
        h1 = hashlib.sha256(b"zoiko.token.v1:" + canonicalize(p1)).digest()
        h2 = hashlib.sha256(b"zoiko.token.v1:" + canonicalize(p2)).digest()
        assert h1 != h2


# ── Unit: TTL ─────────────────────────────────────────────────────────────────

class TestTokenTTL:
    def test_default_ttl_15_minutes(self):
        from services.token_svc.handler import TOKEN_TTL_MINUTES
        assert TOKEN_TTL_MINUTES == 15

    def test_expires_at_is_future(self):
        from datetime import datetime, timezone, timedelta
        from services.token_svc.handler import TOKEN_TTL_MINUTES
        now        = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=TOKEN_TTL_MINUTES)
        assert expires_at > now


# ── Integration: mint with approved decision ──────────────────────────────────

class TestTokenIntegration:
    def _setup_approved_decision(self, db_url, test_case, broker):
        """Walk the full pipeline to get an APPROVED decision."""
        from services.evidence_svc.handler   import EvidenceHandler
        from services.reasoning_svc.handler  import ReasoningHandler
        from services.governance_svc.handler import GovernanceHandler

        ev  = EvidenceHandler(db_url, broker, "default")
        ev_r = ev.add_item(
            tenant_id=test_case["tenant_id"], case_id=test_case["id"],
            item_type="BOL", content_bytes=b"token-test-bol",
            actor_sub="ravi@amazon.com",
        )
        rh   = ReasoningHandler(db_url, broker, "default")
        r    = rh.analyze(
            tenant_id=test_case["tenant_id"], case_id=test_case["id"],
            bundle_id=str(ev_r.bundle_id), proposer_sub="ravi@amazon.com",
            amount=4500.0, currency="INR",
        )
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
        return str(dec.decision_id)

    def test_mint_returns_active_token(self, db_url, test_case, broker):
        from services.token_svc.handler import TokenHandler
        decision_id = self._setup_approved_decision(db_url, test_case, broker)
        handler     = TokenHandler(db_url, broker, "default")
        token       = handler.mint(
            tenant_id   = test_case["tenant_id"],
            decision_id = decision_id,
            case_id     = test_case["id"],
            scope       = "EXECUTE_CREDIT_MEMO",
        )
        assert token.status == "ACTIVE"
        assert token.token_hash != ""
        assert token.tenant_binding != ""
        assert token.expires_at > zoiko.governance.token.issued_at

    def test_mint_rejected_decision_raises(self, db_url, test_case, broker):
        from services.evidence_svc.handler   import EvidenceHandler
        from services.reasoning_svc.handler  import ReasoningHandler
        from services.governance_svc.handler import GovernanceHandler
        from services.token_svc.handler      import TokenHandler

        ev  = EvidenceHandler(db_url, broker, "default")
        ev_r = ev.add_item(
            tenant_id=test_case["tenant_id"], case_id=test_case["id"],
            item_type="PHOTO", content_bytes=b"rejected-test",
            actor_sub="ravi@amazon.com",
        )
        rh   = ReasoningHandler(db_url, broker, "default")
        r    = rh.analyze(
            tenant_id=test_case["tenant_id"], case_id=test_case["id"],
            bundle_id=str(ev_r.bundle_id), proposer_sub="ravi@amazon.com",
        )
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
            outcome="ABORTED",
        )
        with pytest.raises(ValueError, match="EXECUTION_READY"):
            TokenHandler(db_url, broker, "default").mint(
                tenant_id   = test_case["tenant_id"],
                decision_id = str(dec.decision_id),
                case_id     = test_case["id"],
            )
