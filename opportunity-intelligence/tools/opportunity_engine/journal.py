"""Calibrated decision journal.

Implements reasoning-protocol step 4: judgments become dated, falsifiable
predictions with probabilities, logged BEFORE outcomes are knowable and
Brier-scored when resolved. Probabilities are never edited — a wrong
prediction is data; corrections are new predictions.

Journal file: knowledge-base/product-ideas/decision-journal.json
{
  "predictions": [
    {"id": "PRED-001", "statement": "...", "p": 0.30, "made": "YYYY-MM-DD",
     "resolve_by": "YYYY-MM-DD", "links": ["VE-001"],
     "outcome": null | true | false, "resolved_on": null | "YYYY-MM-DD",
     "resolution_note": ""}
  ]
}
"""

import json
import re
from pathlib import Path

from .commercial import InputError

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^PRED-\d{3}$")

CALIBRATION_BUCKETS = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0))


def load(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"predictions": []}
    except json.JSONDecodeError as exc:
        raise InputError(f"journal is not valid JSON: {exc}")
    validate(data)
    return data


def save(data, path):
    validate(data)
    Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def validate(data):
    if not isinstance(data, dict) or "predictions" not in data:
        raise InputError("journal must be an object with a 'predictions' array")
    seen = set()
    for i, p in enumerate(data["predictions"]):
        where = f"prediction[{i}] ({p.get('id', '?')})"
        for key in ("id", "statement", "p", "made", "resolve_by"):
            if key not in p:
                raise InputError(f"{where}: missing '{key}'")
        if not ID_RE.match(p["id"]):
            raise InputError(f"{where}: id must match PRED-nnn")
        if p["id"] in seen:
            raise InputError(f"{where}: duplicate id")
        seen.add(p["id"])
        if not str(p["statement"]).strip():
            raise InputError(f"{where}: empty statement")
        prob = p["p"]
        if not isinstance(prob, (int, float)) or isinstance(prob, bool) or not 0 < prob < 1:
            raise InputError(f"{where}: p must be strictly between 0 and 1 (certainty isn't a prediction)")
        for key in ("made", "resolve_by"):
            if not DATE_RE.match(str(p[key])):
                raise InputError(f"{where}: {key} must be YYYY-MM-DD")
        outcome = p.get("outcome")
        if outcome is not None and not isinstance(outcome, bool):
            raise InputError(f"{where}: outcome must be null, true, or false")
        if outcome is not None and not DATE_RE.match(str(p.get("resolved_on") or "")):
            raise InputError(f"{where}: resolved prediction needs resolved_on date")
        if p.get("excluded_from_calibration") and not str(p.get("exclusion_reason", "")).strip():
            raise InputError(f"{where}: excluded_from_calibration requires exclusion_reason")


def add(data, statement, p, made, resolve_by, links=None, rationale=""):
    next_n = 1 + max((int(x["id"][5:]) for x in data["predictions"]), default=0)
    entry = {
        "id": f"PRED-{next_n:03d}",
        "statement": statement,
        "p": p,
        "made": made,
        "resolve_by": resolve_by,
        "links": links or [],
        "rationale": rationale,   # pre-registration reasoning (RC ids etc.) — set at logging time
        "outcome": None,
        "resolved_on": None,
        "resolution_note": "",
    }
    data["predictions"].append(entry)
    validate(data)
    return entry


def resolve(data, pred_id, outcome, resolved_on, note=""):
    for p in data["predictions"]:
        if p["id"] == pred_id:
            if p.get("outcome") is not None:
                raise InputError(f"{pred_id} already resolved — outcomes are never edited; log a new prediction")
            if str(resolved_on) <= str(p["made"]):
                raise InputError(
                    f"{pred_id}: resolution on/before the logging date ({p['made']}) contaminates "
                    "calibration — if the outcome was already knowable, it was not a prediction (audit R-1)"
                )
            p["outcome"] = bool(outcome)
            p["resolved_on"] = resolved_on
            p["resolution_note"] = note
            validate(data)
            return p
    raise InputError(f"no prediction {pred_id}")


def calibration(data, today=None):
    """Brier score + per-bucket calibration over resolved, non-excluded
    predictions; open/overdue/excluded/contaminated listings for the report.

    Contaminated = resolved on/before its logging date and NOT explicitly
    excluded — such entries must never enter the Brier score (audit R-1);
    they are excluded here and flagged so `check` can fail on them.
    """
    all_resolved = [p for p in data["predictions"] if p.get("outcome") is not None]
    excluded = [p for p in all_resolved if p.get("excluded_from_calibration")]
    contaminated = [p for p in all_resolved
                    if not p.get("excluded_from_calibration")
                    and str(p.get("resolved_on") or "") <= str(p["made"])]
    resolved = [p for p in all_resolved if p not in excluded and p not in contaminated]
    open_ = [p for p in data["predictions"] if p.get("outcome") is None]
    overdue = [p for p in open_ if today and str(p["resolve_by"]) < today]

    brier = (
        sum((p["p"] - (1.0 if p["outcome"] else 0.0)) ** 2 for p in resolved) / len(resolved)
        if resolved else None
    )
    buckets = []
    for lo, hi in CALIBRATION_BUCKETS:
        members = [p for p in resolved if lo <= p["p"] < hi or (hi == 1.0 and p["p"] == 1.0)]
        buckets.append({
            "range": f"{lo:.0%}–{hi:.0%}",
            "n": len(members),
            "mean_p": sum(p["p"] for p in members) / len(members) if members else None,
            "observed": sum(1 for p in members if p["outcome"]) / len(members) if members else None,
        })
    return {"brier": brier, "n_resolved": len(resolved), "buckets": buckets,
            "open": open_, "overdue": overdue,
            "excluded": excluded, "contaminated": contaminated}


def render_markdown(cal):
    lines = ["# Calibration report", ""]
    if cal["brier"] is None:
        lines.append("No resolved predictions yet — Brier score unavailable. "
                     "(Reference: always guessing 50% scores 0.25; lower is better.)")
    else:
        lines.append(f"Resolved predictions: {cal['n_resolved']} · **Brier score: {cal['brier']:.3f}** "
                     "(0 = clairvoyant, 0.25 = coin-flip guessing, lower is better)")
        lines += ["", "| Confidence bucket | n | Mean stated p | Observed frequency |", "|---|---|---|---|"]
        for b in cal["buckets"]:
            lines.append("| {} | {} | {} | {} |".format(
                b["range"], b["n"],
                "—" if b["mean_p"] is None else f"{b['mean_p']:.0%}",
                "—" if b["observed"] is None else f"{b['observed']:.0%}",
            ))
    if cal["excluded"]:
        lines += ["", f"Excluded from calibration ({len(cal['excluded'])}): "
                  + ", ".join(f"{p['id']} ({p.get('exclusion_reason', '')[:60]})" for p in cal["excluded"])]
    if cal["contaminated"]:
        lines += ["", "**CONTAMINATED (resolved on/before logging date, not excluded — fix required):** "
                  + ", ".join(p["id"] for p in cal["contaminated"])]
    lines += ["", f"## Open predictions ({len(cal['open'])})", ""]
    for p in cal["open"]:
        flag = " **OVERDUE**" if p in cal["overdue"] else ""
        lines.append(f"- {p['id']} (p={p['p']:.0%}, resolve by {p['resolve_by']}{flag}): {p['statement']}")
    return "\n".join(lines) + "\n"
