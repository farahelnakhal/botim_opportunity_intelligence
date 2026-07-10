"""Named adverse-scenario engine.

Monte Carlo (montecarlo.py) samples inputs independently; real failures are
correlated. This module applies named, explicitly-reasoned shock combinations
to a case and reports what survives. Each scenario is a business failure
story translated into input shocks — the code makes the story quantitative.

Shock forms: {"mul": x} multiply, {"add": x} add, {"set": x} replace.
Custom scenario files (JSON) use the same structure as SCENARIOS below.
"""

from dataclasses import dataclass

from . import commercial
from .commercial import InputError

SCENARIOS = {
    "credit_and_run": {
        "description": "Merchants draw credit, then route revenue away. Drawn balances persist "
                       "against collapsed flow: payment revenue and data visibility die while "
                       "credit exposure stays; losses spike.",
        "shocks": {
            "routed_share": {"mul": 0.3},
            "limit_multiple_of_routed_flow": {"mul": 3.33},  # limits were granted on pre-collapse flow
            "ecl_rate_annual": {"mul": 2.0},
        },
    },
    "adverse_selection": {
        "description": "Bank-rejected merchants dominate the book: losses at 2.5x plan, fraud "
                       "doubles, and good credits stay away.",
        "shocks": {
            "ecl_rate_annual": {"mul": 2.5},
            "fraud_loss_monthly": {"mul": 2.0},
        },
    },
    "rate_compression": {
        "description": "Competition (or credibility with good merchants) forces pricing down 40% "
                       "— the sensitivity analysis's #1 risk as a scenario.",
        "shocks": {
            "financing_rate_annual": {"mul": 0.6},
        },
    },
    "funding_squeeze": {
        "description": "AstraTech's cost of funds rises 75% (rate cycle / internal capital pricing).",
        "shocks": {
            "funding_rate_annual": {"mul": 1.75},
        },
    },
    "routing_decay": {
        "description": "Merchants onboard but routing halves after the novelty fades; limits "
                       "follow flow down so credit shrinks with it.",
        "shocks": {
            "routed_share": {"mul": 0.5},
        },
    },
    "cac_blowout": {
        "description": "The organic BOTIM channel underdelivers; paid acquisition at 4x assumed CAC.",
        "shocks": {
            "cac_amortised_monthly": {"mul": 4.0},
        },
    },
    "collections_heavy": {
        "description": "Servicing doubles as collections effort grows with a maturing book.",
        "shocks": {
            "servicing_cost_monthly": {"mul": 2.5},
        },
    },
    "perfect_storm": {
        "description": "Correlated bad year: routing decays, losses run hot, funding costs rise, "
                       "acquisition needs paid channels. Not the worst imaginable — a plausible "
                       "simultaneous combination.",
        "shocks": {
            "routed_share": {"mul": 0.5},
            "ecl_rate_annual": {"mul": 2.0},
            "funding_rate_annual": {"mul": 1.5},
            "cac_amortised_monthly": {"mul": 3.0},
        },
    },
}


@dataclass
class ScenarioResult:
    name: str
    description: str
    contribution: float
    contribution_delta: float
    breakeven: float          # None = never
    survived: bool            # contribution > 0


def _apply_shock(value, shock, name):
    if not isinstance(shock, dict) or len(shock) != 1:
        raise InputError(f"shock for '{name}' must be exactly one of mul/add/set")
    op, x = next(iter(shock.items()))
    if op == "mul":
        return value * x
    if op == "add":
        return value + x
    if op == "set":
        return x
    raise InputError(f"unknown shock op {op!r} for '{name}' (use mul/add/set)")


def apply_scenario(raw_case, scenario):
    """Return a new raw case dict with the scenario's shocks applied."""
    shocked = dict(raw_case)
    for name, shock in scenario["shocks"].items():
        if name not in commercial.REQUIRED_INPUTS:
            raise InputError(f"scenario shocks unknown input '{name}'")
        value, label, note = commercial._norm(raw_case[name], name)
        new_value = _apply_shock(value, shock, name)
        if name in ("routed_share", "utilisation"):
            new_value = min(1.0, max(0.0, new_value))
        shocked[name] = {"value": new_value, "label": label, "note": note}
    return shocked


def run(model, case_name="base", scenarios=None):
    """Run scenarios against a case. Returns (baseline CaseResult, [ScenarioResult])."""
    scenarios = scenarios or SCENARIOS
    raw_case = model["cases"][case_name]
    baseline = commercial.compute_case(case_name, raw_case)

    out = []
    for name, scenario in scenarios.items():
        if "shocks" not in scenario or not scenario["shocks"]:
            raise InputError(f"scenario '{name}' has no shocks")
        result = commercial.compute_case(name, apply_scenario(raw_case, scenario))
        out.append(ScenarioResult(
            name=name,
            description=scenario.get("description", ""),
            contribution=result.contribution,
            contribution_delta=result.contribution - baseline.contribution,
            breakeven=result.breakeven_merchants,
            survived=result.contribution > 0,
        ))
    out.sort(key=lambda r: r.contribution)
    return baseline, out


def render_markdown(model, case_name, baseline, scenario_results):
    killed = [r for r in scenario_results if not r.survived]
    lines = [
        f"# Scenario stress test — {model['opportunity_id']} {model.get('name', '')}".rstrip(),
        "",
        f"Case: **{case_name}** · baseline contribution {baseline.contribution:,.0f}/merchant/month. "
        "Scenarios apply correlated shocks that independent sampling cannot produce.",
        "",
        "| Scenario | Contribution | Δ | Break-even | Survives? |",
        "|---|---|---|---|---|",
    ]
    for r in scenario_results:
        lines.append("| {name} | {c:,.0f} | {d:,.0f} | {be} | {s} |".format(
            name=r.name, c=r.contribution, d=r.contribution_delta,
            be="never" if r.breakeven is None else format(r.breakeven, ",.0f"),
            s="yes" if r.survived else "**NO**",
        ))
    lines += ["", "## Scenario definitions", ""]
    for r in scenario_results:
        lines.append(f"- **{r.name}**: {r.description}")
    lines += [
        "",
        f"**{len(killed)}/{len(scenario_results)} scenarios kill unit economics"
        + (f": {', '.join(r.name for r in killed)}.**" if killed else ".**"),
        "Every killing scenario needs either a mitigation in product design or an "
        "early-warning metric in the MVP's failure thresholds.",
    ]
    return "\n".join(lines) + "\n"
