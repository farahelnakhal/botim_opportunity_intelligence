"""Assumptions & Evidence Gaps — filterable (client-side show/hide only)."""

from . import layout as L


def _row(a):
    ev = " ".join(f'<a href="evidence.html#{L.esc(e)}">{L.esc(e)}</a>' for e in a.evidence_ids) or '<span class="muted">none</span>'
    return f"""<tr class="arow" data-opp="{L.esc(a.opportunity_id)}" data-status="{L.esc(a.status)}">
  <td>{L.esc(a.opportunity_id)}</td>
  <td class="fkey">{L.esc(a.factor_key)}</td>
  <td>{L.assumption_badge(a.status)}</td>
  <td class="abasis">{L.esc(a.text)}</td>
  <td>{ev}</td>
  <td>{L.esc(a.validation_method)}</td>
  <td>{L.esc(a.sensitivity)}</td>
  <td>{L.esc(a.owner)}</td>
</tr>"""


def render(model):
    if not model.assumptions:
        body = L.empty_state("No assumptions recorded — every factor is evidence-backed. (Unlikely at this stage.)")
        return L.page("Assumptions & Evidence Gaps", "assumptions.html", body, model.generated_note)
    opps = sorted({a.opportunity_id for a in model.assumptions})
    opp_opts = "".join(f'<option value="{L.esc(o)}">{L.esc(o)}</option>' for o in opps)
    counts = {}
    for a in model.assumptions:
        counts[a.status] = counts.get(a.status, 0) + 1
    summary = " · ".join(f"{L.ASSUMPTION_STATUS_GLYPH.get(k, k)}: {v}" for k, v in sorted(counts.items()))
    rows = "".join(_row(a) for a in model.assumptions)
    body = f"""<p class="lede">Unproven assumptions behind every score. Filter to see what a given
opportunity still needs, and what would validate it. <span class="muted">{summary}</span></p>
<div class="filters" data-note="client-side show/hide only — no recomputation">
  <label>Opportunity
    <select id="f-opp"><option value="">All</option>{opp_opts}</select></label>
  <label>Status
    <select id="f-status"><option value="">All</option>
      <option value="untested">Untested</option>
      <option value="partially-supported">Partially supported</option>
      <option value="supported">Supported</option>
      <option value="contradicted">Contradicted</option></select></label>
</div>
<table class="assumptions" id="atable"><thead><tr>
  <th>Opportunity</th><th>Factor</th><th>Status</th><th>Assumption (basis)</th>
  <th>Supporting evidence</th><th>Validation method</th><th>Sensitivity</th><th>Owner</th>
</tr></thead><tbody>{rows}</tbody></table>
<p class="muted">Sensitivity, owner, and a formal status enum are not yet structured fields in the
knowledge base — shown as "—" rather than invented. Status is derived: evidence-backed → supported;
assumption citing evidence → partially supported; assumption with no evidence → untested.</p>"""
    return L.page("Assumptions & Evidence Gaps", "assumptions.html", body, model.generated_note)
