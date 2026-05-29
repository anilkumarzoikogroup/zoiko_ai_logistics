# tests/test_reasoning.py

import uuid

from services.reasoning_svc.handler import (
    ReasoningHandler,
    SC001_CONFIDENCE,
)


# =========================================================
# TEST: BASIC IMPORT
# =========================================================

def test_import():
    print("\n[TEST] Import successful")
    assert ReasoningHandler is not None


# =========================================================
# TEST: REAL GROQ + REAL DB
# =========================================================

def test_real_groq_and_db():

    print("\n====================================")
    print("[TEST] Starting Real Integration Test")
    print("====================================")

    handler = ReasoningHandler()

    result = handler.analyze(
        tenant_id     = "tenant-prod",
        case_id       = str(uuid.uuid4()),
        bundle_id     = str(uuid.uuid4()),
        proposer_sub  = "real@test.com",
        proposed_action = "REVIEW",
        amount        = 12500.0,        # ← invoice amount
        currency      = "INR",          # ← Indian rupees
        carrier       = "BlueDart",     # ← NEW
        route         = "Hyderabad → Mumbai",  # ← NEW
        contract_rate = 10000.0,        # ← NEW: agreed contract rate
    )

    # =====================================================
    # PRINT RESULTS
    # =====================================================

    print("\n============= FINAL RESULT =============")
    print(f"Finding ID:   {result.finding_id}")
    print(f"Proposal ID:  {result.proposal_id}")
    print(f"\nTenant ID:    {result.tenant_id}")
    print(f"Case ID:      {result.case_id}")
    print(f"Bundle ID:    {result.bundle_id}")
    print(f"\nAI Confidence:   {result.ai_confidence}")
    print(f"Risk Level:      {result.risk_level}")
    print(f"\nAI Reasoning:")
    print(result.ai_reasoning)
    print(f"\nFinal Confidence: {result.confidence}")
    print(f"\nRule Trace:")
    print(result.rule_trace)
    print("\n========================================")

    # =====================================================
    # ASSERTIONS
    # =====================================================

    assert result is not None
    assert result.finding_id is not None
    assert result.proposal_id is not None

    # AI confidence should be meaningful now (not 0.35)
    assert result.ai_confidence > 0.5, (
        f"AI confidence too low ({result.ai_confidence}) — "
        "check Groq is receiving carrier/route/contract_rate"
    )

    assert result.risk_level in ["LOW", "MEDIUM", "HIGH"]

    assert result.rule_trace is not None
    assert result.rule_trace["weighted_average"] == SC001_CONFIDENCE

    # Overcharge is 25% (12500 vs 10000) — should flag as MEDIUM or HIGH
    assert result.risk_level in ["MEDIUM", "HIGH"], (
        f"Expected MEDIUM or HIGH risk for 25% overcharge, got {result.risk_level}"
    )

    # Final confidence should be high since rule engine is strong
    assert result.confidence > 0.80, (
        f"Final confidence too low: {result.confidence}"
    )


# =========================================================
# TEST: REAL GROQ — LOW OVERCHARGE SCENARIO
# =========================================================

def test_low_overcharge_scenario():

    print("\n====================================")
    print("[TEST] Low Overcharge Scenario")
    print("====================================")

    handler = ReasoningHandler()

    result = handler.analyze(
        tenant_id     = "tenant-prod",
        case_id       = str(uuid.uuid4()),
        bundle_id     = str(uuid.uuid4()),
        proposer_sub  = "real@test.com",
        proposed_action = "REVIEW",
        amount        = 10200.0,   # only 2% over contract
        currency      = "INR",
        carrier       = "DTDC",
        route         = "Delhi → Bangalore",
        contract_rate = 10000.0,
    )

    print(f"AI Confidence: {result.ai_confidence}")
    print(f"Risk Level:    {result.risk_level}")
    print(f"AI Reasoning:  {result.ai_reasoning}")
    print(f"Final Conf:    {result.confidence}")

    assert result is not None
    assert result.ai_confidence > 0
    assert result.risk_level in ["LOW", "MEDIUM", "HIGH"]


# =========================================================
# TEST: DB CONNECTION
# =========================================================

def test_db_connection():

    handler = ReasoningHandler()

    print("\n====================================")
    print("[TEST] DB URL")
    print("====================================")
    print(handler.db_url)

    assert handler.db_url is not None