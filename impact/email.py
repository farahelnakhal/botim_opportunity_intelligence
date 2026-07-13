"""Executive email/digest preview renderer.

Preview ONLY — there is no send capability anywhere in this module, so no real
email can be sent (including during tests). The renderer refuses affirmative
overclaims and requires an explicit bounded statement when the evidence does
not justify a decision.
"""

from .errors import ImpactError

# Affirmative overclaims that must never appear in a preview.
OVERCLAIMS = (
    "product validated",
    "opportunity validated",
    "product selected",
    "ready to launch",
    "launch approved",
    "build approved",
)

BOUNDED_STATEMENTS = (
    "This remains unvalidated.",
    "No product or build decision has been made.",
)


def _guard(text, require_bounded):
    low = text.lower()
    for phrase in OVERCLAIMS:
        if phrase in low:
            raise ImpactError(f"email overclaim rejected: '{phrase}'")
    if require_bounded and not any(b in text for b in BOUNDED_STATEMENTS):
        raise ImpactError(
            "email must include an explicit bounded statement "
            f"(one of: {BOUNDED_STATEMENTS})")
    return text


def render(proposal, segment_applied):
    p = proposal["payload"]
    s = p["score_summary"]
    classification_changed = s["classification_prev"] != s["classification_new"]
    confidence = (proposal["payload"]["trigger"]["ev_evidence_confidence"] or "").lower()
    require_bounded = (not classification_changed) or confidence != "high"

    changed = ", ".join(
        f"{fc['factor']} {fc['old_score']}→{fc['proposed_score']}"
        + ("/de-assumed" if fc["old_assumption"] and not fc["proposed_assumption"] else "")
        for fc in p["factor_changes"]) or "none"
    unchanged = ", ".join(u["factor"] for u in p["unchanged"]) or "—"
    seg = "no change"
    if p["segment_changes"]:
        sc = p["segment_changes"][0]
        seg = (f"{sc['segment_id']} {sc['old']}→{sc['proposed']} "
               + ("(applied)" if segment_applied else "(NOT applied — needs human confirmation)"))

    lines = [
        f"# Evidence-impact digest — {s['opportunity_id']}",
        "",
        f"**What changed:** {changed}",
        f"**Affected:** opportunity {s['opportunity_id']}; segment: {seg}",
        f"**Score:** {s['raw_score_prev']}/{s['raw_max']} → {s['raw_score_new']}/{s['raw_max']} "
        f"(engine composite {s['composite_prev']} → {s['composite_new']})",
        f"**Assumptions:** {s['assumption_count_prev']} → {s['assumption_count_new']}",
        f"**Confidence (triggering evidence):** {confidence or 'n/a'}",
        f"**Factors changed:** {changed}",
        f"**Factors unchanged:** {unchanged}",
        f"**Alert tier:** {s['alert_tier']}",
        "",
        "**Why it matters:** an approved evidence change adjusted the scorecard "
        "within existing anchors and caps; classification "
        + ("changed" if classification_changed else "did not change") + ".",
        "**What remains unknown:** "
        + ("; ".join(p["unresolved_questions"]) if p["unresolved_questions"] else "see assumption register"),
        "**Next recommended action:** review the updated assumption register and "
        "run the next validation experiment before any decision.",
        "",
        "No product or build decision has been made. This remains unvalidated.",
    ]
    return _guard("\n".join(lines) + "\n", require_bounded)
