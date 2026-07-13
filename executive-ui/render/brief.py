"""Executive Brief — consumes the impact workflow's brief envelopes (real,
per opportunity) plus committed recommendation docs. Does NOT re-derive
reasoning: it renders `impact/uicontract.envelope(...)` output verbatim."""

import re

from . import layout as L


def _mini_md(text):
    """Minimal, safe markdown → HTML (escape first). Presents, doesn't reinterpret."""
    out, in_list = [], False
    for raw in text.splitlines():
        line = L.esc(raw.rstrip())
        if re.match(r"^#{1,6}\s", raw):
            if in_list:
                out.append("</ul>"); in_list = False
            level = min((len(raw) - len(raw.lstrip("#"))) + 1, 4)
            out.append(f"<h{level}>{line.lstrip('# ').strip()}</h{level}>")
        elif re.match(r"^\s*[-*]\s", raw):
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append("<li>" + re.sub(r"^\s*[-*]\s", "", line) + "</li>")
        elif not raw.strip():
            if in_list:
                out.append("</ul>"); in_list = False
        else:
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<p>{line}</p>")
    if in_list:
        out.append("</ul>")
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", "\n".join(out))


def _evidence_line(items):
    if not items:
        return '<span class="muted">none</span>'
    return " ".join(f'<a href="evidence.html#{L.esc(e)}">{L.esc(e)}</a>' for e in items)


def _envelope_brief(o):
    e = o.brief_envelope
    sc, ev = e["score"], e["evidence"]
    opp = e.get("opportunity", {}) or {}
    cust = opp.get("customer", {}) or {}
    weakest = [a for a in e["assumptions"].get("items", []) if a.get("status") != "supported"][:5]
    weak_html = "".join(
        f'<li>{L.esc(a.get("assumption_id"))} — {L.esc(a.get("status"))}'
        f' <span class="muted">(importance {L.esc(a.get("decision_importance", "—"))})</span></li>'
        for a in weakest) or "<li class=\"muted\">none listed</li>"
    dr = e.get("decision_requested", {}) or {}
    ra = e.get("recommended_action", {}) or {}
    return f"""<article class="brief">
  <h2>{L.esc(opp.get('opportunity_id', o.id))} — {L.esc(opp.get('name', o.name))}</h2>
  <div class="badges">{L.status_badge(sc.get('classification'))}
     <span class="badge neutral">{L.esc(sc.get('raw_score'))} raw · composite {L.esc(sc.get('composite_score'))}</span>
     <span class="badge neutral">{sc.get('assumption_count')} assumptions{' · capped' if sc.get('capped') else ''}</span></div>
  <h3>Opportunity summary</h3>
  <p>Segment: {L.esc(cust.get('segment_title') or cust.get('segment_id') or '—')} ·
     Job: {L.esc(cust.get('job_to_be_done') or '—')}</p>
  <h3>What changed</h3>
  <p>{L.esc('; '.join(str(c) for c in e.get('recent_changes', [])) or 'No approved score changes recorded yet.')}</p>
  <h3>Strongest evidence</h3><p>{_evidence_line(ev.get('supporting_primary'))}</p>
  <h3>Weakest assumptions</h3><ul>{weak_html}</ul>
  <h3>Confidence</h3>
  <p>{L.confidence_badge((e.get('confidence', {}).get('opportunity_assessment', {}) or {}).get('value', '—'))}
     <span class="muted">— exposed as separate signals, never collapsed into one number</span></p>
  <h3>Recommendation</h3><p>{L.esc(ra.get('text', '—'))}</p>
  <h3>Decision requested</h3>
  <p><strong>{L.esc(dr.get('text', '—'))}</strong></p>
  <p class="muted">{L.esc(dr.get('no_build_decision', 'No product or build decision has been made.'))}</p>
  {('<p class="muted">Committed recommendation doc: ' + L.esc(o.rec_doc_path) + '</p>') if getattr(o, 'rec_doc_path', None) else ''}
</article>"""


def render(model):
    intro = ('<p class="lede">Executive briefs are consumed from the brief generator '
             '(<code>impact/uicontract.envelope</code> via <code>impact/brief.build_view</code>) — this '
             'view renders that output and does not re-derive it. Each brief states a decision requested; '
             'none asserts that a product has been validated or selected.</p>')
    with_env = [o for o in model.opportunities if o.brief_envelope]
    if with_env:
        body = [intro,
                '<div class="brief-index"><strong>Live briefs:</strong> '
                + ", ".join(L.esc(o.id) for o in with_env) + "</div>"]
        body += [_envelope_brief(o) for o in with_env]
        return L.page("Executive Brief", "briefs.html", "\n".join(body), model.generated_note)

    # fallback: committed recommendation docs (impact workflow unavailable)
    have = [b for b in model.briefs if b.exists]
    if not have:
        return L.page("Executive Brief", "briefs.html",
                      intro + L.empty_state("No executive brief available yet. The brief generator "
                                            "(impact workflow) is not connected and no recommendation "
                                            "doc has been committed."), model.generated_note)
    names = {o.id: o.name for o in model.opportunities + model.archived}
    secs = [intro, '<div class="brief-index"><strong>Briefs available:</strong> '
            + ", ".join(L.esc(b.opportunity_id) for b in have) + "</div>"]
    for b in have:
        secs.append(f'<article class="brief"><h2>{L.esc(b.opportunity_id)} — '
                    f'{L.esc(names.get(b.opportunity_id, b.opportunity_id))}</h2>'
                    f'<p class="muted">Source: {L.esc(b.path)}</p>'
                    f'<div class="brief-body">{_mini_md(b.body)}</div></article>')
    return L.page("Executive Brief", "briefs.html", "\n".join(secs), model.generated_note)
