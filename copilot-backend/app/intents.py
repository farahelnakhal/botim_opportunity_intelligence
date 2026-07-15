"""Deterministic product-discovery intent classification.

Ordered pattern rules select the intent and the initial tool plan. The model
may request additional allowlisted tools afterwards, within the iteration cap.
"""

import re

INTENTS = ("portfolio_summary", "opportunity_explanation", "opportunity_comparison",
           "segment_analysis", "evidence_support", "contradictory_evidence",
           "assumption_analysis", "evidence_gap", "research_recommendation",
           "challenge_hypothesis", "change_summary", "executive_brief",
           "validation_planning",
           # Merchant Voice (Phase 5) — read-only, approved+published findings only.
           "merchant_feedback", "campaign_summary", "segment_feedback",
           "merchant_objections", "merchant_workarounds", "concept_reactions",
           "merchant_wtp_signals", "merchant_contradictions",
           # Integration Phase 2 — a genuinely new product/opportunity that has
           # no OPP record yet. Never fabricates repository evidence; never
           # persists anything (see grounding.py + system_prompt.py).
           "new_opportunity_analysis",
           # Phase 3 — deterministic, non-product-analysis fallbacks so a
           # greeting or a methodology question is never mistaken for a new
           # product idea (see classify()).
           "clarification_needed", "general_explanation",
           "unknown_or_unsupported")

OPP_REF = re.compile(r"\bOPP-\d{3}\b", re.I)
EV_REF = re.compile(r"\bEV-\d{4}-W\d{2}-\d{3}\b", re.I)
SEG_REF = re.compile(r"\bSEG-[a-z0-9-]+\b", re.I)
ASM_REF = re.compile(r"\bASM-OPP-\d{3}-[a-z0-9_]+\b", re.I)
MVC_REF = re.compile(r"\bMVC-[A-Za-z0-9-]+\b", re.I)

_CODE_WORDS = re.compile(
    r"\b(source code|python module|repositor(y|ies)|file path|json structure|parser|"
    r"stack trace|git |commit|pull request|refactor|function name|implementation detail)\b", re.I)

# Phase 3 — a message that is ONLY a greeting/help word (no other content) gets
# a deterministic clarification, never a new-product analysis or a fabricated
# opportunity. Anchored to the whole (trimmed) message so "Hi, I have an idea
# for..." is untouched — only a bare greeting matches.
_GREETING_ONLY = re.compile(
    r"^\s*(hi|hello|hey|hiya|yo|sup|howdy|help|hi there|hello there|good (morning|afternoon|evening))\s*[!.?]*\s*$",
    re.I)

# Phase 3 — questions about how the app itself scores/classifies opportunities
# are a methodology explanation, not a new-product analysis.
_METHODOLOGY = re.compile(
    r"\b(how (does|do|is|are) .*(scor(e|ing|ed)|classif|calculat|comput)|"
    r"scoring (method|methodology|framework|works?)|"
    r"(explain|what is) the (scoring|methodology|framework)|"
    r"how (does|do) (this|the) (app|system|tool|copilot|engine) work)\b", re.I)

# Phase 3 — positive evidence that the user is proposing/evaluating a
# genuinely new product, feature, customer problem, or build concept — used
# ONLY to let a new-product idea win over a generic keyword collision (e.g.
# "build a card for merchants" would otherwise be swallowed by the bare
# "merchants?" match in segment_analysis below). Never fires unless the
# conversation is new and no opportunity/segment is already selected.
_NEW_PRODUCT_SIGNAL = re.compile(
    r"\b(i have an idea|(a )?new (product |feature |market )?idea|product idea|"
    r"(should|could|can|let'?s) (botim|we)? ?(build|create|launch|design|develop)|"
    r"(build|create|design|develop) (a|an) |"
    r"(analyz|evaluat|assess|review)(e|ing) (a|an|this) (product|feature|opportunity|concept|idea|marketplace)|"
    r"(a|an) (product|feature|concept)( idea)? (that|which|to) |"
    r"want to (build|test|launch|create|develop|try|pitch)|"
    r"propose (a|an)|pitch (a|an|for)|concept for (a|an)?)\b", re.I)

