"""
SC-004 Reasoning Rules — deterministic confidence formula.

NEVER change SC004_CONFIDENCE — it is a locked platform constant.
"""

SC004_CONFIDENCE = 0.9640  # = 1.00×0.70 + 0.88×0.30

_RULES = {
    "breach_detected_rule": {"confidence": 1.00, "weight": 0.70},
    "data_coverage_rule":   {"confidence": 0.88, "weight": 0.30},
}


def compute_rule_traces(composite_score: float, threshold: float, total_claims: int, sla_cases: int) -> list[dict]:
    return [
        {
            "rule":       "breach_detected_rule",
            "confidence": _RULES["breach_detected_rule"]["confidence"],
            "weight":     _RULES["breach_detected_rule"]["weight"],
            "passed":     composite_score < threshold,
            "detail":     f"composite {composite_score} < threshold {threshold}",
        },
        {
            "rule":       "data_coverage_rule",
            "confidence": _RULES["data_coverage_rule"]["confidence"],
            "weight":     _RULES["data_coverage_rule"]["weight"],
            "passed":     total_claims > 0 or sla_cases > 0,
            "detail":     f"total_claims={total_claims} sla_cases={sla_cases}",
        },
    ]
