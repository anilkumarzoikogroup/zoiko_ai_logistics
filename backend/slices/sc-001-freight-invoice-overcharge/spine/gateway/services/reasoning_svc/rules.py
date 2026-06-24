"""SC-001 deterministic rule weights — freight invoice overcharge.

This formula is deterministic and must never change once shipped.
"""

RULES = {
    "fuel_charge":  {"confidence": 1.00, "weight": 0.50},
    "accessorial":  {"confidence": 0.92, "weight": 0.50},
}

SC001_CONFIDENCE = round(
    sum(r["confidence"] * r["weight"] for r in RULES.values()), 4
)  # = 0.96
