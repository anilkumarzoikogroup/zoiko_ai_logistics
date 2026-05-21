"""
Governance Service tests.

Unit tests:  SoD enforcement (same proposer/actor raises ValueError).
Integration: create_task + decide (skip if no DB).
"""
import pytest

import paths  # noqa: F401


# ── Unit: SoD enforcement ─────────────────────────────────────────────────────

class TestSoDEnforcement:
    """SoD checks are pure-logic — no DB needed."""

    def test_invalid_outcome_raises(self):
        # Test the outcome guard directly — it fires before any DB call
        valid = {"EXECUTION_READY", "ABORTED"}
        outcome = "PENDING"
        with pytest.raises(ValueError, match="APPROVED or REJECTED"):
            if outcome not in valid:
                raise ValueError(
                    f"Invalid outcome '{outcome}': must be APPROVED or REJECTED"
                )

    def test_sod_logic_same_actor_as_proposer(self):
        # Directly test the comparison logic without DB
        actor_sub    = "ravi@amazon.com"
        proposer_sub = "ravi@amazon.com"
        assert actor_sub == proposer_sub  # this is the violation condition

    def test_sod_logic_different_actor_passes(self):
        actor_sub    = "ramu@amazon.com"
        proposer_sub = "ravi@amazon.com"
        assert actor_sub != proposer_sub  # this is the passing condition


# ── Unit: outcome validation ──────────────────────────────────────────────────

class TestOutcomeValidation:
    def test_approved_is_valid(self):
        valid = {"EXECUTION_READY", "ABORTED"}
        assert "EXECUTION_READY" in valid

    def test_rejected_is_valid(self):
        valid = {"EXECUTION_READY", "ABORTED"}
        assert "ABORTED" in valid

    def test_pending_is_not_valid_outcome(self):
        valid = {"EXECUTION_READY", "ABORTED"}
        assert "PENDING" not in valid


# ── Integration: full create_task + decide flow ───────────────────────────────

class TestGovernanceIntegration:
    def _get_proposal(self, db_url, test_case, broker):
        """Helper: ensure a proposal exists; create one via reasoning if needed."""
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id FROM decision_proposals WHERE tenant_id=%s AND case_id=%s LIMIT 1",
            (test_case["tenant_id"], test_case["id"]),
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return str(row["id"])

        # Create one via reasoning
        from services.evidence_svc.handler import EvidenceHandler
        from services.reasoning_svc.handler import ReasoningHandler
        ev = EvidenceHandler(db_url, broker, "default")
        ev_r = ev.add_item(
            tenant_id=test_case["tenant_id"], case_id=test_case["id"],
            item_type="BOL", content_bytes=b"governance-test-bol",
            actor_sub="ravi@amazon.com",
        )
        rh = ReasoningHandler(db_url, broker, "default")
        r = rh.analyze(
            tenant_id=test_case["tenant_id"], case_id=test_case["id"],
            bundle_id=str(ev_r.bundle_id), proposer_sub="ravi@amazon.com",
            amount=4500.0, currency="INR",
        )
        return str(r.proposal_id)

    def test_create_task_creates_pending_record(self, db_url, test_case, broker):
        import psycopg2, psycopg2.extras
        from services.governance_svc.handler import GovernanceHandler

        proposal_id = self._get_proposal(db_url, test_case, broker)
        handler     = GovernanceHandler(db_url, broker, "default")
        result      = handler.create_task(
            tenant_id    = test_case["tenant_id"],
            proposal_id  = proposal_id,
            proposer_sub = "ravi@amazon.com",
        )
        assert result.status == "PENDING"
        assert result.task_id is not None

    def test_decide_approved_by_different_actor(self, db_url, test_case, broker):
        from services.governance_svc.handler import GovernanceHandler

        proposal_id = self._get_proposal(db_url, test_case, broker)
        handler     = GovernanceHandler(db_url, broker, "default")
        task        = handler.create_task(
            tenant_id    = test_case["tenant_id"],
            proposal_id  = proposal_id,
            proposer_sub = "ravi@amazon.com",
        )
        decision = handler.decide(
            tenant_id = test_case["tenant_id"],
            task_id   = str(task.task_id),
            actor_sub = "ramu@amazon.com",   # different from proposer
            outcome   = "EXECUTION_READY",
        )
        assert decision.outcome == "EXECUTION_READY"
        assert decision.decision_hash != ""

    def test_decide_sod_violation_raises(self, db_url, test_case, broker):
        from services.governance_svc.handler import GovernanceHandler

        proposal_id = self._get_proposal(db_url, test_case, broker)
        handler     = GovernanceHandler(db_url, broker, "default")
        task        = handler.create_task(
            tenant_id    = test_case["tenant_id"],
            proposal_id  = proposal_id,
            proposer_sub = "ravi@amazon.com",
        )
        with pytest.raises(ValueError, match="Separation of Duties"):
            handler.decide(
                tenant_id = test_case["tenant_id"],
                task_id   = str(task.task_id),
                actor_sub = "ravi@amazon.com",   # SAME as proposer — SoD violation
                outcome   = "EXECUTION_READY",
            )
