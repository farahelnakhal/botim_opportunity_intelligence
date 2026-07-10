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
