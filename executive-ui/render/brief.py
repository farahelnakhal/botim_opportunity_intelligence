"""Executive Brief — consumes recommendation docs; does NOT reinterpret them.

Renders the brief output produced by the recommendation/meeting-ready feature.
Where no brief exists for an opportunity, shows an honest empty state rather
than generating reasoning here."""

import re

from . import layout as L


def _mini_md(text):
    """Minimal, safe markdown → HTML: escape first, then headings/bold/lists.
    Deliberately small — it presents the brief, it does not reinterpret it."""
    out, in_list = [], False
    for raw in text.splitlines():
        line = L.esc(raw.rstrip())
        if re.match(r"^#{1,6}\s", raw):
            if in_list:
                out.append("</ul>"); in_list = False
            level = len(raw) - len(raw.lstrip("#"))
            out.append(f"<h{min(level+1,4)}>{line.lstrip('# ').strip()}</h{min(level+1,4)}>")
        elif re.match(r"^\s*[-*]\s", raw):
            if not in_list:
                out.append("<ul>"); in_list = True
            item = re.sub(r"^\s*[-*]\s", "", line)
            out.append("<li>" + item + "</li>")
        elif not raw.strip():
            if in_list:
                out.append("</ul>"); in_list = False
        else:
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<p>{line}</p>")
    if in_list:
        out.append("</ul>")
    html = "\n".join(out)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    return html


def render(model):
    have = [b for b in model.briefs if b.exists]
    opp_names = {o.id: o.name for o in model.opportunities + model.archived}
    intro = ('<p class="lede">Executive briefs are consumed from the recommendation feature — this view '
             'does not re-derive them. Each brief states a decision requested; none asserts that a product '
             'has been validated or selected.</p>')
    if not have:
        missing = ", ".join(sorted(b.opportunity_id for b in model.briefs)) or "—"
        body = intro + L.empty_state(
            "No executive brief has been generated for any opportunity yet. "
            f"Opportunities awaiting a brief: {L.esc(missing)}. "
            "A brief is produced by the recommendation/meeting-ready feature, not by this UI.")
        return L.page("Executive Brief", "briefs.html", body, model.generated_note)
    sections = [intro]
    # index of which have / lack briefs (honest coverage)
    lack = [b.opportunity_id for b in model.briefs if not b.exists]
    sections.append('<div class="brief-index"><strong>Briefs available:</strong> '
                    + ", ".join(L.esc(b.opportunity_id) for b in have)
                    + (f' · <span class="muted">awaiting a brief: {L.esc(", ".join(lack))}</span>' if lack else "")
                    + "</div>")
    for b in have:
        name = opp_names.get(b.opportunity_id, b.opportunity_id)
        sections.append(f'<article class="brief"><h2>{L.esc(b.opportunity_id)} — {L.esc(name)}</h2>'
                        f'<p class="muted">Source: {L.esc(b.path)}</p>'
                        f'<div class="brief-body">{_mini_md(b.body)}</div></article>')
    return L.page("Executive Brief", "briefs.html", "\n".join(sections), model.generated_note)
