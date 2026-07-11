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
    "payment_take_bps",              # net take on routed flow (wallet fee OR net interchange —
                                     # never gross MDR); must be 0 when the online/offline
                                     # blend inputs are used instead
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

# Optional inputs (card/acquiring products). Absent => defaults; fully
# backwards-compatible with wallet-product models that omit them.
OPTIONAL_INPUTS = (
    "acquiring_revenue_monthly",     # net acquiring margin if BOTIM also acquires (default 0)
    "offline_share",                 # fraction of routed flow that is in-person (blend trio)
    "payment_take_bps_offline",      # net take on offline flow (blend trio)
    "payment_take_bps_online",       # net take on online flow (blend trio)
    "avg_credit_duration_days",      # avg days a drawn dirham stays out; reporting/derived only —
                                     # the balance model already embeds duration in utilisation
)

_BLEND_TRIO = ("offline_share", "payment_take_bps_offline", "payment_take_bps_online")


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
    acquiring_revenue: float = 0.0
    total_revenue: float = 0.0
    effective_payment_take_bps: float = 0.0
    # duration-derived (None unless avg_credit_duration_days provided)
    monthly_originations: float = None
    credit_turns_per_year: float = None
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
    warnings: list = field(default_factory=list)   # plausibility warnings (audit S-2)

    def v(self, name):
        return self.inputs[name][0]


def compute_case(case_name, raw_inputs):
    missing = [k for k in REQUIRED_INPUTS if k not in raw_inputs]
    if missing:
        raise InputError(f"case '{case_name}': missing inputs: {', '.join(missing)}")
    unknown = [k for k in raw_inputs if k not in REQUIRED_INPUTS + OPTIONAL_INPUTS]
    if unknown:
        raise InputError(f"case '{case_name}': unknown inputs: {', '.join(unknown)}")

    inputs = {k: _norm(raw_inputs[k], k) for k in REQUIRED_INPUTS}
    for k in OPTIONAL_INPUTS:
        if k in raw_inputs:
            inputs[k] = _norm(raw_inputs[k], k)
    r = CaseResult(case=case_name, inputs=inputs)
    r.assumption_labels = {k: lab for k, (_, lab, _) in inputs.items()}

    # plausibility validation (audit S-1/S-2): a one-character typo must not
    # flip economics silently through model -> MC -> stress -> recommendation
    for name, (value, _, _) in inputs.items():
        if value < 0:
            raise InputError(
                f"case '{case_name}': {name} is negative ({value}) — no input in this "
                "model is legitimately negative; fix the typo"
            )
    for name, ceiling, what in (
        ("financing_rate_annual", 1.0, "a >100% annual financing rate"),
        ("funding_rate_annual", 1.0, "a >100% annual funding rate"),
        ("ecl_rate_annual", 0.5, "a >50% annualised expected credit loss"),
    ):
        if r.v(name) > ceiling:
            r.warnings.append(
                f"{name} = {r.v(name)} implies {what} — accepted, but verify this is intended"
            )

    for frac in ("routed_share", "utilisation"):
        if not 0 <= r.v(frac) <= 1:
            raise InputError(f"case '{case_name}': {frac} must be a fraction 0..1, got {r.v(frac)}")

    # online/offline blend: all-or-nothing trio, replaces the flat take
    blend_given = [k for k in _BLEND_TRIO if k in inputs]
    if blend_given:
        if len(blend_given) != len(_BLEND_TRIO):
            raise InputError(
                f"case '{case_name}': blend inputs are all-or-nothing; missing "
                f"{', '.join(k for k in _BLEND_TRIO if k not in inputs)}"
            )
        if not 0 <= r.v("offline_share") <= 1:
            raise InputError(f"case '{case_name}': offline_share must be a fraction 0..1")
        if r.v("payment_take_bps") != 0:
            raise InputError(
                f"case '{case_name}': set payment_take_bps to 0 when using the "
                "online/offline blend — providing both double-counts payment revenue"
            )
        off = r.v("offline_share")
        r.effective_payment_take_bps = (
            off * r.v("payment_take_bps_offline") + (1 - off) * r.v("payment_take_bps_online")
        )
    else:
        r.effective_payment_take_bps = r.v("payment_take_bps")

    # volumes
    r.routed_flow = r.v("monthly_revenue_per_merchant") * r.v("routed_share")
    r.credit_limit = r.routed_flow * r.v("limit_multiple_of_routed_flow")
    r.drawn_balance = r.credit_limit * r.v("utilisation")

    # duration-derived reporting (balance model already embeds duration in utilisation)
    if "avg_credit_duration_days" in inputs:
        duration = r.v("avg_credit_duration_days")
        if duration <= 0:
            raise InputError(f"case '{case_name}': avg_credit_duration_days must be > 0")
        r.monthly_originations = r.drawn_balance * 30 / duration
        r.credit_turns_per_year = 365 / duration

    # revenue (per merchant / month)
    r.financing_revenue = r.drawn_balance * r.v("financing_rate_annual") / 12
    r.payment_revenue = r.routed_flow * r.effective_payment_take_bps / 10_000
    r.acquiring_revenue = r.v("acquiring_revenue_monthly") if "acquiring_revenue_monthly" in inputs else 0.0
    r.total_revenue = (
        r.financing_revenue
        + r.payment_revenue
        + r.acquiring_revenue
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
    results = {c: compute_case(c, model["cases"][c]) for c in CASES}
    # inverted-cases sanity (audit S-4): downside outperforming upside is
    # almost always a data-entry error
    if results["downside"].contribution > results["upside"].contribution:
        results["upside"].warnings.append(
            "downside contribution exceeds upside — case columns are probably inverted"
        )
    return results


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
        row("Payment revenue (net take/interchange, never gross MDR)", lambda r: r.payment_revenue),
        row("Effective payment take (bps)", lambda r: r.effective_payment_take_bps, "{:.1f}"),
        row("Acquiring revenue", lambda r: r.acquiring_revenue),
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
        row("Days of drawn-balance funding covered by payment margin (gross)", lambda r: r.max_free_days_gross, "{:.1f}"),
        row("… net of fraud+processing (NOT comparable to subsidy-model grace days)", lambda r: r.max_free_days_net, "{:.1f}"),
        row("Max cashback (% of routed flow)", lambda r: r.max_cashback_pct, "{:.2f}%"),
        row("Max fee subsidy (from contribution)", lambda r: r.max_fee_subsidy),
    ]
    if b.monthly_originations is not None:
        lines += [
            row("Monthly originations (duration-derived)", lambda r: r.monthly_originations or 0),
            row("Credit turns per year", lambda r: r.credit_turns_per_year or 0, "{:.1f}"),
        ]
    all_warnings = [w for r in (d, b, u) for w in r.warnings]
    if all_warnings:
        lines += ["", "## ⚠ Plausibility warnings", ""]
        lines += [f"- {w}" for w in sorted(set(all_warnings))]
    lines += [
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
