"""Three-case commercial model engine.

Implements opportunity-intelligence/templates/commercial-model.md for
wallet/lending propositions: per-merchant unit economics for downside/base/
upside cases, portfolio contribution, break-even, and maximum affordable
subsidies funded by payment margin.

Input JSON schema (see knowledge-base/commercial-models/*-inputs.json):

{
  "opportunity_id": "OPP-001",
  "name": "...",
  "currency": "AED",
  "cases": {
    "downside": {"<input>": <number> | {"value": <number>, "label": "F|E|A", "note": "..."}, ...},
    "base": {...},
    "upside": {...}
  }
}

Every input may carry an F/E/A label; unlabelled inputs default to "A"
(assumption) — the module's discipline is that nothing is a fact until marked.
"""

from dataclasses import dataclass, field

CASES = ("downside", "base", "upside")

REQUIRED_INPUTS = (
    "active_merchants",
    "monthly_revenue_per_merchant",
    "routed_share",                  # fraction of revenue received via BOTIM
    "limit_multiple_of_routed_flow", # credit limit as multiple of monthly routed flow
    "utilisation",                   # fraction of limit drawn on average
    "financing_rate_annual",
    "payment_take_bps",              # net wallet P2M take on routed flow (NOT card interchange)
    "subscription_revenue_monthly",
    "other_revenue_monthly",         # transfers / FX / supplier commissions
    "funding_rate_annual",
    "ecl_rate_annual",
    "fraud_loss_monthly",
    "processing_cost_monthly",
    "scheme_fees_monthly",
    "rewards_monthly",
    "servicing_cost_monthly",
    "cac_amortised_monthly",
    "fixed_costs_monthly",           # programme-level, not per merchant
)


class InputError(ValueError):
    pass


def _norm(raw, name):
    """Normalise a raw input to (value, label, note)."""
    if isinstance(raw, dict):
        try:
            value = float(raw["value"])
        except (KeyError, TypeError, ValueError):
            raise InputError(f"input '{name}': dict form needs a numeric 'value'")
        label = str(raw.get("label", "A")).upper()
        if label not in ("F", "E", "A"):
            raise InputError(f"input '{name}': label must be F, E or A, got {label!r}")
        return value, label, str(raw.get("note", ""))
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw), "A", ""
    raise InputError(f"input '{name}': expected number or {{value,label,note}}, got {type(raw).__name__}")


@dataclass
class CaseResult:
    case: str
    inputs: dict                 # name -> (value, label, note)
    # derived volumes
    routed_flow: float = 0.0
    credit_limit: float = 0.0
    drawn_balance: float = 0.0
    # per-merchant monthly revenue
    financing_revenue: float = 0.0
    payment_revenue: float = 0.0
    total_revenue: float = 0.0
    # per-merchant monthly cost
    cost_of_capital: float = 0.0
    expected_credit_loss: float = 0.0
    total_cost: float = 0.0
    # outputs
    contribution: float = 0.0
    contribution_pct: float = 0.0
    portfolio_contribution: float = 0.0
    breakeven_merchants: float = None      # None => never at these unit economics
    max_free_days_gross: float = 0.0       # payment margin only, before fraud/processing
    max_free_days_net: float = 0.0         # after fraud + processing netted from budget
    max_cashback_pct: float = 0.0          # of routed flow, net budget fully allocated
    max_fee_subsidy: float = 0.0           # AED/merchant/month, from total contribution
    assumption_labels: dict = field(default_factory=dict)

    def v(self, name):
        return self.inputs[name][0]


