"""Evidence Traceability — every record with role/strength; weak visually distinct."""

from . import layout as L


def _row(r):
    weak_cls = " weak" if r.weak else ""
    unresolved = "" if r.resolved else ' <span class="badge ev-excluded">unresolved</span>'
    return f"""<tr id="{L.esc(r.ev_id)}" class="evrow{weak_cls}">
  <td class="evid">{L.esc(r.ev_id)}{unresolved}</td>
  <td>{L.esc(r.segment)}</td>
  <td>{L.esc(r.evidence_class)}</td>
  <td class="num">{L.esc(r.strength)}</td>
  <td>{L.confidence_badge(r.confidence)}</td>
  <td>{L.esc(r.status)}</td>
  <td>{L.evidence_role_badge(r)}</td>
</tr>"""


def render(model):
    if not model.evidence:
        body = L.empty_state("No evidence records found. Until Workstream A lands records, "
                             "all scorecard factors are assumptions.")
        return L.page("Evidence Traceability", "evidence.html", body, model.generated_note)
    strong = [r for r in model.evidence if not r.weak]
    weak = [r for r in model.evidence if r.weak]
    intro = ('<p class="lede">Follow any record from its ID to the factor and opportunity it supports. '
             '<strong>Weak evidence (strength &lt;3 or needs-more-evidence) is a lead, not a finding</strong> '
             'and is shown separately below — it does not drive scores.</p>')
    head = ('<thead><tr><th>EV ID</th><th>Segment</th><th>Class</th><th>Strength</th>'
            '<th>Confidence</th><th>Status</th><th>Role in scoring</th></tr></thead>')
    strong_tbl = f'<table class="evidence">{head}<tbody>{"".join(_row(r) for r in strong)}</tbody></table>'
    weak_tbl = (f'<h2>Weak evidence — leads, not findings ({len(weak)})</h2>'
                f'<table class="evidence weak-table">{head}<tbody>{"".join(_row(r) for r in weak)}</tbody></table>') if weak else ""
    body = f"""{intro}
<h2>Score-driving evidence ({len(strong)})</h2>{strong_tbl}
{weak_tbl}
<p class="muted">Traceability chain: evidence record → customer segment → affected factor (see each opportunity's
17-factor table) → opportunity score → monitoring alert (see Intelligence Feed).</p>"""
    return L.page("Evidence Traceability", "evidence.html", body, model.generated_note)
