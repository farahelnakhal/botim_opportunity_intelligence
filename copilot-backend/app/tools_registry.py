"""Read-only tool allowlist. Every tool calls an EXISTING repository function
(engines, impact read models, monitoring outputs). Strict ID validation; the
model can never supply filesystem paths. Draft tools are in-memory only.

Absent by design: apply/rollback/approve, email, file access, shell, eval.
"""

import datetime
import functools
import json
import re
import sys
from pathlib import Path

from . import mv_tools
from .config import Config, REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "opportunity-intelligence" / "tools"))

from impact import brief as impact_brief                      # noqa: E402
from impact import gaps as impact_gaps                        # noqa: E402
from impact import gap_profile as impact_gap_profile          # noqa: E402
from impact import history as impact_history                  # noqa: E402
from impact import paths as impact_paths                      # noqa: E402
from impact import proposal as impact_proposal                # noqa: E402
from impact import research_request as impact_rr              # noqa: E402
from impact import tracker as impact_tracker                  # noqa: E402
from opportunity_engine import evidence, scoring              # noqa: E402
from shared import freshness as shared_freshness              # noqa: E402
from shared import source_urls as shared_source_urls          # noqa: E402

impact_paths.set_repo_root(REPO_ROOT)

# Merchant Voice tools (app/mv_tools.py) each take `config` as their first
# argument (mv_db_path lives there, mutable — tests point it at a temp
# mv.db). Bound once here via a shared, mutable Config instance so
# REGISTRY/call_tool below can treat them like every other zero-config tool.
MV_CONFIG = Config()

KB = REPO_ROOT / "knowledge-base"

OPP_RE = re.compile(r"^OPP-\d{3}$")
EV_RE = re.compile(r"^EV-\d{4}-W\d{2}-\d{3}$")
SEG_RE = re.compile(r"^SEG-[a-z0-9][a-z0-9-]{0,60}$")
IP_RE = re.compile(r"^IP-\d{4}-\d{3}$")
VE_RE = re.compile(r"^VE-\d{3}$")
ASM_RE = re.compile(r"^ASM-OPP-\d{3}-[a-z0-9_]{1,40}$")


class ToolError(Exception):
    def __init__(self, message, not_found=False):
        super().__init__(message)
        self.not_found = not_found


def _now():
    return datetime.datetime.utcnow().isoformat() + "Z"


def _validate(pattern, value, kind):
    if not isinstance(value, str) or not pattern.match(value):
        raise ToolError(f"invalid {kind} id: {value!r}")
    return value


def _records():
    return evidence.load_records(KB / "customer-evidence")


# --- opportunity tools (reuse scoring engine + impact read models) ----------

def _card_paths():
    return sorted((KB / "opportunity-scores").glob("*-scorecard.json"))


def list_opportunities():
    out = []
    for p in _card_paths():
        card = json.loads(p.read_text(encoding="utf-8"))
        ev = scoring.evaluate(card)
        raw = sum(e["score"] for e in ev["scores"].values())
        out.append({"opportunity_id": card["opportunity_id"], "name": card.get("name", ""),
                    "raw_score": f"{raw}/85", "composite_score": ev["composite_indicative"],
                    "assumption_count": ev["assumption_count"], "capped": ev["assumption_capped"],
                    "classification": card.get("proposed_classification"),
                    "evidence_confidence": card.get("evidence_confidence"),
                    "critical_flags": ev["critical_flags"]})
    return {"opportunities": out}


def _one_opportunity(opp_id):
    for entry in list_opportunities()["opportunities"]:
        if entry["opportunity_id"] == opp_id:
            return entry
    raise ToolError(f"{opp_id} not found", not_found=True)


