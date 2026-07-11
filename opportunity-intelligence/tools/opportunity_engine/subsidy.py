"""MDR/interchange subsidy model for CARD propositions.

Implements opportunity-intelligence/templates/mdr-interchange-subsidy-model.md.
Terminology enforced by construction: the model starts from gross ISSUER
interchange (or agreed programme share) in bps — there is no MDR input, so the
"BOTIM gets full MDR" error cannot be expressed.

Input JSON schema (see knowledge-base/commercial-models/*-subsidy-inputs.json):

{
  "opportunity_id": "OPP-002",
  "name": "...",
  "cases": {
    "downside": {
      "gross_interchange_bps": ...,      # commercial-card interchange / programme share
      "programme_split_bps": ...,        # BIN sponsor / issuer-processor / programme manager
      "scheme_fee_bps": ...,
      "processing_bps": ...,
      "fraud_bps": ...,
      "monthly_card_spend": ...,         # routed spend per merchant, AED
      "funding_rate_annual": ...,
      "offered_free_days": ...,          # the package being tested
      "offered_cashback_pct": ...,       # % of spend
      "offered_fee_subsidy": ...,        # AED/month
      "lending_contribution": ...        # AED/month top-up, ONLY if lending model is positive after risk
    }, "base": {...}, "upside": {...}
  }
}

Inputs accept the same number-or-{value,label,note} form as commercial.py.
"""

from dataclasses import dataclass, field

from .commercial import CASES, InputError, _norm

REQUIRED_INPUTS = (
    "gross_interchange_bps",
    "programme_split_bps",
    "scheme_fee_bps",
    "processing_bps",
    "fraud_bps",
    "monthly_card_spend",
    "funding_rate_annual",
    "offered_free_days",
    "offered_cashback_pct",
    "offered_fee_subsidy",
    "lending_contribution",
)

# Optional credit-cost inputs (audit C-3): expected credit loss and servicing
# expressed in bps of monthly card spend. Default 0 — but then every report
# carries an explicit PRE-CREDIT-COST caption, because for a free-credit-days
# product, affordability without ECL is structurally overstated.
OPTIONAL_INPUTS = ("ecl_bps", "servicing_bps")


@dataclass
class SubsidyResult:
    case: str
    inputs: dict
    net_margin_bps: float = 0.0
    monthly_budget: float = 0.0        # M: payment-economics budget per merchant/month
    total_budget: float = 0.0          # M + lending contribution
    cost_free_days: float = 0.0
    cost_cashback: float = 0.0
    cost_fee_subsidy: float = 0.0
    total_subsidy_cost: float = 0.0
    residual: float = 0.0              # total_budget - total_subsidy_cost
    package_affordable: bool = False
    max_free_days_alone: float = 0.0   # if M were spent only on free days
    max_cashback_alone_pct: float = 0.0
    ecl_bps: float = 0.0
    servicing_bps: float = 0.0
    pre_credit_cost: bool = True       # True when ECL/servicing not modelled (audit C-3)
    assumption_labels: dict = field(default_factory=dict)

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
    r = SubsidyResult(case=case_name, inputs=inputs)
    r.assumption_labels = {k: lab for k, (_, lab, _) in inputs.items()}

    for name, (value, _, _) in inputs.items():
        if value < 0:
            raise InputError(f"case '{case_name}': {name} is negative ({value}) — fix the typo")

    r.ecl_bps = r.v("ecl_bps") if "ecl_bps" in inputs else 0.0
    r.servicing_bps = r.v("servicing_bps") if "servicing_bps" in inputs else 0.0
    r.pre_credit_cost = ("ecl_bps" not in inputs and "servicing_bps" not in inputs)
    r.net_margin_bps = (
        r.v("gross_interchange_bps")
        - r.v("programme_split_bps")
        - r.v("scheme_fee_bps")
        - r.v("processing_bps")
        - r.v("fraud_bps")
        - r.ecl_bps
        - r.servicing_bps
    )
    spend = r.v("monthly_card_spend")
    r.monthly_budget = spend * r.net_margin_bps / 10_000
    r.total_budget = r.monthly_budget + r.v("lending_contribution")

    # cost of the offered package — all drawing on ONE budget (stacking rule)
    day_cost = spend * r.v("funding_rate_annual") / 365
    r.cost_free_days = r.v("offered_free_days") * day_cost
    r.cost_cashback = spend * r.v("offered_cashback_pct") / 100
    r.cost_fee_subsidy = r.v("offered_fee_subsidy")
    r.total_subsidy_cost = r.cost_free_days + r.cost_cashback + r.cost_fee_subsidy
    r.residual = r.total_budget - r.total_subsidy_cost
    r.package_affordable = r.residual >= 0

    # single-use ceilings (payment budget only, whole budget on one lever)
    if day_cost > 0:
        r.max_free_days_alone = max(0.0, r.monthly_budget / day_cost)
    r.max_cashback_alone_pct = max(0.0, r.monthly_budget / spend * 100) if spend else 0.0
    return r


