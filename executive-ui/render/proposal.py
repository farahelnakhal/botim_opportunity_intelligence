"""Rescore-Suggestion Review — READ-ONLY.

The brief's "Impact Proposal Review" assumes an approve/reject/rollback
workflow. No such workflow exists in this system, so this screen is honest
about that: it shows the report-only signals that WOULD feed a rescore
review, and deliberately renders NO approval controls (a fake button that
doesn't call a real workflow is prohibited)."""

from . import layout as L


def render(model):
    # signals relevant to a rescore review = monitoring alerts touching opportunities
    signals = [it for it in model.feed if it.kind in ("alert", "rescore-suggestion")]
    banner = (
        '<div class="notice">'
        '<strong>No impact-proposal, approval, or rollback workflow exists in this system yet.</strong> '
        'This screen is intentionally read-only. No approval control is shown, because there is no '
        'secure backend workflow for it to call. The signals below are the closest existing analogue — '
        'monitoring alerts that would, in a future workflow, trigger a human rescore review of an '
        'opportunity. Any factor rescore is applied by a person editing the scorecard, then re-validated '
        'by the scoring engine — never from this UI.'
        '</div>')
    if not signals:
        body = banner + L.empty_state("No alert-level signals are currently pending review.")
        return L.page("Rescore Review (read-only)", "proposals.html", body, model.generated_note)
    rows = "".join(
        f'<tr><td>{L.esc(s.id)}</td><td>{L.esc(s.tier)}</td><td>{L.esc(s.title)}</td>'
        f'<td>{L.esc(s.detail)}</td><td class="muted">rescore suggested — apply via scorecard edit, '
        f'then re-run the scoring engine</td></tr>' for s in signals)
    body = f"""{banner}
<h2>Signals that would feed a rescore review ({len(signals)})</h2>
<table class="proposals"><thead><tr>
  <th>Signal</th><th>Tier</th><th>What changed</th><th>Touches</th><th>Required action (manual)</th>
</tr></thead><tbody>{rows}</tbody></table>
<p class="muted">Triggering evidence, factor/assumption before-after, warnings, and required approval fields
will render here once an impact-transaction workflow is built. Today those fields do not exist, so they
are not fabricated.</p>"""
    return L.page("Rescore Review (read-only)", "proposals.html", body, model.generated_note)
