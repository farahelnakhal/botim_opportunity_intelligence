"""Part A research-request generator.

A generated request is a PROPOSAL (default status 'draft'); it does NOT enter
Part A's production backlog and is written only under knowledge-base/impact/
(and only with --write). Statuses: draft | approved | completed | rejected.
"""

import re

from . import genmeta, gaps, paths, tracker

ASM_RE = re.compile(r"^ASM-(OPP-\d+)-(.+)$")

REQUIRED_EVIDENCE = {
    "willingness_to_pay": "First-person evidence that this segment already pays (or commits to pay) a comparable price — behavioural, not stated interest.",
    "switching": "Evidence of actual or concretely-planned switching, not just fee complaints.",
    "pain": "Multiple independent first-person accounts quantifying frequency, severity and cost.",
    "credit": "Evidence the credit need is real and repayment risk is observable before lending.",
    "customer": "Independent confirmation of the segment definition (who, size, behaviour).",
    "behaviour": "Observed current workaround and its real cost/consequence.",
    "product": "Evidence the BOTIM/AstraTech advantage is real and defensible for this segment.",
    "commercial": "Volume and unit-economics evidence at realistic, competed prices.",
    "regulatory": "Confirmation of regulatory constraints or clearance.",
    "operational": "Evidence the validation/operation is feasible at the stated cost.",
    "technical": "Evidence a 7-week MVP is technically feasible.",
}
PREFERRED_SOURCES = {
    "willingness_to_pay": ["10-15 merchant interviews", "priced concept / term-sheet test"],
    "switching": ["merchant interviews", "provider-switch evidence in communities"],
    "pain": ["first-person interviews", "trade communities (multilingual)"],
    "credit": ["merchant interviews", "repayment-behaviour data from a pilot"],
    "customer": ["trade communities", "segment interviews"],
    "behaviour": ["interviews", "workaround-cost mapping"],
    "product": ["internal BOTIM data", "competitor teardown"],
    "commercial": ["pilot volumes", "priced offers"],
    "regulatory": ["regulatory review", "licence check"],
    "operational": ["ops feasibility review"],
    "technical": ["engineering spike"],
}


def _thresholds(model_item):
    """success/rejection thresholds from the linked VE result, if any."""
    scoring, _ = paths.load_engine()
    import json
    success, rejection, deadline = None, None, None
    for ve_id in model_item.get("related_ve", []):
        vp = paths.KB / "validation" / f"{ve_id}-result.json"
        if vp.exists():
            data = json.loads(vp.read_text(encoding="utf-8"))
            succ = [f"{m['name']} {m['success']['op']} {m['success']['value']}"
                    for m in data.get("metrics", []) if m.get("success")]
            fail = [f"{m['name']} {m['failure']['op']} {m['failure']['value']}"
                    for m in data.get("metrics", []) if m.get("failure")]
            if succ:
                success = f"{ve_id}: " + " and ".join(succ)
            if fail:
                rejection = f"{ve_id}: " + " or ".join(fail)
            break
    return success, rejection, deadline


def generate(assumption_id, now):
    m = ASM_RE.match(assumption_id)
    if not m:
        raise ValueError(f"assumption_id must look like ASM-OPP-nnn-<factor>, got {assumption_id}")
    opp, factor = m.group(1), m.group(2)
    model = tracker.build(opp, now)
    item = next((a for a in model["assumptions"] if a["assumption_id"] == assumption_id), None)
    if item is None:
        raise ValueError(f"{assumption_id} not found in {opp} assumption register")

    cat = item["category"]
    success, rejection, deadline = _thresholds(item)
    current = {
        "status": item["status"],
        "supporting_ev": item["supporting_ev"],
        "contradicting_ev": item["contradicting_ev"],
        "evidence_confidence": item["evidence_confidence"]["derived"],
    }
    why = (f"{item['decision_importance']} to {opp}; currently {item['status']}; "
           f"{'materially bounded by the >6-assumption classification cap' if model['score']['capped'] else 'affects the composite'}.")

    return {
        "meta": genmeta.build_meta("research-request", [tracker.scorecard_path(opp)], now),
        "request_id": f"REQ-{opp}-{factor}",
        "status": "draft",
        "opportunity_id": opp,
        "assumption_id": assumption_id,
        "question": gaps.QUESTION.get(cat, "Is this assumption evidenced?").format(opp=opp),
        "why_it_matters": why,
        "current_evidence": current,
        "required_evidence": REQUIRED_EVIDENCE.get(cat, "Behavioural evidence for this assumption."),
        "preferred_sources": PREFERRED_SOURCES.get(cat, ["merchant interviews"]),
        "success_threshold": success,
        "rejection_threshold": rejection,
        "deadline_or_review_point": deadline,
        "note": "Proposed request (draft) — does not enter Part A's backlog until explicitly reviewed/approved.",
    }
