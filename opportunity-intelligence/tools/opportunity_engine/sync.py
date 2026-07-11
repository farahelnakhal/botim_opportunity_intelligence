"""Evidence→scorecard sync bridge (the A→B integration feature).

Maps Workstream A's 10 evidence axes onto Workstream B's 17 opportunity
dimensions and, for every scorecard, compares what cited evidence *implies*
against what the scorecard *says*. Report-only: it suggests re-scores and
(A)-flag flips; a human applies them, because scores are per-proposition
judgments, not axis averages.

Rules (agreed at the 2026-07-11 merge session):
- Only records with evidence strength >= 3 can drive suggestions — mirrors
  Workstream A's own rule that weak records are leads, not findings.
- Only records the scorecard already cites are used (segment-fuzzy matching
  is a human job); uncited-but-relevant records surface via `evidence` list.
- Unmapped axes are unmapped on purpose:
    urgency          -> feeds switching_intent qualitatively, no 1:1 scale
    dissatisfaction  -> informs competitor-failure narrative, not a dimension
    botim relevance  -> a routing gate, not an opportunity dimension
    evidence strength-> controls WHETHER to suggest, never WHAT to suggest
"""

import json
import re
from pathlib import Path

from . import evidence, scoring
from .commercial import InputError

AXIS_TO_DIMENSION = {
    "severity": "pain_severity",
    "frequency": "pain_frequency",
    "financial cost": "financial_impact",
    "workaround cost": "workaround_cost",
    "switching intent": "switching_intent",
    "willingness to pay": "willingness_to_pay",
}

UNMAPPED_AXES = ("urgency", "dissatisfaction", "botim relevance", "evidence strength")

MIN_STRENGTH = 3

EV_CITE_RE = re.compile(r"\bEV-\d{4}-W\d{2}-\d{3}\b")


def _implied(values):
    """Evidence-implied dimension score: mean of axis values, conventional rounding."""
    return int(sum(values) / len(values) + 0.5)


def suggestions_for_scorecard(card, records):
    """Compare one scorecard against the records it cites.

    Returns list of suggestion dicts:
      {dimension, current, implied, from_records, kind}
    kind: 'flip-assumption' (evidence exists for an (A) score),
          'rescore' (implied differs from current by >= 1),
          'both'
    """
    ev = scoring.evaluate(card)  # validates the card as a side effect
    cited = sorted({m for e in ev["scores"].values() for m in EV_CITE_RE.findall(e["basis"])})
    usable = [
        records[cid] for cid in cited
        if cid in records and records[cid]["scores"].get("evidence strength", 0) >= MIN_STRENGTH
    ]

    out = []
    for axis, dim in AXIS_TO_DIMENSION.items():
        values = [r["scores"][axis] for r in usable if axis in r["scores"]]
        if not values:
            continue
        implied = _implied(values)
        entry = ev["scores"][dim]
        flip = entry["assumption"]
        differs = abs(implied - entry["score"]) >= 1
        if not (flip or differs):
            continue
        kind = "both" if (flip and differs) else ("flip-assumption" if flip else "rescore")
        out.append({
            "dimension": dim,
            "axis": axis,
            "current": entry["score"],
            "currently_assumption": entry["assumption"],
            "implied": implied,
            "n_records": len(values),
            "from_records": [r["id"] for r in usable if axis in r["scores"]],
            "kind": kind,
        })
    return {
        "opportunity_id": card["opportunity_id"],
        "cited": cited,
        "usable": [r["id"] for r in usable],
        "excluded_weak": [c for c in cited if c in records
                          and records[c]["scores"].get("evidence strength", 0) < MIN_STRENGTH],
        "unresolved": [c for c in cited if c not in records],
        "suggestions": out,
    }


def analyse(root="."):
    """Run the sync over every scorecard in the repo. Returns list of per-card reports."""
    root = Path(root)
    records = evidence.load_records(root / "knowledge-base" / "customer-evidence")
    reports = []
    for path in sorted((root / "knowledge-base" / "opportunity-scores").glob("*.json")):
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise InputError(f"{path}: {exc}")
        reports.append(suggestions_for_scorecard(card, records))
    return reports


def render_markdown(reports):
    lines = ["# Evidence → scorecard sync", ""]
    if not reports:
        return lines[0] + "\n\nNo scorecards found.\n"
    total = sum(len(r["suggestions"]) for r in reports)
    lines.append(f"{len(reports)} scorecard(s) analysed · {total} suggestion(s). "
                 "Report-only — apply by editing the scorecard JSON and re-running `score`.")
    for r in reports:
        lines += ["", f"## {r['opportunity_id']}", ""]
        if not r["cited"]:
            lines.append("- cites no evidence records — all suggestions require citations first")
            continue
        lines.append(f"- cited: {len(r['cited'])} · usable (strength ≥{MIN_STRENGTH}): {len(r['usable'])}"
                     + (f" · weak (excluded): {', '.join(r['excluded_weak'])}" if r["excluded_weak"] else "")
                     + (f" · UNRESOLVED: {', '.join(r['unresolved'])}" if r["unresolved"] else ""))
        if not r["suggestions"]:
            lines.append("- no divergence between cited evidence and current scores")
        for s in r["suggestions"]:
            lines.append(
                f"- **{s['dimension']}**: current {s['current']}"
                f"{' (A)' if s['currently_assumption'] else ''} vs evidence-implied {s['implied']} "
                f"from {s['n_records']} record(s) ({', '.join(s['from_records'])}) — {s['kind']}"
            )
    return "\n".join(lines) + "\n"
