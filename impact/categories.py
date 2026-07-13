"""Scorecard-factor taxonomy: factor -> assumption category and default
decision-importance. Both are transparent, documented tables — decision
importance is a default that a per-opportunity metadata sidecar may override;
it is not claimed to be objective.
"""

# 17 scorecard factors -> 11 assumption categories.
# 'regulatory' has no scorecard factor; it is reachable only via manual/risk
# entries in the metadata sidecar (documented, not silently produced).
FACTOR_CATEGORY = {
    "pain_severity": "pain",
    "pain_frequency": "pain",
    "financial_impact": "pain",
    "workaround_cost": "behaviour",
    "switching_intent": "switching",
    "willingness_to_pay": "willingness_to_pay",
    "digital_readiness": "customer",
    "payment_volume": "commercial",
    "credit_need": "credit",
    "botim_distribution_advantage": "product",
    "transaction_data_advantage": "product",
    "payment_revenue_potential": "commercial",
    "lending_revenue_potential": "commercial",
    "credit_risk_visibility": "credit",
    "competitive_defensibility": "product",
    "ease_of_validation": "operational",
    "mvp_feasibility_7wk": "technical",
}

CATEGORIES = ("customer", "pain", "behaviour", "switching", "willingness_to_pay",
              "product", "commercial", "credit", "regulatory", "operational", "technical")

# Default decision importance per factor (override per-opportunity via sidecar).
_DEFAULT_IMPORTANCE = {
    "critical": ("pain_severity", "switching_intent", "willingness_to_pay",
                 "credit_need", "credit_risk_visibility", "competitive_defensibility"),
    "high": ("financial_impact", "lending_revenue_potential",
             "botim_distribution_advantage", "payment_volume"),
    "medium": ("pain_frequency", "workaround_cost", "transaction_data_advantage",
               "payment_revenue_potential", "digital_readiness"),
    "low": ("ease_of_validation", "mvp_feasibility_7wk"),
}
FACTOR_IMPORTANCE = {f: band for band, fs in _DEFAULT_IMPORTANCE.items() for f in fs}

IMPORTANCE_BANDS = ("critical", "high", "medium", "low")


def category_for(factor):
    return FACTOR_CATEGORY.get(factor, "operational")


def default_importance(factor):
    return FACTOR_IMPORTANCE.get(factor, "medium")
