"""Time-phased break-even model (audit D-1).

The static model answers "how many merchants to break even"; a lender's board
asks "how many months of losses and how much capital before break-even". This
module answers that with a deliberately simple, fully-stated ramp:

    merchants(m) = active_merchants × min(1, m / ramp_months)      (linear ramp)
    net(m)       = merchants(m) × contribution − fixed_costs_monthly
    cumulative(m)= Σ net(1..m)

Outputs per case: first month with positive monthly net, first month with
positive cumulative cash, peak funding need (deepest cumulative hole) and its
month, and end-of-horizon cumulative position. Steady-state per-merchant
contribution comes from commercial.compute_case — cohort maturation, churn,
and seasonality are structurally absent and said so in every report.
"""

from dataclasses import dataclass, field

from . import commercial
from .commercial import CASES, InputError


@dataclass
class RampResult:
    case: str
    months: int
    ramp_months: int
    monthly_breakeven_month: int    # None => not within horizon
    cumulative_breakeven_month: int
    peak_funding_need: float        # max cumulative shortfall (>= 0)
    peak_month: int
    end_cumulative: float
    series: list = field(default_factory=list)  # (month, merchants, net, cumulative)


def analyse_case(case_result, months=36, ramp_months=12):
    if months < 1 or ramp_months < 1:
        raise InputError("months and ramp_months must be >= 1")
    active = case_result.v("active_merchants")
    fixed = case_result.v("fixed_costs_monthly")
    contribution = case_result.contribution

    series = []
    cumulative = 0.0
    monthly_be = cumulative_be = None
    peak = 0.0
    peak_month = 0
    for m in range(1, months + 1):
        merchants = active * min(1.0, m / ramp_months)
        net = merchants * contribution - fixed
        cumulative += net
        if monthly_be is None and net >= 0:
            monthly_be = m
        if cumulative_be is None and cumulative >= 0:
            cumulative_be = m
        if -cumulative > peak:
            peak = -cumulative
            peak_month = m
        series.append((m, merchants, net, cumulative))

    return RampResult(
        case=case_result.case, months=months, ramp_months=ramp_months,
        monthly_breakeven_month=monthly_be, cumulative_breakeven_month=cumulative_be,
        peak_funding_need=peak, peak_month=peak_month,
        end_cumulative=cumulative, series=series,
    )


def analyse(model, months=36, ramp_months=12):
    results = commercial.compute_model(model)
    return {c: analyse_case(results[c], months, ramp_months) for c in CASES}


def render_markdown(model, ramps):
    d, b, u = (ramps[c] for c in CASES)

    def fmt_month(m):
        return "not within horizon" if m is None else f"month {m}"

    lines = [
        f"# Time-phased break-even — {model['opportunity_id']} {model.get('name', '')}".rstrip(),
        "",
        f"Linear merchant ramp to each case's active_merchants over {b.ramp_months} months, "
        f"{b.months}-month horizon, steady-state unit economics from the commercial model. "
        "Structurally absent (stated, not hidden): cohort maturation, churn, seasonality, "
        "credit-line capital (this is operating cash flow, not balance-sheet funding of drawn balances).",
        "",
        "| Output | Downside | Base | Upside |",
        "|---|---|---|---|",
        "| Monthly net turns positive | {} | {} | {} |".format(*(fmt_month(r.monthly_breakeven_month) for r in (d, b, u))),
        "| Cumulative cash turns positive | {} | {} | {} |".format(*(fmt_month(r.cumulative_breakeven_month) for r in (d, b, u))),
        "| **Peak funding need (AED)** | {:,.0f} | {:,.0f} | {:,.0f} |".format(*(r.peak_funding_need for r in (d, b, u))),
        "| …reached in | {} | {} | {} |".format(*(fmt_month(r.peak_month or None) for r in (d, b, u))),
        "| Cumulative position at month {} | {:,.0f} | {:,.0f} | {:,.0f} |".format(
            b.months, d.end_cumulative, b.end_cumulative, u.end_cumulative),
        "",
        "If monthly net never turns positive within the horizon, the case's merchant count "
        "cannot carry its fixed costs — the peak funding need then grows without bound and the "
        "number shown is a horizon-truncated minimum.",
    ]
    return "\n".join(lines) + "\n"
