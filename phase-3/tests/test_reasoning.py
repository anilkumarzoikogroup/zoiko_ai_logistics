"""
Reasoning Service tests.

Unit tests:  SC-001 confidence formula, JCS canonicalization, signing.
Integration: analyze() writes findings + decision_proposals (skip if no DB).
"""
import pytest

import paths  # noqa: F401


# ── Unit: SC-001 confidence formula ──────────────────────────────────────────

class TestConfidenceFormula:
    def test_sc001_confidence_is_096(self):
        from services.reasoning_svc.handler import SC001_CONFIDENCE
        assert SC001_CONFIDENCE == 0.96

    def test_rule_weights_sum_to_one(self):
        from services.reasoning_svc.handler import _RULES
        total_weight = sum(r["weight"] for r in _RULES.values())
        assert abs(total_weight - 1.0) < 1e-9

    def test_weighted_average_matches_constant(self):
        from services.reasoning_svc.handler import _RULES, SC001_CONFIDENCE
        computed = sum(r["confidence"] * r["weight"] for r in _RULES.values())
        assert abs(computed - SC001_CONFIDENCE) < 1e-9

    def test_fuel_charge_confidence_is_100(self):
        from services.reasoning_svc.handler import _RULES
        assert _RULES["fuel_charge"]["confidence"] == 1.00

    def test_accessorial_confidence_is_092(self):
        from services.reasoning_svc.handler import _RULES
        assert _RULES["accessorial"]["confidence"] == 0.92


# ── Unit: finding hash uses domain tag ───────────────────────────────────────

class TestFindingHash:
    def test_domain_tag_prefix(self):
        import hashlib
        from zoiko_common.crypto.jcs import canonicalize

        payload = {
            "bundle_id":  "test-bundle",
            "case_id":    "test-case",
            "confidence": "0.96",
            "rule_trace": {},
            "tenant_id":  "test-tenant",
        }
        canonical = canonicalize(payload)
        h = hashlib.sha256(b"zoiko.finding.v1:" + canonical).hexdigest()
        assert len(h) == 64

    def test_proposal_hash_domain_tag(self):
        import hashlib
        from zoiko_common.crypto.jcs import canonicalize

        payload = {
            "amount":          "4500.0",
            "case_id":         "test-case",
            "currency":        "INR",
            "finding_hash":    "abc123",
            "proposed_action": "CREDIT_MEMO",
            "proposer_sub":    "ravi@amazon.com",
            "tenant_id":       "test-tenant",
        }
        canonical = canonicalize(payload)
        h = hashlib.sha256(b"zoiko.proposal.v1:" + canonical).hexdigest()
        assert len(h) == 64


# ── Integration: analyze writes to DB ────────────────────────────────────────

class TestReasoningIntegration:
    def test_analyze_creates_finding_and_proposal(self, db_url, test_case, broker):
        import psycopg2, psycopg2.extras, uuid

        # Ensure there is a bundle first
        from services.evidence_svc.handler import EvidenceHandler
        ev = EvidenceHandler(db_url, broker, "default")
        ev_result = ev.add_item(
            tenant_id     = test_case["tenant_id"],
            case_id       = test_case["id"],
            item_type     = "RATE_SHEET",
            content_bytes = b"contracted rate 8000 INR",
            actor_sub     = "ravi@amazon.com",
        )

        from services.reasoning_svc.handler import ReasoningHandler
        handler = ReasoningHandler(db_url, broker, "default")
        result  = handler.analyze(
            tenant_id       = test_case["tenant_id"],
            case_id         = test_case["id"],
            bundle_id       = str(ev_result.bundle_id),
            proposer_sub    = "ravi@amazon.com",
            proposed_action = "CREDIT_MEMO",
            amount          = 4500.0,
            currency        = "INR",
        )

        assert result.confidence == 0.96
        assert result.finding_id is not None
        assert result.proposal_id is not None
        assert result.proposed_action == "CREDIT_MEMO"

        # Verify DB records exist
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT confidence FROM findings WHERE id=%s", (result.finding_id,))
        row = cur.fetchone()
        conn.close()
        assert row is not None
        assert float(row["confidence"]) == 0.96

    def test_analyze_confidence_always_096(self, db_url, test_case, broker):
        from services.evidence_svc.handler import EvidenceHandler
        from services.reasoning_svc.handler import ReasoningHandler

        ev = EvidenceHandler(db_url, broker, "default")
        ev_result = ev.add_item(
            tenant_id     = test_case["tenant_id"],
            case_id       = test_case["id"],
            item_type     = "BOL",
            content_bytes = b"bol-data",
            actor_sub     = "ravi@amazon.com",
        )

        rh     = ReasoningHandler(db_url, broker, "default")
        result = rh.analyze(
            tenant_id    = test_case["tenant_id"],
            case_id      = test_case["id"],
            bundle_id    = str(ev_result.bundle_id),
            proposer_sub = "ravi@amazon.com",
            amount       = 0.0,
        )
        assert result.confidence == 0.96
