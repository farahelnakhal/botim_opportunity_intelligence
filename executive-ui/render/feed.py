"""Intelligence Feed — typed events; before/after where it genuinely exists."""

from . import layout as L

KIND_LABEL = {
    "lead": "○ Informational lead",
    "alert": "◆ Monitoring alert",
    "rescore-suggestion": "◑ Rescore suggestion (report-only)",
    "prediction-resolved": "✓ Prediction resolved",
    "summary": "▤ Summary",
}


def _item(it):
    ba = ""
    if it.before_after:
        ba = (f'<div class="ba"><span class="before">before: {L.esc(it.before_after.get("before"))}</span>'
              f'<span class="arrow">→</span>'
              f'<span class="after">after: {L.esc(it.before_after.get("after"))}</span></div>')
    tier = f'<span class="badge tier tier-{L.esc(it.tier)}">{L.esc(it.tier)}</span>' if it.tier and it.tier != L.esc("—") else ""
    return f"""<li class="feed-item kind-{L.esc(it.kind)}">
  <div class="fi-head"><span class="fi-kind">{L.esc(KIND_LABEL.get(it.kind, it.kind))}</span>
    {tier}<span class="fi-date">{L.esc(it.detected_at)}</span><span class="fi-id">{L.esc(it.id)}</span></div>
  <div class="fi-title">{L.esc(it.title)}</div>
  <div class="fi-detail muted">{L.esc(it.detail)}</div>
  {ba}
</li>"""


def render(model):
    if not model.feed:
        body = L.empty_state("No monitoring events or resolved predictions yet. "
                             "Run the monitoring scan to populate the feed.")
        return L.page("Intelligence Feed", "feed.html", body, model.generated_note)
    note = ('<p class="lede">Change signals over the knowledge base and external sources. '
            'Types are distinguished by label, not colour alone. '
            'Approved score changes flow only through the human-governed evidence-impact workflow '
            '(<code>impact/</code>, approved on the CLI via <code>apply-impact --approver</code>); '
            'the items below are the upstream signals — informational leads, monitoring alerts, and '
            'report-only rescore suggestions — not approved impacts.</p>')
    items = "".join(_item(it) for it in model.feed)
    return L.page("Intelligence Feed", "feed.html", f'{note}<ul class="feed">{items}</ul>', model.generated_note)
