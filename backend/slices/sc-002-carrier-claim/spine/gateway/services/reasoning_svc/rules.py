"""SC-002 rule weights and data-driven confidence evaluators — carrier claim.

Rule weights are fixed. Per-rule confidence is computed dynamically from actual
claim attributes fetched during reasoning, so the final weighted confidence
reflects the real strength of each claim rather than a static proxy value.

Baseline (all checks pass fully):
  liability_acknowledged   (0.95 × 0.55) +
  amount_within_policy_cap (0.90 × 0.45) = 0.9275
"""

# Rule weights are deterministic — never change without a schema migration.
RULES = {
    "liability_acknowledged":   {"base_confidence": 0.95, "weight": 0.55},
    "amount_within_policy_cap": {"base_confidence": 0.90, "weight": 0.45},
}

# Baseline confidence (all rules pass at their base level).
SC002_CONFIDENCE = round(
    sum(r["base_confidence"] * r["weight"] for r in RULES.values()), 4
)  # = 0.9275


# ── Claim-age thresholds (days since filed_at) ────────────────────────────────
_AGE_FRESH_DAYS    = 30   # 0–30 days: fresh, full confidence
_AGE_AGING_DAYS    = 90   # 31–90 days: aging, moderate reduction
# > 90 days: stale, meaningful reduction


def evaluate_rule_confidence(rule_name: str, claim_attrs: dict, amount: float) -> float:
    """Return actual per-rule confidence based on claim_attrs (from read_claim_attributes tool).

    Falls back to the rule's base_confidence when data is unavailable, preserving
    determinism for cases where the DB query returned no rows.
    """
    base = RULES[rule_name]["base_confidence"]

    if rule_name == "liability_acknowledged":
        # Proxy: claim age. Fresh claims have strong recency — carrier cannot easily deny
        # receipt. Stale claims may have paperwork gaps that reduce liability certainty.
        days = claim_attrs.get("days_since_filed")
        if days is None:
            return base  # no date info — use base
        if days <= _AGE_FRESH_DAYS:
            return 0.97  # within window, very strong
        if days <= _AGE_AGING_DAYS:
            return 0.92  # carrier may raise timeliness objection
        return 0.78      # stale — significant risk of denial on procedural grounds

    if rule_name == "amount_within_policy_cap":
        # Check claimed amount against max active contract rate (policy cap proxy).
        max_rate = claim_attrs.get("max_rate")
        if not max_rate or max_rate <= 0:
            return base  # no rate on file — cannot validate, use base
        ratio = amount / max_rate
        if ratio <= 1.0:
            return 0.97  # within policy cap — strong claim
        if ratio <= 1.15:
            return 0.85  # slightly over cap — needs justification
        if ratio <= 1.50:
            return 0.70  # materially over cap — partial recovery likely
        return 0.50      # well over cap — high risk of rejection

    return base  # unknown rule — safe fallback


def compute_confidence(claim_attrs: dict, amount: float) -> tuple[dict, float]:
    """Evaluate all rules against actual claim data and return (rule_trace, weighted_confidence)."""
    rule_trace = {}
    weighted_sum = 0.0
    for rule_name, rule in RULES.items():
        conf = evaluate_rule_confidence(rule_name, claim_attrs, amount)
        rule_trace[rule_name] = {
            "confidence": conf,
            "base_confidence": rule["base_confidence"],
            "weight": rule["weight"],
        }
        weighted_sum += conf * rule["weight"]
    confidence = round(weighted_sum, 4)
    rule_trace["weighted_average"] = confidence
    return rule_trace, confidence