def get_opportunity(opp_id):
    _validate(OPP_RE, opp_id, "opportunity")
    view = _brief_view(opp_id)
    # Phase 4 — deterministic freshness for every evidence id this view cites,
    # so grounding can warn about stale support without re-reading the KB.
    records, source_log = _records(), _source_log()
    cited = set(view["supporting_primary"]) | set(view["supporting_leads"]) | set(view["contradicting"])
    evidence_freshness = {}
    for ev_id in sorted(cited):
        rec = records.get(ev_id)
        if rec is not None:
            p = _provenance(rec, source_log)
            evidence_freshness[ev_id] = {k: p[k] for k in
                                         ("freshness_status", "freshness_reason",
                                          "freshness_age_days", "last_verified_at")}
    return {"opportunity_id": opp_id, "name": view["name"], "score": view["score"],
            "customer": view["customer"], "confidence": view["confidence"],
            "supporting_primary": view["supporting_primary"],
            "supporting_leads": view["supporting_leads"],
            "contradicting": view["contradicting"], "risks": view["risks"],
            "next_validation": view["next_validation"],
            "assumptions": view["assumptions"],
            "inflection_points": view["inflection_points"],
            "evidence_freshness": evidence_freshness}


def compare_opportunities(opp_a, opp_b):
    _validate(OPP_RE, opp_a, "opportunity"); _validate(OPP_RE, opp_b, "opportunity")
    return {"a": _one_opportunity(opp_a), "b": _one_opportunity(opp_b)}


def get_opportunity_score(opp_id):
    _validate(OPP_RE, opp_id, "opportunity")
    return {"opportunity_id": opp_id, "score": _tracker(opp_id)["score"]}


def get_score_factors(opp_id):
    _validate(OPP_RE, opp_id, "opportunity")
    p = KB / "opportunity-scores" / f"{opp_id.lower()}-scorecard.json"
    if not p.exists():
        raise ToolError(f"{opp_id} not found", not_found=True)
    card = json.loads(p.read_text(encoding="utf-8"))
    ev = scoring.evaluate(card)
    return {"opportunity_id": opp_id,
            "factors": {d: e for d, e in ev["scores"].items()}}


def _tracker(opp_id):
    try:
        return impact_tracker.build(opp_id, _now())
    except FileNotFoundError:
        raise ToolError(f"{opp_id} not found", not_found=True)


def get_opportunity_assumptions(opp_id):
    _validate(OPP_RE, opp_id, "opportunity")
    m = _tracker(opp_id)
    return {"opportunity_id": opp_id, "counts": m["counts"],
            "assumptions": [{k: a[k] for k in ("assumption_id", "category", "status",
                                               "decision_importance", "supporting_ev",
                                               "contradicting_ev", "next_validation_method")}
                            for a in m["assumptions"]]}


def get_assumption_register(opp_id):
    _validate(OPP_RE, opp_id, "opportunity")
    return _tracker(opp_id)


def get_evidence_gaps():
    return impact_gaps.build_portfolio(_now())


def get_evidence_gap_profile(opp_id):
    """Phase R10 — the deterministic evidence-gap PROFILE for one opportunity:
    its ranked weakest links across five signals (no supporting evidence,
    assumption-capped dimensions, contradicted evidence, stale load-bearing
    evidence, open gaps). Read-only; recomputes no score; every input shown.
    This surfaces WHERE evidence is weakest so a human can target research —
    it never drafts or sends anything to a merchant."""
    _validate(OPP_RE, opp_id, "opportunity")
    try:
        return impact_gap_profile.build_gap_profile(opp_id, _now())
    except FileNotFoundError:
        raise ToolError(f"{opp_id} not found", not_found=True)


# --- evidence / segment / inflection / competitor / experiment ---------------

def _source_log():
    try:
        return evidence.load_source_log(KB / "customer-evidence")
    except AttributeError:  # engine without the Phase 4 source-log parser
        return {}


