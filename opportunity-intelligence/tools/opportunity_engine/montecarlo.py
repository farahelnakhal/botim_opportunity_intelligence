"""Monte Carlo simulation over a three-case commercial model.

The downside/base/upside cases define a triangular distribution per input
(low = worst-case value, mode = base, high = best-case value — direction-
agnostic: min/max are taken per input, so cost inputs where "downside" is the
larger number work unchanged). Inputs are sampled independently and the full
model recomputed per draw, yielding distributions of contribution and
break-even instead of three points.

Deterministic by default (fixed seed) so runs are reproducible and testable.

Known limitation, stated rather than hidden: inputs are sampled independently,
with no correlation structure (e.g. routed_share and ecl_rate are plausibly
negatively correlated). Treat tail probabilities as indicative. The named
scenarios in stress.py cover correlated adversity explicitly.
"""

import random
from dataclasses import dataclass, field

from . import commercial
from .commercial import CASES, InputError


@dataclass
class SimulationResult:
    n: int
    seed: int
    contribution_mean: float
    contribution_percentiles: dict          # {5: x, 25: x, 50: x, 75: x, 95: x}
    p_loss: float                           # P(contribution <= 0)
    p_beats_base: float                     # P(contribution >= base-case contribution)
    breakeven_percentiles: dict             # among profitable draws
    p_never_breakeven: float                # = p_loss (no positive unit economics)
    base_contribution: float
    worst_draw: float
    best_draw: float
    inputs_ranges: dict = field(default_factory=dict)  # name -> (low, mode, high)


def _percentile(sorted_values, pct):
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(sorted_values) - 1)
    frac = k - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def input_ranges(model):
    """Per input: (low, mode, high) across the three cases, mode clamped.

    Optional inputs are sampled too, but must appear in all three cases or
    none — a half-specified optional input silently changes model shape
    between draws, so it is rejected instead. avg_credit_duration_days is
    excluded (reporting-only; no economic effect).
    """
    ranges = {}
    sampled_names = list(commercial.REQUIRED_INPUTS)
    for name in commercial.OPTIONAL_INPUTS:
        if name == "avg_credit_duration_days":
            continue
        present = [c for c in CASES if name in model["cases"][c]]
        if present and len(present) != len(CASES):
            raise InputError(
                f"optional input '{name}' present in {present} but not all cases — "
                "provide it in all three cases or none"
            )
        if present:
            sampled_names.append(name)
    for name in sampled_names:
        values = [commercial._norm(model["cases"][c][name], name)[0] for c in CASES]
        base = values[1]
        low, high = min(values), max(values)
        ranges[name] = (low, min(max(base, low), high), high)
    return ranges


def simulate(model, n=5000, seed=42):
    """Run n draws. Returns SimulationResult."""
    if n < 100:
        raise InputError(f"n must be >= 100 for meaningful percentiles, got {n}")
    for key in ("opportunity_id", "cases"):
        if key not in model:
            raise InputError(f"model missing top-level key '{key}'")
    missing = [c for c in CASES if c not in model["cases"]]
    if missing:
        raise InputError(f"model missing cases: {', '.join(missing)}")

    ranges = input_ranges(model)
    base_result = commercial.compute_case("base", model["cases"]["base"])
    rng = random.Random(seed)

    contributions, breakevens = [], []
    for _ in range(n):
        sampled = {}
        for name, (low, mode, high) in ranges.items():
            if low == high:
                sampled[name] = low
            else:
                value = rng.triangular(low, high, mode)
                if name in ("routed_share", "utilisation", "offline_share"):
                    value = min(1.0, max(0.0, value))
                sampled[name] = value
        result = commercial.compute_case("simulation", sampled)
        contributions.append(result.contribution)
        if result.breakeven_merchants is not None:
            breakevens.append(result.breakeven_merchants)

    contributions.sort()
    breakevens.sort()
    pcts = (5, 25, 50, 75, 95)
    return SimulationResult(
        n=n,
        seed=seed,
        contribution_mean=sum(contributions) / n,
        contribution_percentiles={p: _percentile(contributions, p) for p in pcts},
        p_loss=sum(1 for c in contributions if c <= 0) / n,
        p_beats_base=sum(1 for c in contributions if c >= base_result.contribution) / n,
        breakeven_percentiles={p: _percentile(breakevens, p) for p in pcts},
        p_never_breakeven=1 - len(breakevens) / n,
        base_contribution=base_result.contribution,
        worst_draw=contributions[0],
        best_draw=contributions[-1],
        inputs_ranges=ranges,
    )


def render_markdown(model, sim):
    c = sim.contribution_percentiles
    b = sim.breakeven_percentiles

    def fmt(v, pattern="{:,.0f}"):
        return "—" if v is None else pattern.format(v)

    lines = [
        f"# Monte Carlo — {model['opportunity_id']} {model.get('name', '')}".rstrip(),
        "",
        f"{sim.n:,} draws, seed {sim.seed}. Inputs sampled independently from triangular "
        "distributions spanning the three cases (correlations NOT modelled — see module docstring; "
        "tail probabilities are indicative).",
        "",
        "## Contribution per merchant per month (AED)",
        "",
        "| Statistic | Value |",
        "|---|---|",
        f"| Mean | {sim.contribution_mean:,.0f} |",
        f"| P5 / P25 / P50 / P75 / P95 | {fmt(c[5])} / {fmt(c[25])} / {fmt(c[50])} / {fmt(c[75])} / {fmt(c[95])} |",
        f"| Worst / best draw | {sim.worst_draw:,.0f} / {sim.best_draw:,.0f} |",
        f"| Deterministic base case (for reference) | {sim.base_contribution:,.0f} |",
        f"| **P(loss-making unit economics)** | **{sim.p_loss:.1%}** |",
        f"| P(at or above base case) | {sim.p_beats_base:.1%} |",
        "",
        "## Break-even merchants (among profitable draws)",
        "",
        "| Statistic | Value |",
        "|---|---|",
        f"| P5 / P50 / P95 | {fmt(b[5])} / {fmt(b[50])} / {fmt(b[95])} |",
        f"| **P(never breaks even at unit level)** | **{sim.p_never_breakeven:.1%}** |",
    ]
    return "\n".join(lines) + "\n"
