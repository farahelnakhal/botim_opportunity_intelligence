"""One-at-a-time sensitivity (tornado) analysis on a commercial model case.

For each input, perturb it by a degradation factor in BOTH directions, keep
the direction that hurts contribution most, and rank inputs by damage. This
mechanises the assumption register's "what happens if this is 50% worse"
column — no hand-labelling of which direction is "worse" (for some inputs,
e.g. utilisation, the harmful direction depends on the rate structure).

Fractions (routed_share, utilisation) are clamped to [0, 1] after perturbation.
active_merchants and fixed_costs_monthly don't move per-merchant contribution;
their effect is reported through the break-even column.
"""

from dataclasses import dataclass

from . import commercial

FRACTION_INPUTS = ("routed_share", "utilisation")


@dataclass
class SensitivityRow:
    input_name: str
    base_value: float
    worst_value: float          # perturbed value in the harmful direction
    contribution: float         # contribution at worst_value
    contribution_delta: float   # contribution - baseline contribution (<= 0)
    breakeven: float            # break-even merchants at worst_value (None = never)
    label: str                  # F/E/A of the input


def _perturbed(raw_case, name, value):
    case = dict(raw_case)
    original = case[name]
    if isinstance(original, dict):
        entry = dict(original)
        entry["value"] = value
        case[name] = entry
    else:
        case[name] = value
    return case


def analyse(model, case_name="base", degrade=0.5):
    """Return (baseline CaseResult, [SensitivityRow] ranked by damage)."""
    if not 0 < degrade < 1:
        raise commercial.InputError(f"degrade must be in (0, 1), got {degrade}")
    raw_case = model["cases"][case_name]
    baseline = commercial.compute_case(case_name, raw_case)

    rows = []
    for name in commercial.REQUIRED_INPUTS:
        base_value = baseline.v(name)
        candidates = [base_value * (1 - degrade), base_value * (1 + degrade)]
        if name in FRACTION_INPUTS:
            candidates = [min(1.0, max(0.0, c)) for c in candidates]

        def badness(result):
            # primary: lower contribution; tie-break: worse break-even
            # (inputs like fixed_costs don't move contribution but move break-even)
            be = float("inf") if result.breakeven_merchants is None else result.breakeven_merchants
            return (result.contribution, -be)

        worst = None
        for candidate in candidates:
            if candidate == base_value:
                continue
            result = commercial.compute_case(case_name, _perturbed(raw_case, name, candidate))
            if worst is None or badness(result) < badness(worst[1]):
                worst = (candidate, result)
        if worst is None:  # zero-valued input: +/- both land on 0
            continue

        worst_value, result = worst
        rows.append(SensitivityRow(
            input_name=name,
            base_value=base_value,
            worst_value=worst_value,
            contribution=result.contribution,
            contribution_delta=result.contribution - baseline.contribution,
            breakeven=result.breakeven_merchants,
            label=baseline.assumption_labels[name],
        ))

    rows.sort(key=lambda r: r.contribution_delta)
    return baseline, rows


def grid(model, input_x, input_y, case_name="base", steps=7):
    """Two-way stress grid: vary two inputs across their three-case span,
    recompute contribution at every combination.

    Returns (x_values, y_values, matrix) where matrix[i][j] is the
    contribution at y_values[i], x_values[j].
    """
    for name in (input_x, input_y):
        if name not in commercial.REQUIRED_INPUTS:
            raise commercial.InputError(f"unknown input '{name}'")
    if input_x == input_y:
        raise commercial.InputError("grid needs two different inputs")
    if steps < 3:
        raise commercial.InputError("grid needs at least 3 steps")

    def span(name):
        values = [commercial._norm(model["cases"][c][name], name)[0] for c in commercial.CASES]
        low, high = min(values), max(values)
        if low == high:  # constant across cases: spread ±50% so the grid is informative
            low, high = low * 0.5, high * 1.5
        if name in FRACTION_INPUTS:
            low, high = max(0.0, low), min(1.0, high)
        return [low + (high - low) * i / (steps - 1) for i in range(steps)]

    raw_case = model["cases"][case_name]
    x_values, y_values = span(input_x), span(input_y)
    matrix = []
    for y in y_values:
        row = []
        for x in x_values:
            shocked = _perturbed(_perturbed(raw_case, input_x, x), input_y, y)
            row.append(commercial.compute_case(case_name, shocked).contribution)
        matrix.append(row)
    return x_values, y_values, matrix


def render_grid_markdown(model, input_x, input_y, case_name, x_values, y_values, matrix):
    lines = [
        f"# Stress grid — {model['opportunity_id']}: {input_y} × {input_x}",
        "",
        f"Case: **{case_name}** · cell = contribution/merchant/month; negative cells bracketed. "
        "The bracket boundary is the viability frontier.",
        "",
        "| {} \\ {} | ".format(input_y, input_x) + " | ".join(f"{x:g}" for x in x_values) + " |",
        "|" + "---|" * (len(x_values) + 1),
    ]
    for y, row in zip(y_values, matrix):
        cells = [f"({c:,.0f})" if c <= 0 else f"{c:,.0f}" for c in row]
        lines.append(f"| **{y:g}** | " + " | ".join(cells) + " |")
    n_neg = sum(1 for row in matrix for c in row if c <= 0)
    lines += ["", f"{n_neg}/{len(matrix) * len(matrix[0])} combinations are loss-making."]
    return "\n".join(lines) + "\n"


def render_markdown(model, case_name, degrade, baseline, rows):
    lines = [
        f"# Sensitivity (tornado) — {model['opportunity_id']} {model['name']}",
        "",
        f"Case: **{case_name}** · each input perturbed ±{degrade:.0%}, harmful direction kept. "
        f"Baseline contribution: **{baseline.contribution:,.0f}**/merchant/month, "
        f"break-even {'never' if baseline.breakeven_merchants is None else format(baseline.breakeven_merchants, ',.0f')} merchants.",
        "",
        "| Rank | Input | F/E/A | Base value | Worst value | Contribution | Δ | Break-even |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        lines.append(
            "| {rank} | {name} | {label} | {base:g} | {worst:g} | {contrib:,.0f} | {delta:,.0f} | {be} |".format(
                rank=i, name=r.input_name, label=r.label,
                base=r.base_value, worst=r.worst_value,
                contrib=r.contribution, delta=r.contribution_delta,
                be="never" if r.breakeven is None else format(r.breakeven, ",.0f"),
            )
        )
    top = [r.input_name for r in rows[:3]]
    lines += [
        "",
        f"**Validate first (largest downside): {', '.join(top)}.** "
        "Assumption-labelled (A) inputs near the top of this table are the model's real risk.",
    ]
    return "\n".join(lines) + "\n"
