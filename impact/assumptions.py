"""Per-opportunity assumption register.

Exposes total score, evidence confidence, unresolved-assumption count, and each
assumption with supporting evidence, status, sensitivity and next validation.
Status enum: untested | partially supported | supported | contradicted.
Updated only through an approved impact.
"""

import json

from .proposal import _assumption_count, _raw_score, RAW_MAX

STATUSES = ("untested", "partially supported", "supported", "contradicted")


def build_from_scorecard(card):
    reg = {"opportunity_id": card["opportunity_id"], "assumptions": []}
    for factor, e in card["scores"].items():
        if e.get("assumption", True):
            reg["assumptions"].append({
                "factor": factor, "text": e.get("basis", ""),
                "status": "untested", "supporting_ev": [],
                "sensitivity": "", "next_validation": "",
            })
    return reg


def compute_new(card, old_register, assumption_changes):
    reg = old_register or build_from_scorecard(card)
    by_factor = {a["factor"]: a for a in reg["assumptions"]}
    for ch in assumption_changes:
        a = by_factor.get(ch["assumption"])
        if a is None:
            a = {"factor": ch["assumption"], "text": "", "status": "untested",
                 "supporting_ev": [], "sensitivity": "", "next_validation": ""}
            reg["assumptions"].append(a)
            by_factor[a["factor"]] = a
        if ch["proposed_status"] not in STATUSES:
            raise ValueError(f"bad status {ch['proposed_status']}")
        a["status"] = ch["proposed_status"]
        for ev in ch.get("supporting_ev", []):
            if ev not in a["supporting_ev"]:
                a["supporting_ev"].append(ev)
        if ch.get("next_validation"):
            a["next_validation"] = ch["next_validation"]
    return reg


def dumps(register):
    return json.dumps(register, indent=2, ensure_ascii=False) + "\n"


def render_markdown(card, register):
    scores = card["scores"]
    unresolved = [a for a in register["assumptions"]
                  if a["status"] in ("untested", "partially supported")]
    lines = [
        f"# Assumption register — {register['opportunity_id']}",
        "",
        f"- Raw score: **{_raw_score(scores)}/{RAW_MAX}**",
        f"- Evidence confidence: {card.get('evidence_confidence', 'not stated')}",
        f"- Assumption-based factors: {_assumption_count(scores)}/17",
        f"- Unresolved assumptions (untested / partially supported): **{len(unresolved)}**",
        "",
        "| Assumption (factor) | Status | Supporting EV | Sensitivity | Next validation |",
        "|---|---|---|---|---|",
    ]
    for a in register["assumptions"]:
        lines.append("| {} | {} | {} | {} | {} |".format(
            a["factor"], a["status"], ", ".join(a["supporting_ev"]) or "—",
            a.get("sensitivity") or "—", a.get("next_validation") or "—"))
    return "\n".join(lines) + "\n"
