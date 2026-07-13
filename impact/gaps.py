"""Portfolio evidence-gap list with an explicitly heuristic priority ranking.

Each gap carries priority_score, priority_band, reasons, inputs_used and
missing_inputs. The ranking is a documented weighted heuristic — NOT a
statistically objective score — and every input and gap is shown.
"""

import json

from . import genmeta, paths, tracker

# transparent weights (documented, not objective)
IMPORTANCE_W = {"critical": 3, "high": 2, "medium": 1, "low": 0}
STATUS_W = {"contradicted": 3, "untested": 2, "partially_supported": 1, "supported": 0}
CONF_W = {None: 2, "low": 2, "medium": 1, "high": 0}

QUESTION = {
    "customer": "Who exactly is the {opp} customer, and is the segment definition evidenced?",
    "pain": "Is the {opp} pain severe, frequent and costly enough to drive action?",
    "behaviour": "What do {opp} merchants actually do today, and what does the workaround cost?",
    "switching": "Will {opp} merchants actually switch, not just search for alternatives?",
    "willingness_to_pay": "Do {opp} customers pay enough for the offer to switch?",
    "product": "Does BOTIM/AstraTech have a real, defensible advantage for {opp}?",
    "commercial": "Do the {opp} unit economics and volumes hold at realistic prices?",
    "credit": "Is the {opp} credit need real and the risk visible enough to lend?",
    "regulatory": "Do regulatory constraints block {opp}?",
    "operational": "Can {opp} be validated and operated feasibly?",
    "technical": "Is a 7-week {opp} MVP technically feasible?",
}


def _band(score):
    if score >= 7:
        return "critical"
    if score >= 5:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def _score_gap(a, capped, ease_score):
    imp = a["decision_importance"]
    status = a["status"]
    conf = a["evidence_confidence"]["derived"]
    inputs = {
        "decision_importance": imp,
        "status": status,
        "evidence_confidence": conf,
        "assumption_capped": capped,
        "ease_of_validation_score": ease_score,
    }
    missing = []
    if conf is None:
        missing.append("no cited supporting evidence → evidence_confidence unavailable")
    if not a.get("sensitivity"):
        missing.append("quantified sensitivity not available (scorecard is an unweighted average)")

    score = IMPORTANCE_W.get(imp, 0) + STATUS_W.get(status, 0) + CONF_W.get(conf, 2)
    reasons = [
        f"{imp} decision importance",
        {"untested": "no evidence yet (untested)",
         "partially_supported": "only partially supported",
         "contradicted": "has contradicting evidence",
         "supported": "already supported"}[status],
        {None: "no supporting evidence cited", "low": "supporting evidence is low-confidence",
         "medium": "supporting evidence only medium-confidence",
         "high": "supporting evidence high-confidence"}[conf],
    ]
    if capped:
        score += 1
        reasons.append("resolving assumptions can lift the >6-assumption classification cap")
    if ease_score is not None and ease_score >= 4:
        score += 1
        reasons.append("cheaply testable now (ease_of_validation high)")
    return score, _band(score), reasons, inputs, missing


def build_portfolio(now):
    scoring, _ = paths.load_engine()
    sc_dir = paths.KB / "opportunity-scores"
    gaps, no_ev, contradicted, ve_map = [], [], [], {}
    source_files = []
    opp_ids = []
    for sp in sorted(sc_dir.glob("*-scorecard.json")):
        card = json.loads(sp.read_text(encoding="utf-8"))
        opp_ids.append(card["opportunity_id"])

    for opp in opp_ids:
        model = tracker.build(opp, now)
        source_files += [paths.REPO_ROOT / f for f in model["meta"]["source_files"]]
        ease = None
        card = json.loads(tracker.scorecard_path(opp).read_text(encoding="utf-8"))
        if "ease_of_validation" in card["scores"]:
            ease = card["scores"]["ease_of_validation"]["score"]
        capped = model["score"]["capped"]
        ve_map[opp] = {}
        for a in model["assumptions"]:
            if a["related_ve"]:
                for v in a["related_ve"]:
                    ve_map[opp].setdefault(v, []).append(a["assumption_id"])
            if not a["supporting_ev"]:
                no_ev.append({"opportunity_id": opp, "assumption_id": a["assumption_id"],
                              "category": a["category"], "status": a["status"]})
            if a["status"] == "contradicted":
                contradicted.append({"opportunity_id": opp, "assumption_id": a["assumption_id"],
                                     "supporting_ev": a["supporting_ev"],
                                     "contradicting_ev": a["contradicting_ev"]})
            if a["status"] == "supported":
                continue  # not a gap
            score, band, reasons, inputs, missing = _score_gap(a, capped, ease)
            gaps.append({
                "opportunity_id": opp, "assumption_id": a["assumption_id"],
                "factor": a.get("factor"), "category": a["category"],
                "statement": a["statement"], "status": a["status"],
                "decision_importance": a["decision_importance"],
                "priority_score": score, "priority_band": band,
                "reasons": reasons, "inputs_used": inputs, "missing_inputs": missing,
                "related_ve": a["related_ve"],
                "question": QUESTION.get(a["category"], "Is this assumption evidenced?").format(opp=opp),
            })

    gaps.sort(key=lambda g: (-g["priority_score"], g["opportunity_id"], g["assumption_id"]))
    for i, g in enumerate(gaps, 1):
        g["priority_rank"] = i

    # de-dup source files, stable order
    seen, uniq = set(), []
    for f in source_files:
        s = str(f)
        if s not in seen:
            seen.add(s); uniq.append(f)

    return {
        "meta": genmeta.build_meta("evidence-gaps", uniq, now),
        "ranking_method": {
            "type": "heuristic (not statistically objective)",
            "weights": {"importance": IMPORTANCE_W, "status": STATUS_W, "confidence": CONF_W,
                        "cap_bonus": 1, "ease_bonus": 1},
            "bands": {"critical": ">=7", "high": "5-6", "medium": "3-4", "low": "<=2"},
        },
        "gaps": gaps,
        "high_priority_questions": [{"priority_rank": g["priority_rank"], "priority_band": g["priority_band"],
                                     "opportunity_id": g["opportunity_id"], "question": g["question"],
                                     "reasons": g["reasons"]} for g in gaps],
        "assumptions_no_supporting_evidence": no_ev,
        "assumptions_contradicted": contradicted,
        "ve_assumption_map": ve_map,
    }


def render_markdown(report, top=None):
    lines = ["# Portfolio evidence-gap report", "",
             f"_Ranking is heuristic, not objective. Weights: {report['ranking_method']['weights']}_", "",
             "| # | Band | Opportunity | Assumption | Priority | Reasons |",
             "|---|---|---|---|---|---|"]
    gaps = report["gaps"][:top] if top else report["gaps"]
    for g in gaps:
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            g["priority_rank"], g["priority_band"], g["opportunity_id"],
            g["assumption_id"], g["priority_score"], "; ".join(g["reasons"])))
    lines += ["", "## Highest-priority unanswered questions"]
    for q in report["high_priority_questions"][:(top or 5)]:
        lines.append(f"{q['priority_rank']}. [{q['priority_band']}] {q['question']}  \n"
                     f"   why: {'; '.join(q['reasons'])}")
    return "\n".join(lines) + "\n"