_RULES = [
    ("executive_brief", re.compile(r"\b(brief|two.minute|2.minute|executive summary|tell arihant|for arihant|management summary)\b", re.I)),
    ("general_explanation", _METHODOLOGY),
    ("change_summary", re.compile(
        r"\b(what changed|recent(ly)? chang|latest updates?|what'?s new|change summary|"
        r"monitoring update|show .*monitoring|recent (developments?|updates?)|monitoring status)\b", re.I)),
    ("opportunity_comparison", re.compile(r"\b(compare|versus|vs\.?|stronger|strongest|which .*opportunit)\b", re.I)),
    ("challenge_hypothesis", re.compile(r"\b(challenge|should (botim|we) build|devil'?s advocate|poke holes|steelman|stress.test|why might .*fail|reject this)\b", re.I)),
    # Merchant Voice (Phase 5) — deliberately scoped to explicit merchant-
    # research phrasing (the word "merchant", an MVC- campaign reference, or
    # distinctive research-only vocabulary like "concept reaction") so
    # generic Part A phrasing ("what evidence supports willingness to pay",
    # "what evidence contradicts OPP-013") keeps routing to the existing
    # evidence_support/contradictory_evidence intents unchanged.
    ("campaign_summary", re.compile(r"\b(mvc-[a-z0-9-]+|campaign summary|what did we learn from)\b", re.I)),
    ("concept_reactions", re.compile(r"\bconcept (reaction|test)s?\b", re.I)),
    ("merchant_contradictions", re.compile(
        r"\bmerchants?[^.?!]{0,30}(disagree|contradict)|contradicting merchant|conflicting merchant\b", re.I)),
    ("merchant_wtp_signals", re.compile(
        r"\bmerchants?[^.?!]{0,30}(willing(ness)? to pay|would pay|wtp)|"
        r"(willing(ness)? to pay|wtp)[^.?!]{0,30}merchants?\b", re.I)),
    ("merchant_objections", re.compile(
        r"\bmerchants?[^.?!]{0,30}object|objections?[^.?!]{0,30}merchants?\b", re.I)),
    ("merchant_workarounds", re.compile(
        r"\bmerchants?[^.?!]{0,30}workaround|workarounds?[^.?!]{0,30}merchants?\b", re.I)),
    ("segment_feedback", re.compile(
        r"\bmerchant segment|which (merchant )?segment[^.?!]{0,30}(report|feedback|say)|"
        r"segment[^.?!]{0,30}merchants?[^.?!]{0,10}(report|say)\b", re.I)),
    ("merchant_feedback", re.compile(
        r"\bmerchants? (are )?saying|merchant feedback|supplier.payment (delay|problem|pain)|"
        r"survey (and|vs\.?) interview findings?|survey vs\.? interview\b", re.I)),
    ("contradictory_evidence", re.compile(r"\b(contradict|against (this|the)|weakens?|counter.evidence|negative signal)\b", re.I)),
    ("evidence_gap", re.compile(r"\b(evidence gaps?|unanswered|unknowns?|what.s missing|no supporting evidence)\b", re.I)),
    ("research_recommendation", re.compile(r"\b(research next|should .*research|next research|research request|validate next|what should part a)\b", re.I)),
    ("assumption_analysis", re.compile(r"\b(assumptions?|unproven|capped|unvalidated|what remains assumed)\b", re.I)),
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
            "assumptions": ASM_REF.findall(text),
            # not case-normalized: unlike OPP-/EV- ids, campaign ids carry a
            # lowercase-hex suffix (MVC-4f0cfb3ad4) — preserve exactly as typed
            "campaigns": MVC_REF.findall(text)}


def is_out_of_scope(text):
    return bool(_CODE_WORDS.search(text))


# Deterministic, provider-independent reply for clarification_needed — a bare
# greeting has no product-discovery content to ground an answer in, so the
# response is fixed rather than left to (or overridable by) the model.
CLARIFICATION = (
    "Tell me whether you want to explore a new product idea, review an existing opportunity, "
    "inspect monitoring updates, or examine merchant feedback."
)


# Rules that are broad, generic keyword catch-alls (e.g. segment_analysis's
# bare "merchants?") and can otherwise swallow a genuine new-product message
# that happens to mention one of their trigger words. The positive
# new-product signal is checked immediately before these specific two, so a
# strong signal wins; everything else in _RULES (brief, comparisons,
# challenge, all Merchant Voice intents, evidence/assumption/validation
# intents, portfolio_summary) keeps first-priority as before.
_GENERIC_CATCHALLS = {"segment_analysis", "opportunity_explanation"}


