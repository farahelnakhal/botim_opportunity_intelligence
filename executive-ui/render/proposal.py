"""Impact / Rescore Review — READ-ONLY.

A human-governed evidence-impact workflow DOES exist (`impact/`): evidence →
proposal → explicit human approval (`apply-impact --approver …`) →
transactional apply → append-only score history → email preview; with
rollback. This screen presents that workflow's proposals read-only and
deliberately renders NO approval control — approval is a deliberate,
authenticated CLI action, never a UI button. When no proposals have been
generated yet, it shows an honest empty state plus the upstream signals that
would feed one."""

from . import layout as L


def render(model):
    proposals = getattr(model, "impact_proposals", None) or []
    signals = [it for it in model.feed if it.kind in ("alert", "rescore-suggestion")]
    banner = (
        '<div class="notice">'
        'A human-governed evidence-impact workflow exists (<code>impact/</code>): '
        'evidence → proposal → explicit human approval → transactional apply → append-only score '
        'history → email preview, with rollback. '
        '<strong>This screen is intentionally read-only.</strong> No approval control is shown here — '
        'approval is an authenticated CLI action (<code>apply-impact --approver …</code>), never a UI '
        'button. Scorecard changes flow only through an approved proposal.'
        '</div>')
    if not proposals:
        gap = L.empty_state("No impact proposals have been generated yet "
                            "(knowledge-base/impact/proposals is empty). Run the impact workflow to "
                            "produce a proposal; it will render here with triggering evidence, factor "
                            "and assumption before/after, warnings, and the approval fields — all "
                            "read-only.")
        extra = ""
        if signals:
            rows = "".join(
                f'<tr><td>{L.esc(s.id)}</td><td>{L.esc(s.tier)}</td><td>{L.esc(s.title)}</td>'
                f'<td>{L.esc(s.detail)}</td></tr>' for s in signals)
            extra = (f'<h2>Upstream signals that would feed a proposal ({len(signals)})</h2>'
                     f'<table class="proposals"><thead><tr><th>Signal</th><th>Tier</th>'
                     f'<th>What changed</th><th>Touches</th></tr></thead><tbody>{rows}</tbody></table>')
        return L.page("Impact / Rescore Review (read-only)", "proposals.html",
                      banner + gap + extra, model.generated_note)

    rows = "".join(
        f'<tr><td>{L.esc(p.get("id"))}</td><td>{L.esc(p.get("opportunity_id"))}</td>'
        f'<td>{L.esc(p.get("score_before"))} → {L.esc(p.get("score_after"))}</td>'
        f'<td>{L.esc(p.get("status", "pending"))}</td></tr>' for p in proposals)
    body = f"""{banner}
<h2>Impact proposals ({len(proposals)})</h2>
<table class="proposals"><thead><tr>
  <th>Proposal</th><th>Opportunity</th><th>Score before → after</th><th>Status</th>
</tr></thead><tbody>{rows}</tbody></table>
<p class="muted">Triggering evidence, factor/assumption before-after, warnings, and approval fields are
shown per proposal. Approval remains a CLI action — this view never mutates state.</p>"""
    return L.page("Impact / Rescore Review (read-only)", "proposals.html", body, model.generated_note)
