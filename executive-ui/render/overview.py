"""Executive Overview — ranked opportunity cards + archived rejects."""

from . import layout as L


def _score_line(o):
    if o.raw_score is None:
        return '<div class="score"><span class="raw">—</span> <span class="muted">no active scorecard</span></div>'
    return (f'<div class="score"><span class="raw">{o.raw_score}/{o.raw_max}</span>'
            f'<span class="muted"> raw · composite {o.composite} (indicative)</span></div>')


def _card(o):
    flags = ""
    if o.critical_flags:
        flags = '<div class="flags">⚠ ' + L.esc("; ".join(o.critical_flags)) + "</div>"
    return f"""<article class="opp-card" data-opp="{L.esc(o.id)}">
  <div class="card-head">
    <a class="opp-id" href="opportunity-{L.esc(o.id)}.html">{L.esc(o.id)}</a>
    <span class="opp-name">{L.esc(o.name)}</span>
  </div>
  {_score_line(o)}
  <div class="badges">{L.status_badge(o.classification)} {L.confidence_badge(o.confidence)}</div>
  <dl class="facts">
    <dt>Unresolved assumptions</dt><dd>{o.assumption_count}</dd>
    <dt>Latest change</dt><dd>{L.esc(o.latest_change)}</dd>
    <dt>Latest intelligence alert</dt><dd>{L.esc(o.latest_alert)}</dd>
    <dt>Next validation action</dt><dd class="next">{L.esc(o.next_action)}</dd>
  </dl>
  {flags}
  <a class="detail-link" href="opportunity-{L.esc(o.id)}.html">Full scorecard &amp; evidence →</a>
</article>"""


def render(model):
    if not model.opportunities and not model.archived:
        body = L.empty_state("No opportunities are recorded yet.")
        return L.page("Executive Overview", "index.html", body, model.generated_note)
    cards = "".join(_card(o) for o in model.opportunities)
    body = [
        '<p class="lede">Opportunities under investigation, ranked by raw evidence-weighted score. '
        'Every score is a hypothesis awaiting validation — none has been selected or built.</p>',
        f'<section class="opp-grid">{cards}</section>',
    ]
    if model.archived:
        arch = "".join(_card(o) for o in model.archived)
        body.append('<h2>Archived / rejected</h2>')
        body.append('<p class="muted">Kept visible so rejected ideas are not silently re-litigated.</p>')
        body.append(f'<section class="opp-grid archived">{arch}</section>')
    return L.page("Executive Overview", "index.html", "\n".join(body), model.generated_note)