def classify(text, ids, is_new_conversation=False, has_selected_context=False):
    """Deterministic mode detection.

    `is_new_conversation` / `has_selected_context` let a genuinely new product
    idea (first message, no conversation history, no explicit/selected record)
    route to `new_opportunity_analysis` instead of falling through to
    `unknown_or_unsupported` and being treated as a bare LLM prompt. Any
    explicit OPP/EV/SEG/ASM/MVC id, or an existing selected opportunity
    (frontend `context.opportunity_id`), or a message matching one of the
    deterministic rules above, always takes priority — new_opportunity_analysis
    requires POSITIVE evidence of a product idea, not just an unmatched
    message (see _NEW_PRODUCT_SIGNAL).
    """
    is_new_product_candidate = (
        is_new_conversation and not has_selected_context
        and not (ids["opportunities"] or ids["evidence"] or ids["segments"] or ids.get("assumptions") or ids.get("campaigns"))
        and bool(text.strip())
    )
    # A bare greeting/help word is never a product idea and never a rule match
    # away from being treated as one — check before anything else.
    if is_new_product_candidate and _GREETING_ONLY.search(text):
        return "clarification_needed"

    for intent, pattern in _RULES:
        if (intent in _GENERIC_CATCHALLS and is_new_product_candidate
                and _NEW_PRODUCT_SIGNAL.search(text)):
            return "new_opportunity_analysis"
        if pattern.search(text):
            return intent
    if ids["opportunities"] or ids["evidence"] or ids["segments"]:
        return "opportunity_explanation"
    if ids.get("campaigns"):
        return "campaign_summary"
    if is_new_product_candidate:
        return "new_opportunity_analysis"
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

    # --- Merchant Voice (Phase 5) — read-only, approved+published only ------
    elif intent == "campaign_summary":
        camp = ids["campaigns"][0] if ids["campaigns"] else None
        if camp:
            plan.append(("get_campaign_summary", {"campaign_id": camp}))
        else:
            plan.append(("list_merchant_campaigns", {}))
    elif intent == "segment_feedback":
        if len(ids["segments"]) >= 2 and ids["campaigns"]:
            plan.append(("compare_segment_feedback", {"campaign_id": ids["campaigns"][0],
                                                       "segment_a": ids["segments"][0],
                                                       "segment_b": ids["segments"][1]}))
        elif ids["segments"]:
            plan.append(("get_segment_feedback", {"segment_id": ids["segments"][0]}))
        else:
            plan.append(("list_merchant_campaigns", {}))
    elif intent == "merchant_objections":
        camp = ids["campaigns"][0] if ids["campaigns"] else None
        plan.append(("get_merchant_objections", {"campaign_id": camp} if camp else {}))
    elif intent == "merchant_workarounds":
        camp = ids["campaigns"][0] if ids["campaigns"] else None
        plan.append(("get_merchant_workarounds", {"campaign_id": camp} if camp else {}))
    elif intent == "concept_reactions":
        camp = ids["campaigns"][0] if ids["campaigns"] else None
        args = {"finding_type": "concept_reaction"}
        if camp:
            args["campaign_id"] = camp
        plan.append(("get_approved_merchant_findings", args))
    elif intent == "merchant_wtp_signals":
        camp = ids["campaigns"][0] if ids["campaigns"] else None
        args = {"finding_type": "willingness_to_pay_signal"}
        if camp:
            args["campaign_id"] = camp
        plan.append(("get_approved_merchant_findings", args))
    elif intent == "merchant_contradictions":
        camp = ids["campaigns"][0] if ids["campaigns"] else None
        args = {"finding_type": "contradiction"}
        if camp:
            args["campaign_id"] = camp
        plan.append(("get_approved_merchant_findings", args))
        if opp:
            plan.append(("get_opportunity_merchant_feedback", {"opportunity_id": opp}))
    elif intent == "merchant_feedback":
        camp = ids["campaigns"][0] if ids["campaigns"] else None
        if camp:
            plan.append(("get_campaign_summary", {"campaign_id": camp}))
        elif opp:
            plan.append(("get_opportunity_merchant_feedback", {"opportunity_id": opp}))
        elif ids["segments"]:
            plan.append(("get_segment_feedback", {"segment_id": ids["segments"][0]}))
        else:
            plan.append(("list_merchant_campaigns", {}))

    if intent == "contradictory_evidence" and opp:
        plan.append(("get_opportunity_merchant_feedback", {"opportunity_id": opp}))

    # --- new_opportunity_analysis (Phase 2) -------------------------------- #
    # No OPP record exists yet, so there is nothing to look up by id — instead
    # search everything the repository already knows (evidence, opportunities,
    # segments, experiments, competitors, inflection points via the bounded
    # keyword search), surface portfolio-wide evidence gaps and monitoring
    # signals for context, and check for any approved Merchant Voice findings
    # that already speak to this space. Every tool here is read-only and
    # already used elsewhere; nothing new is written or scored.
    elif intent == "new_opportunity_analysis":
        plan.append(("search_product_knowledge", {"query": message[:200]}))
        plan.append(("get_evidence_gaps", {}))
        plan.append(("get_recent_changes", {}))
        plan.append(("get_approved_merchant_findings", {}))

    # --- clarification_needed / general_explanation (Phase 3) -------------- #
    # Neither needs a tool: a bare greeting has nothing to look up, and the
    # scoring methodology is a fixed fact about how this system itself works
    # (added as a deterministic fact in grounding.py), not a repository query.

    return plan[:6]


ANSWER_TYPE = {
    "portfolio_summary": "analysis", "opportunity_explanation": "analysis",
    "opportunity_comparison": "comparison", "segment_analysis": "analysis",
    "evidence_support": "evidence", "contradictory_evidence": "evidence",
    "assumption_analysis": "assumptions", "evidence_gap": "research_recommendation",
    "research_recommendation": "research_recommendation",
    "challenge_hypothesis": "challenge", "change_summary": "change_summary",
    "executive_brief": "brief", "validation_planning": "research_recommendation",
    "merchant_feedback": "merchant_feedback", "campaign_summary": "merchant_feedback",
    "segment_feedback": "merchant_feedback", "merchant_objections": "merchant_feedback",
    "merchant_workarounds": "merchant_feedback", "concept_reactions": "merchant_feedback",
    "merchant_wtp_signals": "merchant_feedback", "merchant_contradictions": "merchant_feedback",
    "new_opportunity_analysis": "new_opportunity_analysis",
    "clarification_needed": "clarification", "general_explanation": "analysis",
    "unknown_or_unsupported": "analysis",
}
