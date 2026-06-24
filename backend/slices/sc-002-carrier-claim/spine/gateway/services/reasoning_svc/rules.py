"""SC-002 deterministic rule weights — carrier claim.

Example bundle — illustrative starting point for a real claims-adjustment rule
owner to refine. Deterministic the same way SC001_CONFIDENCE is.
"""

RULES = {
    "liability_acknowledged":   {"confidence": 0.95, "weight": 0.55},
    "amount_within_policy_cap": {"confidence": 0.90, "weight": 0.45},
}

SC002_CONFIDENCE = round(
    sum(r["confidence"] * r["weight"] for r in RULES.values()), 4
)  # = 0.9275
