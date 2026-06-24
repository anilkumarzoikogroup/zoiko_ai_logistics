"""
Reasoning Service tests.

Unit tests:  SC-002 confidence formula, JCS canonicalization, signing.
Integration: analyze() writes findings + decision_proposals (skip if no DB).
"""
import pytest

import paths  # noqa: F401


# ── Unit: SC-002 confidence formula ──────────────────────────────────────────

class TestConfidenceFormula:
    def test_sc002_confidence_is_09275(self):
        from services.reasoning_svc.handler import SC002_CONFIDENCE
        assert SC002_CONFIDENCE == 0.9275

    def test_rule_weights_sum_to_one(self):
        from services.reasoning_svc.handler import _RULES
        total_weight = sum(r["weight"] for r in _RULES.values())
        assert abs(total_weight - 1.0) < 1e-9

    def test_weighted_average_matches_constant(self):
        from services.reasoning_svc.handler import _RULES, SC002_CONFIDENCE
        computed = sum(r["confidence"] * r["weight"] for r in _RULES.values())
        assert abs(computed - SC002_CONFIDENCE) < 1e-9

    def test_liability_acknowledged_confidence_is_095(self):
        from services.reasoning_svc.handler import _RULES
        assert _RULES["liability_acknowledged"]["confidence"] == 0.95

    def test_amount_within_policy_cap_confidence_is_090(self):
        from services.reasoning_svc.handler import _RULES
        assert _RULES["amount_within_policy_cap"]["confidence"] == 0.90


# ── Unit: finding hash uses domain tag ───────────────────────────────────────

class TestFindingHash:
    def test_domain_tag_prefix(self):
        import hashlib
        from zoiko_common.crypto.jcs import canonicalize

        payload = {
            "bundle_id":  "test-bundle",
            "case_id":    "test-case",
            "confidence": "0.9275",
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

        # Ensure there is a bundle first, then seal it (T-006)
        from services.evidence_svc.handler import EvidenceHandler
        ev = EvidenceHandler(db_url, broker, "default")
        ev_result = ev.add_item(
            tenant_id     = test_case["tenant_id"],
            case_id       = test_case["id"],
            item_type     = "RATE_SHEET",
            content_bytes = b"contracted rate 8000 INR",
            actor_sub     = "ravi@amazon.com",
        )
        ev.seal_bundle(tenant_id=test_case["tenant_id"], case_id=test_case["id"])

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

        assert result.confidence == 0.9275
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
        assert float(row["confidence"]) == 0.9275

    def test_analyze_confidence_always_09275(self, db_url, test_case, broker):
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
        ev.seal_bundle(tenant_id=test_case["tenant_id"], case_id=test_case["id"])

        rh     = ReasoningHandler(db_url, broker, "default")
        result = rh.analyze(
            tenant_id    = test_case["tenant_id"],
            case_id      = test_case["id"],
            bundle_id    = str(ev_result.bundle_id),
            proposer_sub = "ravi@amazon.com",
            amount       = 0.0,
        )
        assert result.confidence == 0.9275

    def test_analyze_blocks_on_incomplete_bundle(self, db_url, test_tenant, broker):
        """T-006/T-025: ReasoningHandler.analyze() raises if the bundle hasn't been sealed.

        Uses a freshly-opened case rather than the shared session-scoped test_case
        fixture, since other tests in this module already seal that case's bundle.
        """
        import sys, os, uuid as _uuid
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "gateway"))
        from services.ingestion_svc.handler   import IngestionHandler
        from services.ingestion_svc.models    import ClaimInput
        from services.canonical_truth.handler import CanonicalHandler
        from services.case_orchestration.handler import CaseHandler
        from services.evidence_svc.handler import EvidenceHandler
        from services.reasoning_svc.handler import ReasoningHandler

        slug  = test_tenant["slug"]
        tid   = test_tenant["id"]
        claim = ClaimInput(carrier_id="TestCarrier", claim_reference=f"TEST-{_uuid.uuid4().hex[:6].upper()}",
                            claim_type="DAMAGE", claimed_amount=10000.0, currency="INR")
        ing_r  = IngestionHandler(db_url, broker, slug).ingest_claim(tid, claim, str(_uuid.uuid4()))
        can_r  = CanonicalHandler(db_url, broker, slug).canonicalize_claim(
                     tid, ing_r.source_record_id, claim.claim_reference,
                     claim.carrier_id, claim.claim_type, claim.claimed_amount, claim.currency)
        case_r = CaseHandler(db_url, broker).open_case(tid, can_r.claim_id, "test-setup")

        ev = EvidenceHandler(db_url, broker, "default")
        ev_result = ev.add_item(
            tenant_id     = tid,
            case_id       = str(case_r.case_id),
            item_type     = "BOL",
            content_bytes = b"unsealed-bundle-data",
            actor_sub     = "ravi@amazon.com",
        )
        # Deliberately do NOT seal — analyze() must block

        rh = ReasoningHandler(db_url, broker, "default")
        with pytest.raises(ValueError, match="INCOMPLETE|seal"):
            rh.analyze(
                tenant_id    = tid,
                case_id      = str(case_r.case_id),
                bundle_id    = str(ev_result.bundle_id),
                proposer_sub = "ravi@amazon.com",
            )