def compute_case(case_name, raw_inputs):
    missing = [k for k in REQUIRED_INPUTS if k not in raw_inputs]
    if missing:
        raise InputError(f"case '{case_name}': missing inputs: {', '.join(missing)}")
    unknown = [k for k in raw_inputs if k not in REQUIRED_INPUTS]
    if unknown:
        raise InputError(f"case '{case_name}': unknown inputs: {', '.join(unknown)}")

    inputs = {k: _norm(raw_inputs[k], k) for k in REQUIRED_INPUTS}
    r = CaseResult(case=case_name, inputs=inputs)
    r.assumption_labels = {k: lab for k, (_, lab, _) in inputs.items()}

    for frac in ("routed_share", "utilisation"):
        if not 0 <= r.v(frac) <= 1:
            raise InputError(f"case '{case_name}': {frac} must be a fraction 0..1, got {r.v(frac)}")

    # volumes
    r.routed_flow = r.v("monthly_revenue_per_merchant") * r.v("routed_share")
    r.credit_limit = r.routed_flow * r.v("limit_multiple_of_routed_flow")
    r.drawn_balance = r.credit_limit * r.v("utilisation")

    # revenue (per merchant / month)
    r.financing_revenue = r.drawn_balance * r.v("financing_rate_annual") / 12
    r.payment_revenue = r.routed_flow * r.v("payment_take_bps") / 10_000
    r.total_revenue = (
        r.financing_revenue
        + r.payment_revenue
        + r.v("subscription_revenue_monthly")
        + r.v("other_revenue_monthly")
    )

    # cost (per merchant / month)
    r.cost_of_capital = r.drawn_balance * r.v("funding_rate_annual") / 12
    r.expected_credit_loss = r.drawn_balance * r.v("ecl_rate_annual") / 12
    r.total_cost = (
        r.cost_of_capital
        + r.expected_credit_loss
        + r.v("fraud_loss_monthly")
        + r.v("processing_cost_monthly")
        + r.v("scheme_fees_monthly")
        + r.v("rewards_monthly")
        + r.v("servicing_cost_monthly")
        + r.v("cac_amortised_monthly")
    )

    # outputs
    r.contribution = r.total_revenue - r.total_cost
    r.contribution_pct = (r.contribution / r.total_revenue * 100) if r.total_revenue else 0.0
    r.portfolio_contribution = r.contribution * r.v("active_merchants")
    fixed = r.v("fixed_costs_monthly")
    r.breakeven_merchants = (fixed / r.contribution) if r.contribution > 0 else None

    # subsidy ceilings funded by PAYMENT margin (lending margin is priced, not a subsidy pool)
    day_cost = r.drawn_balance * r.v("funding_rate_annual") / 365
    net_budget = r.payment_revenue - r.v("fraud_loss_monthly") - r.v("processing_cost_monthly")
    if day_cost > 0:
        r.max_free_days_gross = max(0.0, r.payment_revenue / day_cost)
        r.max_free_days_net = max(0.0, net_budget / day_cost)
    r.max_cashback_pct = max(0.0, net_budget / r.routed_flow * 100) if r.routed_flow else 0.0
    r.max_fee_subsidy = max(0.0, r.contribution)
    return r


def compute_model(model):
    """model: parsed JSON dict. Returns {case_name: CaseResult}."""
    for key in ("opportunity_id", "name", "cases"):
        if key not in model:
            raise InputError(f"model is missing top-level key '{key}'")
    missing = [c for c in CASES if c not in model["cases"]]
    if missing:
        raise InputError(f"model is missing cases: {', '.join(missing)} (downside/base/upside are all mandatory)")
    return {c: compute_case(c, model["cases"][c]) for c in CASES}


def render_markdown(model, results):
    """Render results as a markdown report string."""
    cur = model.get("currency", "AED")
    d, b, u = (results[c] for c in CASES)

    def row(label, fn, fmt="{:,.0f}"):
        return "| {} | {} | {} | {} |".format(label, *(fmt.format(fn(x)) for x in (d, b, u)))

    lines = [
        f"# Computed commercial model — {model['opportunity_id']} {model['name']}",
        "",
        f"All figures {cur}, per merchant per month unless noted. Generated by opportunity_engine; "
        "inputs and F/E/A labels in the companion *-inputs.json.",
        "",
        "| Line | Downside | Base | Upside |",
        "|---|---|---|---|",
        row("Routed flow", lambda r: r.routed_flow),
        row("Credit limit", lambda r: r.credit_limit),
        row("Average drawn balance", lambda r: r.drawn_balance),
        row("Financing revenue", lambda r: r.financing_revenue),
        row("Payment revenue (wallet take, not interchange)", lambda r: r.payment_revenue),
        row("Total revenue", lambda r: r.total_revenue),
        row("Cost of capital", lambda r: r.cost_of_capital),
        row("Expected credit loss", lambda r: r.expected_credit_loss),
        row("Total cost", lambda r: r.total_cost),
        row("**Contribution / merchant / month**", lambda r: r.contribution),
        row("Contribution margin %", lambda r: r.contribution_pct, "{:.1f}%"),
        row("Portfolio contribution (all merchants)", lambda r: r.portfolio_contribution),
        "| Break-even merchants | {} | {} | {} |".format(
            *("never" if r.breakeven_merchants is None else f"{r.breakeven_merchants:,.0f}" for r in (d, b, u))
        ),
        row("Max free-credit days (payment margin, gross)", lambda r: r.max_free_days_gross, "{:.1f}"),
        row("Max free-credit days (net of fraud+processing)", lambda r: r.max_free_days_net, "{:.1f}"),
        row("Max cashback (% of routed flow)", lambda r: r.max_cashback_pct, "{:.2f}%"),
        row("Max fee subsidy (from contribution)", lambda r: r.max_fee_subsidy),
        "",
        "## Assumption labels",
        "",
        "Inputs labelled A (assumption) in the base case: "
        + (", ".join(sorted(k for k, lab in b.assumption_labels.items() if lab == "A")) or "none"),
        "",
        "F/E-labelled inputs: "
        + (", ".join(sorted(f"{k}({lab})" for k, lab in b.assumption_labels.items() if lab != "A")) or "none — model is fully assumption-based"),
    ]
    return "\n".join(lines) + "\n"
