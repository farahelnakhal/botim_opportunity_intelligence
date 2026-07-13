"""Opportunity Detail — all 17 factors shown; never hidden behind a composite."""

from . import layout as L


def _factor_row(f):
    aflag = '<span class="aflag" title="assumption-based">(A)</span>' if f.assumption else '<span class="eflag" title="evidence-based">✓</span>'
    chips = " ".join(
        f'<a class="evchip" href="evidence.html#{L.esc(e)}">{L.esc(e)}</a>' for e in f.evidence_ids
    ) or '<span class="muted">no evidence cited</span>'
    kind = "assumption" if f.assumption else "fact"
    return (f'<tr class="factor {kind}"><td class="fkey">{L.esc(f.key)}</td>'
            f'<td class="fscore">{f.score}/5</td><td class="fflag">{aflag}</td>'
            f'<td class="fbasis">{L.esc(f.basis)}</td><td class="fchips">{chips}</td></tr>')


def _evidence_list(refs):
    if not refs:
        return L.empty_state("No primary (evidence-backed) records cited yet.")
    items = "".join(
        f'<li><a href="evidence.html#{L.esc(r.ev_id)}">{L.esc(r.ev_id)}</a> '
        f'— strength {L.esc(r.strength)}, {L.confidence_badge(r.confidence)} '
        f'<span class="muted">{L.esc(r.title)}</span></li>' for r in refs)
    return f'<ul class="ev-strong">{items}</ul>'


def _history(o):
    if not o.score_history:
        return L.empty_state("No prior score versions recorded (single snapshot). "
                             "History would derive from version control once the scorecard is re-scored.")
    rows = "".join(f'<li><span class="date">{L.esc(h["date"])}</span> {L.esc(h["subject"])}</li>'
                   for h in o.score_history)
    return f'<ul class="history">{rows}</ul>'


def render_one(o, model):
    if o.raw_score is None:  # archived reject, no scorecard
        body = f"""<div class="badges">{L.status_badge(o.classification)}</div>
<h2>Why it was rejected</h2><p>{L.esc(o.rejection_conditions)}</p>
<h2>Reopen condition</h2><p>{L.esc(o.next_action)}</p>
{L.empty_state("No active scorecard — this proposition is archived. Factor-level scoring does not apply.")}"""
        return L.page(f"{o.id} — {o.name}", "index.html", body, model.generated_note)

    factors = "".join(_factor_row(f) for f in o.factors)
    flags = ("<p class=\"flags\">⚠ Critical-dimension flags: " + L.esc("; ".join(o.critical_flags)) + "</p>") if o.critical_flags else ""
    body = f"""<div class="detail-head">
  <div class="score-big">{o.raw_score}<span>/{o.raw_max} raw</span></div>
  <div class="badges">{L.status_badge(o.classification)} {L.confidence_badge(o.confidence)}
    <span class="badge neutral">{o.assumption_count} unresolved assumptions</span></div>
</div>
<p class="muted">Composite {o.composite} shown for reference only — the 17 factors below are the real picture.</p>
{flags}

<section class="meta">
  <h2>Segment &amp; job</h2>
  <dl class="kv">
    <dt>Customer segment</dt><dd>{L.esc(o.segment)}</dd>
    <dt>Job-to-be-done</dt><dd>{L.esc(o.jtbd)}</dd>
    <dt>Next validation action</dt><dd class="next">{L.esc(o.next_action)}</dd>
  </dl>
  <h2>Product hypothesis</h2>
  <div class="prose">{L.esc(o.hypothesis)}</div>
</section>

<section><h2>All 17 scoring factors</h2>
<p class="muted">Score and assumption flag for every factor; evidence IDs link to the traceability view.</p>
<table class="factors"><thead><tr><th>Factor</th><th>Score</th><th>Basis</th><th>Rationale</th><th>Evidence</th></tr></thead>
<tbody>{factors}</tbody></table></section>

<section><h2>Strongest supporting evidence</h2>{_evidence_list(o.strongest_evidence)}</section>
<section><h2>Contradictory / disconfirming evidence</h2><div class="prose">{L.esc(o.contradictory_evidence)}</div></section>
<section><h2>Rejection conditions</h2><div class="prose">{L.esc(o.rejection_conditions)}</div></section>
<section><h2>Seven-week MVP / validation plan</h2><div class="prose">{L.esc(o.validation_plan)}</div>
  <p class="muted">Full profile: {L.esc(o.profile_path)}</p></section>
<section><h2>Score history</h2>{_history(o)}</section>
"""
    return L.page(f"{o.id} — {o.name}", "index.html", body, model.generated_note)


def render_all(model):
    """Returns {filename: html} for every opportunity + archived reject."""
    out = {}
    for o in model.opportunities + model.archived:
        out[f"opportunity-{o.id}.html"] = render_one(o, model)
    return out