def compute_model(model):
    for key in ("opportunity_id", "name", "cases"):
        if key not in model:
            raise InputError(f"model is missing top-level key '{key}'")
    missing = [c for c in CASES if c not in model["cases"]]
    if missing:
        raise InputError(f"model is missing cases: {', '.join(missing)}")
    return {c: compute_case(c, model["cases"][c]) for c in CASES}


def render_markdown(model, results):
    d, b, u = (results[c] for c in CASES)

    def row(label, fn, fmt="{:,.1f}"):
        return "| {} | {} | {} | {} |".format(label, *(fmt.format(fn(x)) for x in (d, b, u)))

    pre_credit = any(r.pre_credit_cost for r in (d, b, u))
    lines = [
        f"# Computed subsidy model — {model['opportunity_id']} {model['name']}",
        "",
        "Issuer-interchange/programme-share based; the accepting merchant's MDR is not BOTIM revenue "
        "and is not an input to this model.",
    ]
    if pre_credit:
        lines += [
            "",
            "**⚠ PRE-CREDIT-COST FIGURES:** expected credit loss and servicing are not modelled "
            "(ecl_bps/servicing_bps inputs omitted). For a free-credit-days product this "
            "structurally overstates affordability — treat every 'affordable' verdict below as "
            "an upper bound until credit costs are added.",
        ]
    lines += [
        "",
        "| Line | Downside | Base | Upside |",
        "|---|---|---|---|",
        row("Net payment margin (bps)", lambda r: r.net_margin_bps),
        row("Monthly budget M (AED/merchant)", lambda r: r.monthly_budget),
        row("Lending contribution top-up", lambda r: r.v("lending_contribution")),
        row("Total budget", lambda r: r.total_budget),
        row("Cost: offered free-credit days", lambda r: r.cost_free_days),
        row("Cost: offered cashback", lambda r: r.cost_cashback),
        row("Cost: offered fee subsidy", lambda r: r.cost_fee_subsidy),
        row("Total package cost (stacked on one budget)", lambda r: r.total_subsidy_cost),
        row("**Residual**", lambda r: r.residual),
        "| Package affordable? | {} | {} | {} |".format(
            *("YES" if r.package_affordable else "NO — loss-leader, needs stated payback" for r in (d, b, u))
        ),
        row("Ceiling: GRACE DAYS on monthly card spend if M funds free days only "
            "(not comparable to the commercial model's drawn-balance days)", lambda r: r.max_free_days_alone),
        row("Ceiling: max cashback % if M spent on cashback only", lambda r: r.max_cashback_alone_pct, "{:.2f}"),
        "",
        "Assumption-labelled inputs (base): "
        + (", ".join(sorted(k for k, lab in b.assumption_labels.items() if lab == "A")) or "none"),
    ]
    return "\n".join(lines) + "\n"