def _provenance(rec, source_log=None):
    """Provenance + deterministic freshness for one parsed record (Phase 4).

    Only data already stored in the record/source log; a missing field is
    None, and the URL is emitted only when it passes the shared http(s)-only
    policy — never a local path, never fabricated.
    """
    source_log = _source_log() if source_log is None else source_log
    src = source_log.get((rec.get("source_ids") or [None])[0]) or {}
    fresh = shared_freshness.compute({
        "last_verified_at": rec.get("last_verified_at"),
        "retrieved_at": src.get("added"),
        "publication_date": rec.get("publication_date"),
        "date_of_evidence": rec.get("date_of_evidence"),
        "created_at": rec.get("created_at"),
    })
    return {
        "source_title": src.get("title"),
        "source_url": (shared_source_urls.first_candidate(rec.get("source_text"))
                       or shared_source_urls.normalize(src.get("url_text"))),
        "publisher": src.get("publisher"),
        "publication_date": rec.get("publication_date"),
        "date_of_evidence": rec.get("date_of_evidence"),
        "retrieved_at": src.get("added"),
        "created_at": rec.get("created_at"),
        "last_verified_at": rec.get("last_verified_at"),
        "excerpt": rec.get("excerpt"),
        "access_label": rec.get("access_label"),
        **fresh,
    }


def get_evidence_record(ev_id):
    _validate(EV_RE, ev_id, "evidence")
    rec = _records().get(ev_id)
    if rec is None:
        raise ToolError(f"{ev_id} not found", not_found=True)
    weak = bool(evidence.check_citations([ev_id], {ev_id: rec})["weak"])
    return {"ev_id": ev_id, "title": rec.get("title", ""), "status": rec.get("status"),
            "evidence_confidence": rec.get("evidence_confidence", ""),
            "segment": rec.get("segment", ""), "pain_category": rec.get("pain_category", ""),
            "workaround": rec.get("workaround", ""),
            "contradictory_evidence": rec.get("contradictory_evidence", ""),
            "scores": rec.get("scores", {}), "is_weak_lead": weak,
            "provenance": _provenance(rec)}


def get_segment(seg_id):
    _validate(SEG_RE, seg_id, "segment")
    seg = impact_brief._read_segment(seg_id)   # reuses the existing adapter logic
    if seg is None:
        raise ToolError(f"{seg_id} not found", not_found=True)
    return {"segment_id": seg_id, "title": seg["title"], "confidence": seg["confidence"],
            "job_to_be_done": seg["job"]}


def get_inflection_point(ip_id):
    _validate(IP_RE, ip_id, "inflection")
    p = KB / "inflection-points" / f"{ip_id}.md"     # narrow fallback: fixed dir + validated id
    if not p.exists():
        raise ToolError(f"{ip_id} not found", not_found=True)
    text = p.read_text(encoding="utf-8")
    title = re.search(r"^#\s+(.+)$", text, re.M)
    status = re.search(r"\*\*Status:\*\*\s*(\S+)", text)
    return {"ip_id": ip_id, "title": title.group(1) if title else ip_id,
            "status": status.group(1) if status else None}


def _known_competitors():
    return sorted(p.stem for p in (KB / "competitors").glob("*.md") if p.stem != "README")


def get_competitor_evidence(name):
    known = _known_competitors()
    if not isinstance(name, str) or name.lower() not in known:
        raise ToolError(f"unknown competitor {name!r}; known: {', '.join(known)}", not_found=True)
    text = (KB / "competitors" / f"{name.lower()}.md").read_text(encoding="utf-8")
    title = re.search(r"^#\s+(.+)$", text, re.M)
    gaps_m = re.search(r"\*\*Gaps[^:]*:\*\*\s*(.+)", text)
    return {"competitor": name.lower(), "title": title.group(1) if title else name,
            "gaps": gaps_m.group(1)[:500] if gaps_m else None}


def get_validation_experiment(ve_id):
    _validate(VE_RE, ve_id, "experiment")
    p = KB / "validation" / f"{ve_id}-result.json"
    if not p.exists():
        raise ToolError(f"{ve_id} not found", not_found=True)
    data = json.loads(p.read_text(encoding="utf-8"))
    return {"ve_id": ve_id, "proposition": data.get("proposition"),
            "metrics": data.get("metrics", []), "on_pass": data.get("on_pass"),
            "on_fail": data.get("on_fail")}


# --- brief / changes / history ----------------------------------------------

def _brief_view(opp_id):
    try:
        return impact_brief.build_view(opp_id, _now())
    except FileNotFoundError:
        raise ToolError(f"{opp_id} not found", not_found=True)


