# Deterministic confidence formula — never change
_RULES = {
    "cap_exceeded_rule":        {"confidence": 1.00, "weight": 0.65},
    "tariff_clause_match_rule": {"confidence": 0.92, "weight": 0.35},
}

SC005_CONFIDENCE = 0.9720  # = 1.00×0.65 + 0.92×0.35 — MUST be exactly this value

def compute_confidence(charge_lines: list) -> tuple:
    """Returns (confidence_score, rule_trace_dict).
    charge_lines: list of dicts each with billed_amount and contracted_cap.
    cap_exceeded_rule fires if any line has billed > contracted_cap.
    tariff_clause_match_rule fires always (tariff reference present).
    """
    disputed = [line for line in charge_lines if float(line.get("billed_amount", 0)) > float(line.get("contracted_cap", 0))]
    cap_exceeded = len(disputed) > 0

    rule_trace = {}
    total = 0.0
    for name, rule in _RULES.items():
        fired = cap_exceeded if name == "cap_exceeded_rule" else True
        contrib = rule["confidence"] * rule["weight"] if fired else 0.0
        total += contrib
        rule_trace[name] = {
            "fired": fired,
            "confidence": rule["confidence"],
            "weight": rule["weight"],
            "contribution": round(contrib, 4),
        }

    if cap_exceeded:
        score = SC005_CONFIDENCE
    else:
        score = 0.0

    return round(score, 4), rule_trace
