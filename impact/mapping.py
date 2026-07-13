"""Declarative evidence-to-factor mapping and safety gates.

This is the ONLY place an evidence field is linked to an opportunity factor.
Each evidence field maps to exactly one factor; the generator refuses to let a
single evidence fact fan out across several unrelated factors (capability 2).
"""

from .errors import ImpactError

# evidence_field  ->  opportunity scorecard factor (1:1, no fan-out)
FIELD_TO_FACTOR = {
    "willingness_to_pay_signal": "willingness_to_pay",
    "switching_signal": "switching_intent",
    "pain_severity_evidence": "pain_severity",
    "pain_frequency_evidence": "pain_frequency",
    "financial_impact_evidence": "financial_impact",
    "workaround_cost_evidence": "workaround_cost",
    "credit_need_confirmation": "credit_need",
    "payment_volume_evidence": "payment_volume",
    "transaction_data_evidence": "transaction_data_advantage",
    "distribution_evidence": "botim_distribution_advantage",
}

# Safety gates -------------------------------------------------------------
# Evidence strength below this stays a lead and cannot drive any score change.
MIN_STRENGTH = 3

# Only behavioural evidence classes may move a demand/score factor. Complaint
# and stated-interest are leads; vendor/funding claims are never demand.
BEHAVIOURAL_CLASSES = {
    "observed behaviour",
    "workaround spending",
    "switching intent",
    "actual switching",
}
NON_DEMAND_CLASSES = {"complaint", "stated interest"}

CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


def resolve_factor(evidence_field):
    """Return the single factor for an evidence field, or raise on unknown."""
    if evidence_field not in FIELD_TO_FACTOR:
        raise ImpactError(
            f"unmapped evidence_field '{evidence_field}': add it to mapping.FIELD_TO_FACTOR "
            "before it can affect any factor (no silent/implicit mapping)"
        )
    return FIELD_TO_FACTOR[evidence_field]


def assert_no_fanout(evidence_fields):
    """A single evidence fact must not target several factors via duplicate rows."""
    seen = {}
    for field in evidence_fields:
        factor = resolve_factor(field)
        if factor in seen and seen[factor] != field:
            raise ImpactError(
                f"fan-out refused: factor '{factor}' targeted by both "
                f"'{seen[factor]}' and '{field}' in one proposal"
            )
        seen[factor] = field


def gate_reason(evidence_confidence, evidence_strength, evidence_class):
    """Return None if evidence may drive a change, else a human-readable reason
    why it must remain a lead."""
    if evidence_strength is None or evidence_strength < MIN_STRENGTH:
        return (f"evidence strength {evidence_strength} below minimum {MIN_STRENGTH} "
                "(remains a lead, not a finding)")
    cls = (evidence_class or "").strip().lower()
    if cls in NON_DEMAND_CLASSES:
        return f"evidence class '{evidence_class}' is not behavioural (complaint/stated interest are leads)"
    if cls not in BEHAVIOURAL_CLASSES:
        return f"evidence class '{evidence_class}' is not a recognised behavioural class"
    conf = (evidence_confidence or "").strip().lower()
    if conf not in CONFIDENCE_ORDER:
        return f"evidence confidence '{evidence_confidence}' not one of high/medium/low"
    if CONFIDENCE_ORDER[conf] < CONFIDENCE_ORDER["medium"]:
        return "evidence confidence 'low' cannot drive a score or assumption change"
    return None


def assumption_status_for(evidence_confidence, contradicts=False):
    """Map confidence to the assumption-register status an approved change yields.
    Medium confidence is never treated as full validation ('supported')."""
    if contradicts:
        return "contradicted"
    conf = (evidence_confidence or "").strip().lower()
    if conf == "high":
        return "supported"
    return "partially supported"  # medium (low is gated out upstream)
