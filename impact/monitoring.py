"""Monitoring-summary renderer (transactional output).

Rendered in memory during preparation, staged, validated, backed up and
replaced in the same applying phase as the other targets.
"""


def render_markdown(proposal, segment_applied):
    p = proposal["payload"]
    s = p["score_summary"]
    lines = [
        f"# Monitoring summary — {s['opportunity_id']}",
        "",
        f"- Proposal: {proposal['proposal_id']}  ·  alert tier: **{s['alert_tier']}**",
        f"- Triggering evidence: {', '.join(p['trigger']['ev_ids'])} "
        f"(confidence {p['trigger']['ev_evidence_confidence']}, strength {p['trigger']['ev_evidence_strength']})",
        f"- Raw score: {s['raw_score_prev']}/{s['raw_max']} → **{s['raw_score_new']}/{s['raw_max']}**",
        f"- Composite (engine): {s['composite_prev']} → {s['composite_new']}",
        f"- Assumption count: {s['assumption_count_prev']} → **{s['assumption_count_new']}**",
        f"- Classification: {s['classification_prev']} → {s['classification_new']}",
        "",
        "## Factors changed",
    ]
    if p["factor_changes"]:
        for fc in p["factor_changes"]:
            lines.append(
                f"- {fc['factor']}: score {fc['old_score']}→{fc['proposed_score']}, "
                f"assumption {fc['old_assumption']}→{fc['proposed_assumption']} "
                f"({fc['change_type']}; {fc['ev_id']}/{fc['evidence_field']})")
    else:
        lines.append("- none")
    lines += ["", "## Segment"]
    if p["segment_changes"]:
        for sc in p["segment_changes"]:
            state = "APPLIED" if segment_applied else "NOT APPLIED (unconfirmed)"
            lines.append(f"- {sc['segment_id']} confidence {sc['old']}→{sc['proposed']} — {state}")
    else:
        lines.append("- no segment change")
    lines += ["", "## Factors left unchanged"]
    for u in p["unchanged"] or [{"factor": "(all others)", "reason": "no mapped evidence"}]:
        lines.append(f"- {u['factor']}: {u['reason']}")
    if p["unresolved_questions"]:
        lines += ["", "## Unresolved questions"]
        lines += [f"- {q}" for q in p["unresolved_questions"]]
    return "\n".join(lines) + "\n"
