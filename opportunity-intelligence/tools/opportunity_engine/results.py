"""Verdict engine for validation-experiment results.

When field results land, the verdict comes from the pre-committed thresholds
mechanically — not from post-hoc argument. The thresholds are copied from the
VE spec into a result JSON *before* the experiment runs; observed values are
filled in afterwards; this module only compares.

Result JSON schema (knowledge-base/validation/VE-nnn-result.json):

{
  "experiment_id": "VE-001",
  "proposition": "OPP-001",
  "metrics": [
    {
      "name": "waitlist_completion_pct",
      "observed": null,                       # fill after the run
      "success": {"op": ">=", "value": 40},   # pre-committed
      "failure": {"op": "<=", "value": 15}    # pre-committed; null = cannot alone kill
    }, ...
  ],
  "on_pass": "...", "on_fail": "...", "on_inconclusive": "..."
}

Verdict rules (from templates/validation-experiment.md):
- FAIL if ANY metric breaches its failure threshold — kill thresholds kill.
- PASS only if ALL metrics with a success threshold meet it.
- Otherwise INCONCLUSIVE — extend or redesign, never silently continue.
- PENDING while any metric's observed value is null.
"""

from .commercial import InputError

OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
}

VERDICTS = ("pass", "fail", "inconclusive", "pending")


def _check_condition(cond, where):
    if cond is None:
        return
    if not isinstance(cond, dict) or "op" not in cond or "value" not in cond:
        raise InputError(f"{where}: condition must be {{op, value}} or null")
    if cond["op"] not in OPS:
        raise InputError(f"{where}: op must be one of {sorted(OPS)}, got {cond['op']!r}")
    if not isinstance(cond["value"], (int, float)) or isinstance(cond["value"], bool):
        raise InputError(f"{where}: value must be numeric")


def _met(cond, observed):
    return OPS[cond["op"]](observed, cond["value"])


def evaluate(result):
    """Evaluate a result dict. Returns an evaluation dict with per-metric detail."""
    for key in ("experiment_id", "proposition", "metrics", "on_pass", "on_fail", "on_inconclusive"):
        if key not in result:
            raise InputError(f"result missing key '{key}'")
    metrics = result["metrics"]
    if not metrics:
        raise InputError("result has no metrics")

    detail = []
    any_fail = False
    any_pending = False
    all_success = True
    has_success_criteria = False

    for i, m in enumerate(metrics):
        where = f"metric[{i}] '{m.get('name', '?')}'"
        if "name" not in m or "observed" not in m:
            raise InputError(f"{where}: needs 'name' and 'observed'")
        _check_condition(m.get("success"), where + " success")
        _check_condition(m.get("failure"), where + " failure")
        if m.get("success") is None and m.get("failure") is None:
            raise InputError(f"{where}: needs at least one of success/failure thresholds")

        observed = m["observed"]
        if observed is None:
            any_pending = True
            detail.append({"name": m["name"], "observed": None, "state": "pending"})
            continue
        if not isinstance(observed, (int, float)) or isinstance(observed, bool):
            raise InputError(f"{where}: observed must be numeric or null")

        state = "between"
        if m.get("failure") is not None and _met(m["failure"], observed):
            state = "failed"
            any_fail = True
        elif m.get("success") is not None:
            has_success_criteria = True
            if _met(m["success"], observed):
                state = "met"
            else:
                all_success = False
        detail.append({"name": m["name"], "observed": observed, "state": state})

    if any_fail:
        verdict = "fail"          # kill thresholds kill, even with other metrics pending
    elif any_pending:
        verdict = "pending"
    elif has_success_criteria and all_success:
        verdict = "pass"
    else:
        verdict = "inconclusive"

    action_key = {"pass": "on_pass", "fail": "on_fail", "inconclusive": "on_inconclusive"}.get(verdict)
    return {
        "experiment_id": result["experiment_id"],
        "proposition": result["proposition"],
        "verdict": verdict,
        "action": result[action_key] if action_key else "await remaining observations",
        "metrics": detail,
    }


def render_markdown(ev):
    lines = [
        f"# Verdict — {ev['experiment_id']} ({ev['proposition']})",
        "",
        "| Metric | Observed | State |",
        "|---|---|---|",
    ]
    for m in ev["metrics"]:
        lines.append("| {} | {} | {} |".format(
            m["name"], "—" if m["observed"] is None else f"{m['observed']:g}", m["state"]
        ))
    lines += [
        "",
        f"**Verdict: {ev['verdict'].upper()}**",
        f"**Pre-committed action:** {ev['action']}",
    ]
    if ev["verdict"] == "inconclusive":
        lines.append("\nBetween thresholds: extend or redesign per the spec — do not silently continue.")
    return "\n".join(lines) + "\n"
