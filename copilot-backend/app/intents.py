"""Deterministic product-discovery intent classification.

Ordered pattern rules select the intent and the initial tool plan. The model
may request additional allowlisted tools afterwards, within the iteration cap.
"""

import re

INTENTS = ("portfolio_summary", "opportunity_explanation", "opportunity_comparison",
           "segment_analysis", "evidence_support", "contradictory_evidence",
           "assumption_analysis", "evidence_gap", "research_recommendation",
           "challenge_hypothesis", "change_summary", "executive_brief",
           "validation_planning", "unknown_or_unsupported")

OPP_REF = re.compile(r"\bOPP-\d{3}\b", re.I)
EV_REF = re.compile(r"\bEV-\d{4}-W\d{2}-\d{3}\b", re.I)
SEG_REF = re.compile(r"\bSEG-[a-z0-9-]+\b", re.I)
ASM_REF = re.compile(r"\bASM-OPP-\d{3}-[a-z0-9_]+\b", re.I)

_CODE_WORDS = re.compile(
    r"\b(source code|python module|repositor(y|ies)|file path|json structure|parser|"
    r"stack trace|git |commit|pull request|refactor|function name|implementation detail)\b", re.I)

_RULES = [
    ("executive_brief", re.compile(r"\b(brief|two.minute|2.minute|executive summary|tell arihant|for arihant|management summary)\b", re.I)),
    ("change_summary", re.compile(r"\b(what changed|recent(ly)? chang|latest updates?|what'?s new|change summary)\b", re.I)),
    ("opportunity_comparison", re.compile(r"\b(compare|versus|vs\.?|stronger|strongest|which .*opportunit)\b", re.I)),
    ("challenge_hypothesis", re.compile(r"\b(challenge|should (botim|we) build|devil'?s advocate|poke holes|steelman|stress.test|why might .*fail|reject this)\b", re.I)),
    ("contradictory_evidence", re.compile(r"\b(contradict|against (this|the)|weakens?|counter.evidence|negative signal)\b", re.I)),
    ("evidence_gap", re.compile(r"\b(evidence gaps?|unanswered|unknowns?|what.s missing|no supporting evidence)\b", re.I)),
    ("research_recommendation", re.compile(r"\b(research next|should .*research|next research|research request|validate next|what should part a)\b", re.I)),
    ("assumption_analysis", re.compile(r"\b(assumption|unproven|capped|unvalidated|what remains assumed)\b", re.I)),
    ("evidence_support", re.compile(r"\b(evidence (support|for)|what supports|willingness to pay|what do .*use instead|workaround)\b", re.I)),
    ("validation_planning", re.compile(r"\b(validation (plan|experiment)|how (do|would) we validate|ve-\d{3})\b", re.I)),
    ("segment_analysis", re.compile(r"\b(segment|importers?|merchants?|customers? (are|is)|who is the customer|which segment)\b", re.I)),
    ("portfolio_summary", re.compile(r"\b(portfolio|all opportunit|list opportunit|overview|strongest right now)\b", re.I)),
    ("opportunity_explanation", re.compile(r"\b(explain|what is|why is|tell me about|in simple terms|risks?)\b", re.I)),
]


def extract_ids(text):
    return {"opportunities": [m.upper() for m in OPP_REF.findall(text)],
            "evidence": [m.upper() for m in EV_REF.findall(text)],
            "segments": [m if m.startswith("SEG-") else m.lower() for m in SEG_REF.findall(text)],
            "assumptions": ASM_REF.findall(text)}


def is_out_of_scope(text):
    return bool(_CODE_WORDS.search(text))


def classify(text, ids):
    for intent, pattern in _RULES.items() if isinstance(_RULES, dict) else _RULES:
        if pattern.search(text):
            return intent
    if ids["opportunities"] or ids["evidence"] or ids["segments"]:
        return "opportunity_explanation"
    return "unknown_or_unsupported"


def tool_plan(intent, ids, message):
    """The bounded initial tool plan per intent. Returns [(tool, args), …]."""
    opp = ids["opportunities"][0] if ids["opportunities"] else None
    plan = []
    if intent == "portfolio_summary":
        plan.append(("list_opportunities", {}))
    elif intent == "opportunity_comparison":
        if len(ids["opportunities"]) >= 2:
            plan.append(("compare_opportunities", {"opp_a": ids["opportunities"][0],
                                                   "opp_b": ids["opportunities"][1]}))
        else:
            plan.append(("list_opportunities", {}))
    elif intent in ("opportunity_explanation", "assumption_analysis"):
        if opp:
            plan += [("get_opportunity", {"opp_id": opp}),
                     ("get_assumption_register", {"opp_id": opp})]
        else:
            plan.append(("list_opportunities", {}))
    elif intent == "segment_analysis":
        if ids["segments"]:
            plan.append(("get_segment", {"seg_id": ids["segments"][0]}))
        if opp:
            plan.append(("get_opportunity", {"opp_id": opp}))
        if not plan:
            plan.append(("search_product_knowledge", {"query": message[:200]}))
    elif intent in ("evidence_support", "contradictory_evidence"):
        if opp:
            plan.append(("get_opportunity", {"opp_id": opp}))
        for ev in ids["evidence"][:3]:
            plan.append(("get_evidence_record", {"ev_id": ev}))
        plan.append(("search_product_knowledge", {"query": message[:200]}))
        if intent == "contradictory_evidence" and opp:
            plan.append(("get_assumption_register", {"opp_id": opp}))
    elif intent in ("evidence_gap", "research_recommendation"):
        plan.append(("get_evidence_gaps", {}))
        if opp:
            plan.append(("get_opportunity_assumptions", {"opp_id": opp}))
    elif intent == "challenge_hypothesis":
        if opp:
            plan += [("get_opportunity", {"opp_id": opp}),
                     ("get_assumption_register", {"opp_id": opp})]
        plan += [("search_product_knowledge", {"query": message[:200]}),
                 ("get_evidence_gaps", {})]
    elif intent == "change_summary":
        plan.append(("get_recent_changes", {}))
        if opp:
            plan.append(("get_score_history", {"opp_id": opp}))
    elif intent == "executive_brief":
        if opp:
            plan.append(("get_executive_brief", {"opp_id": opp}))
        else:
            plan.append(("list_opportunities", {}))
    elif intent == "validation_planning":
        if opp:
            plan.append(("get_opportunity", {"opp_id": opp}))
        plan.append(("search_product_knowledge", {"query": message[:200]}))
    return plan[:6]


ANSWER_TYPE = {
    "portfolio_summary": "analysis", "opportunity_explanation": "analysis",
    "opportunity_comparison": "comparison", "segment_analysis": "analysis",
    "evidence_support": "evidence", "contradictory_evidence": "evidence",
    "assumption_analysis": "assumptions", "evidence_gap": "research_recommendation",
    "research_recommendation": "research_recommendation",
    "challenge_hypothesis": "challenge", "change_summary": "change_summary",
    "executive_brief": "brief", "validation_planning": "research_recommendation",
    "unknown_or_unsupported": "analysis",
}
