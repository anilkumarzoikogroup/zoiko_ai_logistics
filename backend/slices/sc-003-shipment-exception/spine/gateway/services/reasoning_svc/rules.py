"""SC-003 deterministic rule weights — shipment exception / SLA penalty.

Two rules drive the confidence score for every SLA breach case.

delivery_window_breach (weight 0.60)
    Fully deterministic: committed_eta and actual_delivery are timestamped
    facts.  If actual_delivery > committed_eta the breach occurred; there is
    no ambiguity, so confidence is 1.00.  This rule carries the majority of
    the weight because it is the objective trigger for the entire claim.

sla_clause_applicable (weight 0.40)
    AI judgment: does the contract's SLA penalty clause actually cover this
    shipment and this type of delay?  Some contracts exclude force-majeure
    events, specific routes, or delay categories.  Confidence 0.88 reflects
    that most clauses are unambiguous but a small fraction require human
    review (e.g. disputed force-majeure declarations).

SC003_CONFIDENCE is computed — never hardcoded — so any future calibration
of an individual rule automatically propagates to the case-level score.
"""

RULES = {
    "delivery_window_breach": {"confidence": 1.00, "weight": 0.60},  # deterministic: late or not
    "sla_clause_applicable":  {"confidence": 0.88, "weight": 0.40},  # AI: does clause apply?
}

SC003_CONFIDENCE = round(
    sum(r["confidence"] * r["weight"] for r in RULES.values()), 4
)  # = 0.9520