def get_executive_brief(opp_id):
    """Uses the existing generator, in memory; regenerates when no derived
    file exists. Never writes."""
    _validate(OPP_RE, opp_id, "opportunity")
    view = _brief_view(opp_id)
    return {"opportunity_id": opp_id, "markdown": impact_brief.render_markdown(view),
            "json": impact_brief.render_json(view)}


def get_recent_changes():
    changes = []
    for e in impact_history.read_all():
        changes.append({"source": "score-history", "kind": e.get("kind"),
                        "timestamp": e.get("timestamp"), "opportunity_id": e.get("opportunity_id"),
                        "summary": e.get("explanation", ""),
                        "simulated_fixture": "TEST" in json.dumps(e.get("ev_ids", []))})
    events_dir = KB / "monitoring" / "events"
    if events_dir.is_dir():
        for f in sorted(events_dir.glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                ev = json.loads(line)
                changes.append({"source": "monitoring", "kind": ev.get("adapter"),
                                "timestamp": ev.get("detected_at"), "entity": ev.get("entity"),
                                "summary": f"{ev.get('adapter')} detected change on {ev.get('entity')}",
                                "simulated_fixture": bool(ev.get("simulated"))
                                                     or "TEST" in str(ev.get("entity", ""))})
    return {"changes": changes[-50:]}


def get_score_history(opp_id):
    _validate(OPP_RE, opp_id, "opportunity")
    return {"opportunity_id": opp_id,
            "entries": [e for e in impact_history.read_all()
                        if e.get("opportunity_id") == opp_id]}


# --- bounded knowledge search (approved record fields only) ------------------

def search_product_knowledge(query):
    """Searches ONLY approved product-discovery record fields: IDs, titles,
    evidence statements, segment/opportunity descriptions, assumptions,
    experiments, competitor profiles and inflection points. Never code,
    config, env files, prompts, or git metadata. Deterministic keyword
    matching only — no vector index, no external search."""
    if not isinstance(query, str) or not (2 <= len(query) <= 200):
        raise ToolError("query must be a string of 2..200 characters")
    terms = [t for t in re.split(r"[^a-z0-9-]+", query.lower()) if len(t) >= 3]
    if not terms:
        raise ToolError("query has no searchable terms")

    def hit(text):
        low = (text or "").lower()
        return sum(1 for t in terms if t in low)

    results = []
    for ev_id, rec in _records().items():
        score = hit(ev_id) + hit(rec.get("title", "")) + hit(rec.get("segment", "")) \
            + hit(rec.get("pain_category", "")) + hit(rec.get("workaround", ""))
        if score:
            results.append({"id": ev_id, "type": "evidence", "title": rec.get("title", ""), "match": score})
    for p in _card_paths():
        card = json.loads(p.read_text(encoding="utf-8"))
        basis = " ".join(e.get("basis", "") for e in card["scores"].values())
        score = hit(card["opportunity_id"]) + hit(card.get("name", "")) + hit(basis)
        if score:
            results.append({"id": card["opportunity_id"], "type": "opportunity",
                            "title": card.get("name", ""), "match": score})
    for p in sorted((KB / "segments").glob("SEG-*.md")):
        text = p.read_text(encoding="utf-8")
        first = text.splitlines()[0] if text else ""
        score = hit(p.stem) + hit(first)
        if score:
            results.append({"id": p.stem, "type": "segment", "title": first.lstrip("# "), "match": score})
    for p in sorted((KB / "validation").glob("VE-*-result.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        blob = json.dumps(data.get("metrics", [])) + str(data.get("proposition", ""))
        score = hit(data.get("experiment_id", "")) + hit(blob)
        if score:
            results.append({"id": data.get("experiment_id"), "type": "experiment",
                            "title": data.get("proposition", ""), "match": score})
    for name in _known_competitors():
        p = KB / "competitors" / f"{name}.md"
        text = p.read_text(encoding="utf-8")
        title_m = re.search(r"^#\s+(.+)$", text, re.M)
        title = title_m.group(1) if title_m else name
        gaps_m = re.search(r"\*\*Gaps[^:]*:\*\*\s*(.+)", text)
        score = hit(name) + hit(title) + hit(gaps_m.group(1) if gaps_m else "")
        if score:
            results.append({"id": name, "type": "competitor", "title": title, "match": score})
    for p in sorted((KB / "inflection-points").glob("IP-*.md")):
        text = p.read_text(encoding="utf-8")
        title_m = re.search(r"^#\s+(.+)$", text, re.M)
        title = title_m.group(1) if title_m else p.stem
        score = hit(p.stem) + hit(title)
        if score:
            results.append({"id": p.stem, "type": "inflection", "title": title, "match": score})
    results.sort(key=lambda r: -r["match"])
    return {"query": query, "results": results[:12]}


# --- draft-only tools (EPHEMERAL: returned in the response, never persisted) -

def generate_research_request_draft(assumption_id):
    _validate(ASM_RE, assumption_id, "assumption")
    try:
        draft = impact_rr.generate(assumption_id, _now())
    except (ValueError, FileNotFoundError) as exc:
        raise ToolError(str(exc), not_found=True)
    draft["ephemeral"] = True
    return {"draft_type": "research_request", "draft": draft}


def generate_executive_brief(opp_id):
    _validate(OPP_RE, opp_id, "opportunity")
    out = get_executive_brief(opp_id)
    return {"draft_type": "executive_brief", "draft": {"markdown": out["markdown"],
                                                       "ephemeral": True}}


def generate_impact_proposal_draft(opp_id, ev_id, factor, proposed_score, justification):
    """Builds a DRAFT impact proposal in memory using the existing generator.
    It is never written to knowledge-base/impact/proposals and cannot be
    applied from this backend (no apply tool exists here)."""
    _validate(OPP_RE, opp_id, "opportunity"); _validate(EV_RE, ev_id, "evidence")
    if not isinstance(factor, str) or factor not in scoring.DIMENSIONS:
        raise ToolError(f"unknown factor {factor!r}")
    if not isinstance(proposed_score, int) or not 1 <= proposed_score <= 5:
        raise ToolError("proposed_score must be an integer 1..5")
    if not isinstance(justification, str) or not justification.strip():
        raise ToolError("justification required")
    rec = _records().get(ev_id)
    if rec is None:
        raise ToolError(f"{ev_id} not found", not_found=True)
    p = KB / "opportunity-scores" / f"{opp_id.lower()}-scorecard.json"
    if not p.exists():
        raise ToolError(f"{opp_id} not found", not_found=True)
    card = json.loads(p.read_text(encoding="utf-8"))
    conf = (rec.get("evidence_confidence", "") or "").split("—")[0].strip().lower() or None
    strength = rec.get("scores", {}).get("evidence strength")
    field_map = {"willingness_to_pay": "willingness_to_pay_signal",
                 "switching_intent": "switching_signal",
                 "credit_need": "credit_need_confirmation"}
    field = field_map.get(factor)
    if field is None:
        raise ToolError(f"factor {factor!r} has no approved evidence-field mapping for drafts")
    descriptor = {"ev_id": ev_id, "evidence_confidence": conf,
                  "evidence_strength": strength, "evidence_class": "observed behaviour",
                  "observations": [{"evidence_field": field, "proposed_score": proposed_score,
                                    "justification": justification.strip()}]}
    draft = impact_proposal.generate(card, descriptor, None,
                                     proposal_id="PROP-DRAFT-EPHEMERAL", today=_now()[:10])
    draft["ephemeral"] = True
    draft["note"] = ("Draft only — not persisted, not appliable from the copilot. "
                     "A human must create and approve a real proposal via the impact workflow.")
    return {"draft_type": "impact_proposal", "draft": draft}


def get_external_research(opportunity_ref=None):
    """Human-APPROVED external-research candidate claims (Phase R3), read
    from the research platform's runtime store (shared/research). Approved
    means a human reviewed the claim — it is still candidate research, NEVER
    authoritative Part A evidence; no EV id exists or is implied. Sources
    carry recorded metadata plus deterministic freshness."""
    if opportunity_ref is not None:
        if not isinstance(opportunity_ref, str) or not re.match(
                r"^(OPP-\d{3}|UOPP-[0-9a-f]{12})$", opportunity_ref):
            raise ToolError("opportunity_ref must be an OPP-nnn or UOPP- id")
    from shared.research import ResearchStore, ResearchStoreError
    try:
        store = ResearchStore()
        candidates = store.list_candidates(status="approved",
                                           opportunity_ref=opportunity_ref, limit=20)
    except ResearchStoreError as exc:
        raise ToolError(f"research store unavailable: {exc}")
    out = []
    # latest revalidation per source, per run (Phase R4b) — computed once
    revalidations_by_run = {}
    for c in candidates:
        if c["run_id"] not in revalidations_by_run:
            revalidations_by_run[c["run_id"]] = store.latest_revalidations(c["run_id"])
        latest = revalidations_by_run[c["run_id"]]
        sources = []
        for s in store.get_sources(c["source_ids"]):
            # Information age comes from the publication date ONLY: automated
            # retrieval is always recent, so counting retrieved_at would mark
            # every external source permanently "fresh". No publication date
            # -> honestly "unknown", never a guess.
            fresh = shared_freshness.compute({
                "publication_date": s.get("published_at")})
            rev = latest.get(s["id"])
            sources.append({"id": s["id"], "url": s["canonical_url"],
                            "domain": s["domain"], "title": s.get("title"),
                            "publisher": s.get("publisher"),
                            "published_at": s.get("published_at"),
                            "retrieved_at": s.get("retrieved_at"),
                            "freshness_status": fresh["freshness_status"],
                            # Phase R4b — latest re-check, if one exists
                            "check_outcome": rev["outcome"] if rev else None,
                            "last_checked": rev["checked_at"] if rev else None})
        out.append({"candidate_id": c["id"], "claim": c["claim"],
                    "contradicts": c.get("contradicts"),
                    "run_id": c["run_id"], "run_title": c.get("run_title"),
                    "opportunity_ref": c.get("opportunity_ref"),
                    "reviewed": True,
                    "source_health": store.source_health(c, latest),
                    "sources": sources})
    return {"approved_candidates": out,
            "note": ("External research candidates are human-approved web-research "
                     "claims — clearly external, not authoritative repository evidence.")}


def get_analysis_workspace(opportunity_ref):
    """Latest COMPLETE preliminary analysis workspace version for a saved
    opportunity (Phase R5/PR4). Everything in it is machine-generated
    PRELIMINARY analysis: the preliminary score is an all-assumption card
    evaluated (and capped) by the real scoring engine; claims are candidate
    external research with their CURRENT human-review status (approvals live
    on the claims, never on the workspace). Reading a workspace never
    triggers a build — refreshes happen only via the explicit triggers."""
    if not isinstance(opportunity_ref, str) or not re.match(
            r"^(OPP-\d{3}|UOPP-[0-9a-f]{12})$", opportunity_ref):
        raise ToolError("opportunity_ref must be an OPP-nnn or UOPP- id")
    from shared.workspace import WorkspaceStore, WorkspaceStoreError
    from shared.research import ResearchStore, ResearchStoreError
    try:
        ws = WorkspaceStore()
        latest = ws.latest(opportunity_ref)
    except WorkspaceStoreError as exc:
        raise ToolError(f"workspace store unavailable: {exc}")
    if latest is None:
        return {"workspace": None,
                "note": ("no analysis workspace exists for this opportunity yet — "
                         "a workspace refresh must be run first")}
    claims = []
    if latest.get("research_run_id") and latest.get("claim_ids"):
        try:
            detail = ResearchStore().get_run(latest["research_run_id"],
                                             include_children=True)
            by_id = {c["id"]: c for c in detail.get("candidate_evidence", [])}
            for cid in latest["claim_ids"]:
                c = by_id.get(cid)
                if c:
                    claims.append({"candidate_id": c["id"], "claim": c["claim"],
                                   "status": c["status"], "origin": c.get("origin"),
                                   "run_id": latest["research_run_id"]})
        except ResearchStoreError:
            pass  # workspace still reports its ids; claims just can't resolve
    return {"workspace": {
        "id": latest["id"], "opportunity_ref": opportunity_ref,
        "version": latest["version"], "trigger": latest["trigger"],
        "question": latest.get("question"),
        "completed_at": latest.get("completed_at"),
        "is_stale": ws.is_stale(latest),
        "preliminary_score": latest.get("preliminary_score"),
        "kb_evidence": latest.get("kb_evidence") or [],
        "document_evidence": latest.get("document_evidence") or [],
        "claims": claims,
        "gaps": latest.get("gaps") or [],
        "research_run_id": latest.get("research_run_id"),
        "provenance": latest.get("provenance"),
    }, "note": ("PRELIMINARY machine-generated analysis — nothing here is "
                "authoritative repository evidence; unreviewed claims remain "
                "pending human review.")}


def list_calculators():
    """Phase C1 — the deterministic-calculator catalog: each calculator's id,
    title, and REQUIRED inputs (with units). Use this to learn which inputs
    run_calculator needs before calling it; never invent input values."""
    from shared.calculators import catalog
    out = []
    for c in catalog():
        out.append({"id": c["id"], "title": c["title"], "description": c["description"],
                    "inputs": [{"name": i["name"], "unit": i["unit"], "kind": i["kind"],
                                "required": i["required"], "description": i["description"]}
                               for i in c["inputs"]]})
    return {"calculators": out,
            "note": ("Deterministic calculators compute exact, shown-working results from "
                     "the numbers you pass — the model must never do the arithmetic itself.")}


def run_calculator(calculator_id, inputs):
    """Phase C1 — run a deterministic calculator and return its FULLY SHOWN
    working (typed steps + outputs + disclaimers). The formula is fixed in
    code; only numbers are supplied (never an expression). A calculation over
    assumed inputs is illustrative/preliminary, never a validated figure; the
    numbers here are authoritative over anything the model might compute."""
    from shared.calculators import compute, render_markdown, CalculatorError
    if not isinstance(calculator_id, str):
        raise ToolError("calculator_id must be a string")
    if inputs is None:
        inputs = {}
    if not isinstance(inputs, dict):
        raise ToolError("inputs must be an object of {name: number | {value,label,note}}")
    try:
        envelope = compute(calculator_id, inputs)
    except CalculatorError as exc:
        raise ToolError(str(exc), not_found=(exc.status == 404))
    return {"calculation": envelope, "shown_working": render_markdown(envelope),
            "note": ("Deterministic calculation — every number is computed and shown; "
                     "inputs labelled 'assumption' make the result illustrative, not validated.")}


# --- registry ----------------------------------------------------------------

def _schema(props, required):
    return {"type": "object", "properties": props, "required": required}

_ID = {"type": "string"}

REGISTRY = {
    "list_opportunities": (list_opportunities, _schema({}, []), "List all opportunities with engine scores"),
    "compare_opportunities": (compare_opportunities, _schema({"opp_a": _ID, "opp_b": _ID}, ["opp_a", "opp_b"]), "Compare two opportunities"),
    "get_opportunity": (get_opportunity, _schema({"opp_id": _ID}, ["opp_id"]), "Full grounded view of one opportunity"),
    "get_opportunity_score": (get_opportunity_score, _schema({"opp_id": _ID}, ["opp_id"]), "Engine score block"),
    "get_score_factors": (get_score_factors, _schema({"opp_id": _ID}, ["opp_id"]), "All 17 factors with bases"),
    "get_opportunity_assumptions": (get_opportunity_assumptions, _schema({"opp_id": _ID}, ["opp_id"]), "Assumption summary"),
    "get_assumption_register": (get_assumption_register, _schema({"opp_id": _ID}, ["opp_id"]), "Rich assumption register"),
    "get_evidence_gaps": (get_evidence_gaps, _schema({}, []), "Portfolio evidence gaps, prioritized"),
    "get_evidence_gap_profile": (get_evidence_gap_profile, _schema({"opp_id": _ID}, ["opp_id"]),
                                 "Ranked evidence-gap profile (weakest links) for one opportunity — where its evidence is thinnest"),
    "get_evidence_record": (get_evidence_record, _schema({"ev_id": _ID}, ["ev_id"]), "One Part A evidence record"),
    "get_segment": (get_segment, _schema({"seg_id": _ID}, ["seg_id"]), "Segment profile"),
    "get_inflection_point": (get_inflection_point, _schema({"ip_id": _ID}, ["ip_id"]), "Inflection point"),
    "get_competitor_evidence": (get_competitor_evidence, _schema({"name": _ID}, ["name"]), "Competitor profile summary"),
    "get_validation_experiment": (get_validation_experiment, _schema({"ve_id": _ID}, ["ve_id"]), "Validation experiment + thresholds"),
    "get_executive_brief": (get_executive_brief, _schema({"opp_id": _ID}, ["opp_id"]), "Executive brief (in-memory)"),
    "get_recent_changes": (get_recent_changes, _schema({}, []), "Recent history + monitoring changes"),
    "get_score_history": (get_score_history, _schema({"opp_id": _ID}, ["opp_id"]), "Score history entries"),
    "search_product_knowledge": (search_product_knowledge, _schema({"query": _ID}, ["query"]), "Bounded search over approved record fields"),
    "get_external_research": (get_external_research,
                              _schema({"opportunity_ref": _ID}, []),
                              "Human-approved external web-research candidates (never authoritative KB evidence)"),
    "get_analysis_workspace": (get_analysis_workspace,
                               _schema({"opportunity_ref": _ID}, ["opportunity_ref"]),
                               "Latest preliminary analysis workspace for a saved opportunity (machine-generated, pending review)"),
    "list_calculators": (list_calculators, _schema({}, []),
                         "List the deterministic calculators and their required inputs (call before run_calculator)"),
    "run_calculator": (run_calculator,
                       _schema({"calculator_id": _ID, "inputs": {"type": "object"}},
                               ["calculator_id", "inputs"]),
                       "Run a deterministic calculator (market sizing, unit economics, payback, ...) and return fully shown working; the model must NEVER do the arithmetic itself"),
    "generate_research_request_draft": (generate_research_request_draft, _schema({"assumption_id": _ID}, ["assumption_id"]), "Draft research request (ephemeral)"),
    "generate_executive_brief": (generate_executive_brief, _schema({"opp_id": _ID}, ["opp_id"]), "Draft executive brief (ephemeral)"),
    "generate_impact_proposal_draft": (generate_impact_proposal_draft,
                                       _schema({"opp_id": _ID, "ev_id": _ID, "factor": _ID,
                                                "proposed_score": {"type": "integer"},
                                                "justification": {"type": "string"}},
                                               ["opp_id", "ev_id", "factor", "proposed_score", "justification"]),
                                       "Draft impact proposal (ephemeral, never appliable here)"),
}

# Merchant Voice tools — each wrapped with MV_CONFIG bound in (see mv_tools.py)
# and mv_tools.ToolError translated to THIS module's ToolError (a distinct
# class — orchestrator.py only catches this one), so call_tool() below can
# invoke every entry uniformly as fn(**args).

def _wrap_mv_tool(fn):
    @functools.wraps(fn)
    def wrapper(**kwargs):
        try:
            return fn(MV_CONFIG, **kwargs)
        except mv_tools.ToolError as exc:
            raise ToolError(str(exc), not_found=exc.not_found)
    return wrapper


for _mv_name, (_mv_fn, _mv_schema, _mv_desc) in mv_tools.REGISTRY.items():
    REGISTRY[_mv_name] = (_wrap_mv_tool(_mv_fn), _mv_schema, _mv_desc)


def tool_specs():
    return [{"name": name, "description": desc, "input_schema": schema}
            for name, (_, schema, desc) in REGISTRY.items()]


def call_tool(name, arguments):
    if name not in REGISTRY:
        raise ToolError(f"tool {name!r} is not in the allowlist")
    fn, schema, _ = REGISTRY[name]
    args = arguments or {}
    unknown = set(args) - set(schema["properties"])
    if unknown:
        raise ToolError(f"unknown arguments: {sorted(unknown)}")
    missing = [k for k in schema["required"] if k not in args]
    if missing:
        raise ToolError(f"missing arguments: {missing}")
    return fn(**args)
