"""Read-only collection pass: repository outputs -> UIModel.

Reuses the existing engines as the single source of truth. No scoring, no
confidence reinterpretation, no writes. Best-effort prose extraction from
profiles degrades to model.UNKNOWN — never fabricates, never crashes.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

from . import impact_bridge
from . import model as M

EV_RE = re.compile(r"\bEV-\d{4}-W\d{2}-\d{3}\b")
OPP_RE = re.compile(r"\bOPP-\d{3}\b")
VE_RE = re.compile(r"\bVE-\d{3}\b")


def _engines(root):
    """Import Workstream B and C engines read-only (single source of truth)."""
    b = str(Path(root).resolve() / "opportunity-intelligence" / "tools")
    c = str(Path(root).resolve() / "intelligence-monitoring" / "tools")
    # repo root too, so shared/ (freshness thresholds, URL policy) resolves
    for p in (b, c, str(Path(root).resolve())):
        if p not in sys.path:
            sys.path.insert(0, p)
    from opportunity_engine import backlog, evidence, journal, scoring
    mon = {}
    try:
        from monitoring_engine import alerts, events, summaries
        mon = {"events": events, "alerts": alerts, "summaries": summaries}
    except Exception:  # monitoring optional for the UI to render
        mon = {}
    return {"scoring": scoring, "backlog": backlog, "evidence": evidence,
            "journal": journal, **mon}


def _section(text, header):
    """Return the body under a '## header' (or '### header') until the next header."""
    m = re.search(rf"^#{{2,3}}\s+{re.escape(header)}.*?$(.*?)(?=^#{{2,3}}\s|\Z)",
                  text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else M.UNKNOWN


def _first_line_matching(text, needle):
    for line in text.splitlines():
        if needle.lower() in line.lower():
            return line.strip("-* ").strip()
    return M.UNKNOWN


def _git_history(root, rel_path):
    """Commits touching a file, newest first: [{date, subject}]. Empty if unavailable."""
    try:
        out = subprocess.run(
            ["git", "log", "--format=%ad|%s", "--date=short", "--", rel_path],
            cwd=root, capture_output=True, text=True, timeout=10)
        if out.returncode != 0:
            return []
        rows = []
        for line in out.stdout.splitlines():
            if "|" in line:
                d, s = line.split("|", 1)
                rows.append({"date": d, "subject": s})
        return rows
    except Exception:
        return []


def _load_profiles(kb):
    """Map OPP id -> {path, text} for product-ideas/opp-*.md (non-recommendation)."""
    out = {}
    for path in sorted((kb / "product-ideas").glob("opp-*.md")):
        if "recommendation" in path.name:
            continue
        m = OPP_RE.search("OPP-" + path.name[4:7])
        oid = "OPP-" + path.name[4:7]
        out[oid] = {"path": str(path.relative_to(kb.parent)), "text": path.read_text(encoding="utf-8")}
    return out


def _backlog_rows(eng, kb):
    """OPP id -> backlog row dict (classification_label, next_action, segment, archived)."""
    path = kb / "product-ideas" / "BACKLOG.md"
    rows = {}
    if not path.exists():
        return rows
    data = eng["backlog"].parse(path)
    for r in data["backlog"]:
        rows[r["id"]] = {"label": r["classification"], "next_action": r["next_action"],
                         "segment": r["segment"], "archived": False}
    for r in data["archive"]:
        rows.setdefault(r["id"], {"label": "Reject", "next_action": M.UNKNOWN,
                                  "segment": M.UNKNOWN, "archived": True})
    return rows


def _evidence_refs(eng, kb, cited_ids, roles_by_id):
    """Build EvidenceRef for every real record + any cited-but-missing id.

    Phase 4: preserves the provenance the parser now retains (source title/
    publisher/URL/dates/excerpt/access label) and attaches the deterministic
    freshness status from shared/freshness.py. Absent provenance stays None —
    an unresolved or source-less record is reported honestly, never padded.
    """
    from shared import freshness, source_urls
    refs = {}
    records = eng["evidence"].load_records(kb / "customer-evidence") if "evidence" in eng else {}
    try:
        source_log = eng["evidence"].load_source_log(kb / "customer-evidence")
    except AttributeError:  # older engine without the source-log parser
        source_log = {}
    for rid, rec in records.items():
        strength = rec["scores"].get("evidence strength", M.UNKNOWN)
        status = rec.get("status") or M.UNKNOWN
        weak = (isinstance(strength, int) and strength < 3) or status == "needs-more-evidence"
        src = source_log.get((rec.get("source_ids") or [None])[0]) or {}
        source_url = (source_urls.first_candidate(rec.get("source_text"))
                      or source_urls.normalize(src.get("url_text")))
        fresh = freshness.compute({
            "last_verified_at": rec.get("last_verified_at"),
            "retrieved_at": src.get("added"),
            "publication_date": rec.get("publication_date"),
            "date_of_evidence": rec.get("date_of_evidence"),
            "created_at": rec.get("created_at"),
        })
        refs[rid] = M.EvidenceRef(
            ev_id=rid, resolved=True,
            evidence_class="behavioural/stated (see record)",
            strength=strength, confidence=(rec.get("evidence_confidence") or M.UNKNOWN).split(" ")[0],
            status=status, segment=rec.get("segment", M.UNKNOWN), title=rec.get("title", M.UNKNOWN),
            role=roles_by_id.get(rid, M.CONTEXTUAL), weak=weak,
            source_type=rec.get("access_label") or M.UNKNOWN,
            source_title=src.get("title"),
            source_url=source_url,
            publisher=src.get("publisher"),
            publication_date=rec.get("publication_date"),
            date_of_evidence=rec.get("date_of_evidence"),
            retrieved_at=src.get("added"),
            created_at=rec.get("created_at"),
            last_verified_at=rec.get("last_verified_at"),
            excerpt=rec.get("excerpt"),
            access_label=rec.get("access_label"),
            contradictory_evidence=rec.get("contradictory_evidence"),
            **fresh,
        )
    for cid in cited_ids:
        if cid not in refs:
            refs[cid] = M.EvidenceRef(
                ev_id=cid, resolved=False, role=roles_by_id.get(cid, M.CONTEXTUAL),
                weak=True, status="unresolved",
                freshness_reason="This evidence id is cited but the record is not on file.")
    return refs


def _assumption_status(factor):
    if not factor.assumption:
        return "supported"
    if factor.evidence_ids:
        return "partially-supported"
    return "untested"


def build_model(root="."):
    root = Path(root)
    kb = root / "knowledge-base"
    eng = _engines(root)
    scoring = eng["scoring"]
    m = M.UIModel()

    profiles = _load_profiles(kb)
    blrows = _backlog_rows(eng, kb)

    # monitoring (optional)
    mon_events = eng["events"].load_events(kb / "monitoring" / "events") if "events" in eng else []
    events_by_opp = {}
    for e in mon_events:
        for link in e.get("kb_links", []):
            events_by_opp.setdefault(link, []).append(e)

    cited_ids = set()
    roles_by_id = {}   # ev_id -> primary/contextual/excluded (max role seen across scorecards)

    def bump_role(eid, role):
        order = {M.EXCLUDED: 0, M.CONTEXTUAL: 1, M.PRIMARY: 2}
        if order[role] > order.get(roles_by_id.get(eid, M.EXCLUDED), -1):
            roles_by_id[eid] = role

    scorecards = sorted((kb / "opportunity-scores").glob("*.json"))
    raw_opps = []
    for path in scorecards:
        card = json.loads(path.read_text(encoding="utf-8"))
        ev = scoring.evaluate(card)   # SINGLE SOURCE OF TRUTH — no recompute in UI
        oid = ev["opportunity_id"]
        factors = []
        for key in scoring.DIMENSIONS:
            fe = ev["scores"][key]
            ev_ids = EV_RE.findall(fe["basis"])
            factors.append(M.Factor(key=key, score=fe["score"], assumption=fe["assumption"],
                                    basis=fe["basis"], evidence_ids=ev_ids))
            for eid in ev_ids:
                cited_ids.add(eid)
                bump_role(eid, M.PRIMARY if not fe["assumption"] else M.CONTEXTUAL)
        raw = sum(f.score for f in factors)
        prof = profiles.get(oid, {})
        ptext = prof.get("text", "")
        row = blrows.get(oid, {})
        opp = M.Opportunity(
            id=oid, name=card.get("name", oid), raw_score=raw, raw_max=5 * len(scoring.DIMENSIONS),
            composite=ev["composite_indicative"], classification=ev["proposed_classification"] or "unscored",
            classification_label=row.get("label", ev["proposed_classification"] or M.UNKNOWN),
            confidence=(ev["evidence_confidence"] or M.UNKNOWN),
            assumption_count=ev["assumption_count"], factors=factors,
            critical_flags=ev["critical_flags"],
            segment=row.get("segment", M.UNKNOWN),
            jtbd=_first_line_matching(ptext, "job-to-be-done") if ptext else M.UNKNOWN,
            hypothesis=_section(ptext, "Proposition") if ptext else M.UNKNOWN,
            contradictory_evidence=_section(ptext, "Disconfirmation") if ptext else M.UNKNOWN,
            rejection_conditions=(_first_line_matching(ptext, "rejection condition")
                                  or _first_line_matching(ptext, "This changes if")) if ptext else M.UNKNOWN,
            validation_plan=_first_line_matching(ptext, "Next action") if ptext else M.UNKNOWN,
            next_action=row.get("next_action", M.UNKNOWN),
            profile_path=prof.get("path", M.UNKNOWN),
            is_archived=row.get("archived", False),
            score_history=_git_history(root, str(path.relative_to(root))),
        )
        opp_events = sorted(events_by_opp.get(oid, []), key=lambda e: e["detected_at"], reverse=True)
        if opp_events:
            opp.latest_alert = f"{opp_events[0]['id']} [{opp_events[0]['tier']}] {opp_events[0]['title']}"
        raw_opps.append((opp, card))

    # strongest / contradictory evidence refs need the evidence table first
    all_refs = _evidence_refs(eng, kb, cited_ids, roles_by_id)
    for opp, card in raw_opps:
        prim = [all_refs[f_ev] for f in opp.factors for f_ev in f.evidence_ids
                if f_ev in all_refs and all_refs[f_ev].role == M.PRIMARY and not all_refs[f_ev].weak]
        # dedupe, keep strongest few
        seen, uniq = set(), []
        for r in sorted(prim, key=lambda r: -(r.strength if isinstance(r.strength, int) else 0)):
            if r.ev_id not in seen:
                seen.add(r.ev_id); uniq.append(r)
        opp.strongest_evidence = uniq[:5]
        # assumptions from (A) factors
        for f in opp.factors:
            if f.assumption:
                m.assumptions.append(M.Assumption(
                    opportunity_id=opp.id, factor_key=f.key, text=f.basis,
                    status=_assumption_status(f), evidence_ids=f.evidence_ids,
                    validation_method=(opp.next_action if VE_RE.search(opp.next_action or "") else M.UNKNOWN),
                ))
        (m.archived if opp.is_archived else m.opportunities).append(opp)

    m.opportunities.sort(key=lambda o: -o.raw_score)
    m.evidence = sorted(all_refs.values(), key=lambda r: r.ev_id)

    # feed: monitoring events + resolved predictions
    for e in sorted(mon_events, key=lambda e: e["detected_at"], reverse=True):
        kind = "alert" if e["tier"] in ("important", "critical") else "lead"
        m.feed.append(M.FeedItem(id=e["id"], kind=kind, tier=e["tier"], title=e["title"],
                                 detected_at=e["detected_at"],
                                 detail=", ".join(e.get("kb_links", [])) or M.UNKNOWN))
    jpath = kb / "product-ideas" / "decision-journal.json"
    if jpath.exists() and "journal" in eng:
        for p in eng["journal"].load(jpath)["predictions"]:
            if p.get("outcome") is not None:
                m.feed.append(M.FeedItem(
                    id=p["id"], kind="prediction-resolved", tier=M.UNKNOWN,
                    title=p["statement"], detected_at=p.get("resolved_on") or M.UNKNOWN,
                    detail=p.get("resolution_note", ""),
                    before_after={"before": f"p={p['p']:.0%}", "after": str(p["outcome"])}))

    # archived rejects from the backlog (no scorecard, but leadership must see them)
    blpath = kb / "product-ideas" / "BACKLOG.md"
    if blpath.exists():
        scored_ids = {o.id for o in m.opportunities} | {o.id for o in m.archived}
        for r in eng["backlog"].parse(blpath)["archive"]:
            if r["id"] in scored_ids:
                continue
            prof = profiles.get(r["id"], {})
            m.archived.append(M.Opportunity(
                id=r["id"], name=r.get("proposition", r["id"]), raw_score=None, raw_max=5 * len(scoring.DIMENSIONS),
                composite=None, classification="reject",
                classification_label=r.get("reason", "Reject"), confidence=M.UNKNOWN,
                assumption_count=0, factors=[], is_archived=True,
                rejection_conditions=r.get("reason", M.UNKNOWN),
                next_action=f"Reopen trigger: {r.get('reopen_trigger', M.UNKNOWN)}",
                profile_path=prof.get("path", M.UNKNOWN)))

    # briefs: recommendation docs (filenames are lowercase opp-nnn)
    def _oid_from_name(name):
        mm = re.search(r"opp-(\d{3})", name, re.IGNORECASE)
        return f"OPP-{mm.group(1)}" if mm else None
    rec_paths = {}
    for p in (kb / "product-ideas").glob("*recommendation*.md"):
        oid = _oid_from_name(p.name)
        if oid:
            rec_paths[oid] = p
    for opp in m.opportunities + m.archived:
        rp = rec_paths.get(opp.id)
        if rp:
            m.briefs.append(M.Brief(opportunity_id=opp.id, exists=True,
                                    path=str(rp.relative_to(root)), body=rp.read_text(encoding="utf-8")))
        else:
            m.briefs.append(M.Brief(opportunity_id=opp.id, exists=False))

    # --- Evidence-Impact Workflow enrichment (authoritative, read-only) ---
    # Overlays real assumption status/sensitivity/validation/owner, executive
    # brief envelopes, and score history. Degrades silently to the scorecard-
    # derived view above if the impact workflow is unavailable.
    live_ids = [o.id for o in m.opportunities]
    m.impact_available = impact_bridge.available(str(root))
    if m.impact_available:
        tracker_assumptions = impact_bridge.assumptions_by_opp(str(root), live_ids)
        if tracker_assumptions:
            opp_by_id = {o.id: o for o in m.opportunities}
            m.assumptions = []
            for oid in live_ids:
                for a in tracker_assumptions.get(oid, []):
                    m.assumptions.append(M.Assumption(
                        opportunity_id=oid, factor_key=a.get("factor", M.UNKNOWN),
                        text=a.get("statement", M.UNKNOWN),
                        status=str(a.get("status", "untested")).replace("_", "-"),
                        evidence_ids=a.get("supporting_ev", []) or [],
                        sensitivity=a.get("sensitivity", M.UNKNOWN) or M.UNKNOWN,
                        validation_method=(", ".join(a.get("related_ve", []))
                                           or a.get("next_validation_method", M.UNKNOWN) or M.UNKNOWN),
                        owner=a.get("validation_owner", M.UNKNOWN) or M.UNKNOWN,
                        decision_importance=a.get("decision_importance", M.UNKNOWN) or M.UNKNOWN,
                        source="impact-tracker"))

        envelopes = impact_bridge.brief_envelopes(str(root), live_ids)
        hist = impact_bridge.history_by_opp(str(root))
        for o in m.opportunities:
            o.brief_envelope = envelopes.get(o.id)
            o.impact_history = hist.get(o.id, [])
            if o.impact_history:
                h = o.impact_history[0]
                o.latest_change = (f"{h.get('history_id', 'HIST')}: raw "
                                   f"{h.get('raw_score_prev', '?')}→{h.get('raw_score_new', '?')} "
                                   f"({h.get('kind', 'applied')}, approved by {h.get('approved_by', '—')})")
        m.impact_proposals = impact_bridge.proposals(str(root))

    # Phase 4 — reverse-link every evidence ref to the opportunities and
    # assumptions that actually cite it (never an invented relation)
    links_opp, links_asm = {}, {}
    for opp, _card in raw_opps:
        for f in opp.factors:
            for eid in f.evidence_ids:
                links_opp.setdefault(eid, set()).add(opp.id)
    for a in m.assumptions:
        for eid in (a.evidence_ids or []):
            links_asm.setdefault(eid, set()).add(f"{a.opportunity_id}::{a.factor_key}")
    for ref in m.evidence:
        ref.linked_opportunity_ids = sorted(links_opp.get(ref.ev_id, ()))
        ref.linked_assumption_ids = sorted(links_asm.get(ref.ev_id, ()))

    m.generated_note = (f"{len(m.opportunities)} live + {len(m.archived)} archived opportunities · "
                        f"{len(m.evidence)} evidence records · {len(m.feed)} feed items · "
                        f"impact workflow: {'connected' if m.impact_available else 'unavailable'} · "
                        "engine-computed, read-only")
    return m
