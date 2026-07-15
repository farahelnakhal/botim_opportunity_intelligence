"""UIModel + engine outputs -> JSON-ready dicts.

Pure transformation. No scoring, no writes, no reinterpretation. Everything
here is derived from the read-only adapter (`adapter.collect.build_model`) or
from a direct read-only engine call. Absent data becomes an explicit sentinel
("—") or null — never a fabricated value.
"""

import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
REPO = UI.parents[0]
for _p in (str(UI), str(REPO), str(REPO / "opportunity-intelligence" / "tools"),
           str(REPO / "intelligence-monitoring" / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from adapter import collect  # noqa: E402

DECISION_BANNER = "No product or build decision has been made."


# --------------------------------------------------------------------------- #
# Core model (opportunities, evidence, assumptions, feed, briefs)
# --------------------------------------------------------------------------- #
def build_payload(root=None):
    """Return the whole read-only model as a JSON-ready dict."""
    root = str(root or REPO)
    m = collect.build_model(root)
    return {
        "meta": {
            "generated_note": m.generated_note,
            "decision_banner": m.decision_banner,
            "impact_available": m.impact_available,
            "counts": {
                "opportunities": len(m.opportunities),
                "archived": len(m.archived),
                "evidence": len(m.evidence),
                "assumptions": len(m.assumptions),
                "feed": len(m.feed),
            },
        },
        "opportunities": [_opp(o) for o in m.opportunities],
        "archived": [_opp(o) for o in m.archived],
        "evidence": [asdict(e) for e in m.evidence],
        "assumptions": [asdict(a) for a in m.assumptions],
        "feed": [asdict(f) for f in m.feed],
        "briefs": [asdict(b) for b in m.briefs],
        "impact_proposals": m.impact_proposals,
    }


def _opp(o):
    d = asdict(o)
    # dataclasses.asdict already recurses into Factor / EvidenceRef lists
    return d


# --------------------------------------------------------------------------- #
# Commercial model (opportunity_engine.commercial) — downside/base/upside
# --------------------------------------------------------------------------- #
def commercial_payload(opp_id, root=None):
    """Compute the commercial model for one opportunity. Read-only: reads the
    committed inputs JSON and runs the engine; nothing is written."""
    root = Path(root or REPO)
    from opportunity_engine import commercial
    n = opp_id.split("-")[-1]
    candidates = sorted((root / "knowledge-base" / "commercial-models").glob(f"opp-{n}*inputs.json"))
    if not candidates:
        return None
    model = json.loads(candidates[0].read_text(encoding="utf-8"))
    results = commercial.compute_model(model)
    cases = {}
    for name, r in results.items():
        cases[name] = {
            "case": r.case,
            "total_revenue": round(r.total_revenue, 2),
            "financing_revenue": round(r.financing_revenue, 2),
            "payment_revenue": round(r.payment_revenue, 2),
            "acquiring_revenue": round(r.acquiring_revenue, 2),
            "total_cost": round(r.total_cost, 2),
            "cost_of_capital": round(r.cost_of_capital, 2),
            "expected_credit_loss": round(r.expected_credit_loss, 2),
            "contribution": round(r.contribution, 2),
            "contribution_pct": round(r.contribution_pct, 1),
            "portfolio_contribution": round(r.portfolio_contribution, 2),
            "breakeven_merchants": (round(r.breakeven_merchants, 1)
                                    if r.breakeven_merchants is not None else None),
            "active_merchants": r.v("active_merchants"),
            "warnings": list(r.warnings),
        }
    return {
        "opportunity_id": model.get("opportunity_id", opp_id),
        "name": model.get("name", opp_id),
        "currency": model.get("currency", "AED"),
        "source": str(candidates[0].relative_to(root)),
        "cases": cases,
        "decision_banner": DECISION_BANNER,
        "note": ("Illustrative unit economics from committed model inputs. These are "
                 "planning scenarios, not a forecast, and imply no build decision."),
    }


# --------------------------------------------------------------------------- #
# Experiments (opportunity_engine.experiments) — VE specs + committed results
# --------------------------------------------------------------------------- #
def experiments_payload(root=None):
    root = Path(root or REPO)
    from opportunity_engine import experiments
    vdir = root / "knowledge-base" / "validation"
    out = []
    if not vdir.is_dir():
        return out
    for path in sorted(vdir.glob("VE-*.md")):
        fields = experiments.parse_file(path)
        issues = experiments.validate_file(path)
        ve_id = fields.get("experiment id", path.stem[:6])
        # title: first markdown H1, minus the "VE-nnn — " prefix
        title = path.stem
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = line[2:].split("—", 1)[-1].strip() or line[2:].strip()
                break
        result = None
        rpath = vdir / f"{ve_id}-result.json"
        if rpath.exists():
            try:
                result = json.loads(rpath.read_text(encoding="utf-8"))
            except Exception:
                result = None
        out.append({
            "id": ve_id,
            "title": title,
            "hypothesis": fields.get("hypothesis", "—"),
            "success_threshold": fields.get("success threshold", "—"),
            "kill_threshold": fields.get("failure threshold", "—"),
            "method": fields.get("method", "—"),
            "linked_opportunity": fields.get("proposition tested", "—"),
            "duration": fields.get("duration", "—"),
            "decision_informed": fields.get("decision informed", "—"),
            "status": (result or {}).get("status", "designed" if not issues else "draft"),
            "result": result,
            "spec_issues": issues,
            "source": str(path.relative_to(root)),
        })
    return out


# --------------------------------------------------------------------------- #
# Decision journal (opportunity_engine.journal) — predictions + calibration
# --------------------------------------------------------------------------- #
def journal_payload(root=None, today=None):
    root = Path(root or REPO)
    from opportunity_engine import journal
    jpath = root / "knowledge-base" / "product-ideas" / "decision-journal.json"
    if not jpath.exists():
        return {"predictions": [], "calibration": None}
    data = journal.load(jpath)
    cal = journal.calibration(data, today=today)
    entries = []
    for p in data["predictions"]:
        outcome = p.get("outcome")
        brier = None
        if outcome is not None:
            brier = round((p["p"] - (1.0 if outcome else 0.0)) ** 2, 3)
        entries.append({
            "id": p["id"],
            "statement": p["statement"],
            "p": p["p"],
            "made": p["made"],
            "resolve_by": p["resolve_by"],
            "outcome": outcome,
            "resolved_on": p.get("resolved_on"),
            "resolution_note": p.get("resolution_note", ""),
            "rationale": p.get("rationale", ""),
            "links": p.get("links", []),
            "brier": brier,
            "excluded_from_calibration": bool(p.get("excluded_from_calibration")),
        })
    return {
        "predictions": entries,
        "calibration": {
            "brier": (round(cal["brier"], 3) if cal["brier"] is not None else None),
            "n_resolved": cal["n_resolved"],
            "n_open": len(cal["open"]),
            "n_overdue": len(cal["overdue"]),
            "buckets": cal["buckets"],
        },
        "note": ("Brier score over resolved, non-excluded predictions. Lower is better "
                 "(0 = perfect, 0.25 = a coin flip at 50%)."),
    }


# --------------------------------------------------------------------------- #
# Monitoring (monitoring_engine) — events, alerts, summaries
# --------------------------------------------------------------------------- #
# Internal-KB watcher adapter name — events from it are repository changes,
# not external observations, and must be labelled that way in the UI.
KB_WATCHER_ADAPTER = "kb-watcher"

# An event feed with nothing newer than this is "no recent updates" rather
# than "active" (deterministic; based only on stored detected_at dates).
MONITORING_RECENT_DAYS = 14


def _monitoring_summary_state(available, events, alerts_rows, entities):
    """Current-state monitoring summary (Phase 4). Every count comes from a
    committed artefact; anything the backend cannot calculate is None with an
    honest note — never an invented number."""
    import datetime
    if not available:
        return {"status": "unavailable",
                "status_note": "The monitoring engine could not be loaded; monitoring data is unavailable.",
                "last_checked": None, "latest_event_at": None, "event_count": None,
                "open_alert_count": None, "unresolved_warning_count": None,
                "monitored_entity_count": None, "external_source_count": None,
                "internal_only": None}
    latest = max((e.get("detected_at") or "" for e in events), default=None) or None
    adapters = {e.get("adapter") for e in events}
    internal_only = bool(events) and adapters <= {KB_WATCHER_ADAPTER}
    open_statuses = ("new", "analyzed", "alerted")
    unresolved = sum(1 for e in events
                     if e.get("tier") in ("important", "critical")
                     and e.get("status") in open_statuses)
    ent_rows = entities or []
    external_sources = (sum(len(e.get("sources") or []) for e in ent_rows)
                        if ent_rows else None)
    if not events:
        status = "never-run" if not ent_rows else "no-events"
        note = ("The monitoring engine has never produced an event." if not ent_rows else
                "Monitored entities are configured but no monitoring events exist yet.")
    else:
        recent = False
        try:
            latest_d = datetime.date.fromisoformat(latest)
            recent = (datetime.date.today() - latest_d).days <= MONITORING_RECENT_DAYS
        except (TypeError, ValueError):
            pass
        status = "active" if recent else "no-recent-updates"
        if internal_only:
            note = ("Monitoring is running against the internal knowledge base only — "
                    "all events are internal knowledge-base changes; no external "
                    "monitoring source is connected yet.")
        else:
            note = "Monitoring includes external sources."
        if status == "no-recent-updates":
            note += f" No event in the last {MONITORING_RECENT_DAYS} days."
    return {
        "status": status,
        "status_note": note,
        # no run timestamp is committed anywhere, so this is honestly null —
        # the latest event date below is the best committed signal
        "last_checked": None,
        "latest_event_at": latest,
        "event_count": len(events),
        "open_alert_count": len(alerts_rows),
        "unresolved_warning_count": unresolved,
        "monitored_entity_count": len(ent_rows) if ent_rows else (0 if entities == [] else None),
        "external_source_count": external_sources,
        "internal_only": internal_only if events else None,
    }


def monitoring_payload(root=None):
    root = Path(root or REPO)
    mdir = root / "knowledge-base" / "monitoring"
    out = {"events": [], "alerts": [], "summaries": [], "summary_state": None}
    available = True
    try:
        from monitoring_engine import alerts, events, summaries
    except Exception:
        out["summary_state"] = _monitoring_summary_state(False, [], [], None)
        return out
    try:
        evs = events.load_events(mdir / "events")
        out["events"] = sorted(evs, key=lambda e: e.get("detected_at", ""), reverse=True)
    except Exception:
        available = False
    try:
        out["alerts"] = alerts.load_alerts(mdir / "alerts")
    except Exception:
        pass
    try:
        sm = summaries.load_summaries(mdir / "summaries")
        # Only the event id + machine flags — never the local file path.
        # The markdown itself is served by monitoring_summary_payload below.
        if isinstance(sm, dict):
            out["summaries"] = [{"id": k, "available": True, "flags": (v or {}).get("flags")}
                                for k, v in sorted(sm.items())]
    except Exception:
        pass
    entities = None
    try:
        epath = mdir / "entities.json"
        if epath.exists():
            entities = [e for e in json.loads(epath.read_text(encoding="utf-8")).get("entities", [])
                        if e.get("status") == "active"]
    except Exception:
        entities = None
    out["summary_state"] = _monitoring_summary_state(available, out["events"], out["alerts"], entities)
    return out


# Bounded, read-only access to a per-event summary Markdown file (Phase 4).
# The id is strictly validated and the file is resolved ONLY inside the
# monitoring summaries directory — no caller-supplied path ever reaches the
# filesystem, and the response is size-limited.
EVENT_ID_RE = re.compile(r"^EVT-\d{4}-W\d{2}-\d{3}$")
MONITORING_SUMMARY_MAX_BYTES = 131072  # 128 KiB — summaries are ~2-4 KiB


# --------------------------------------------------------------------------- #
# Web brief (Phase 4) — GET /executive-api/brief/{opportunity_id}
# --------------------------------------------------------------------------- #
OPP_ID_RE = re.compile(r"^OPP-\d{3}$")


def _approved_merchant_findings(opp_id, root):
    """Approved, PUBLISHED Merchant Voice findings linked to this opportunity,
    through Merchant Voice's own read-only query layer (published_query) over
    a strictly read-only SQLite connection — the same seam copilot-backend
    uses. Never opens identity.db; never returns identities, transcripts, or
    unapproved/suppressed/needs-revalidation content. Honest unavailable
    state when Merchant Voice has never run (no mv.db)."""
    import importlib
    import importlib.util
    import sqlite3
    mv_db = Path(root) / "merchant-voice" / "data" / "mv.db"
    if not mv_db.exists():
        return {"available": False, "findings": [],
                "note": "Merchant Voice has not published any findings in this environment."}
    try:
        if "mv_app" not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                "mv_app", Path(root) / "merchant-voice" / "app" / "__init__.py",
                submodule_search_locations=[str(Path(root) / "merchant-voice" / "app")])
            module = importlib.util.module_from_spec(spec)
            sys.modules["mv_app"] = module
            spec.loader.exec_module(module)
        published_query = importlib.import_module("mv_app.published_query")
        conn = sqlite3.connect(f"file:{mv_db}?mode=ro", uri=True)
        try:
            rows = published_query.list_findings(conn, opportunity_id=opp_id)
        finally:
            conn.close()
    except Exception:
        return {"available": False, "findings": [],
                "note": "Merchant Voice findings could not be loaded."}
    keep = ("finding_id", "approved_statement", "finding_type", "campaign_id", "method",
            "segment_id", "strength_band", "support_count", "contradiction_count",
            "numerator", "denominator", "denominator_definition", "limitations")
    return {"available": True,
            "findings": [{k: f.get(k) for k in keep} for f in rows],
            "note": ("Approved, published Merchant Voice research signals — never "
                     "authoritative Part A evidence.")}


def brief_payload(opp_id, root=None):
    """The full web-report read model for one opportunity. Reuses the existing
    overview/brief envelope/journal/monitoring read models — no second brief
    model, no recomputation. None for an unknown opportunity; ValueError for
    an invalid id."""
    if not isinstance(opp_id, str) or not OPP_ID_RE.match(opp_id):
        raise ValueError("invalid opportunity id")
    root = Path(root or REPO)
    payload = build_payload(root)
    opp = next((o for o in payload["opportunities"] + payload["archived"]
                if o["id"] == opp_id), None)
    if opp is None:
        return None

    brief = next((b for b in payload["briefs"]
                  if b["opportunity_id"] == opp_id and b["exists"]), None)
    cited = sorted({ev for f in opp["factors"] for ev in f["evidence_ids"]})
    evidence_rows = [e for e in payload["evidence"] if e["ev_id"] in cited]
    assumptions = [a for a in payload["assumptions"] if a["opportunity_id"] == opp_id]

    # predictions: direct OPP links plus links via a validation experiment
    # that tests this opportunity (both are real, recorded relations)
    experiments = experiments_payload(root)
    ve_for_opp = {e["id"] for e in experiments
                  if opp_id in (e.get("linked_opportunity") or "")}
    predictions = [pr for pr in journal_payload(root)["predictions"]
                   if opp_id in (pr.get("links") or [])
                   or ve_for_opp & set(pr.get("links") or [])]

    mon = monitoring_payload(root)
    mon_events = [e for e in mon["events"]
                  if opp_id in (e.get("kb_links") or []) or e.get("entity") == opp_id]

    # risks from the impact brief view (authoritative); honest empty if the
    # impact workflow is unavailable
    risks, unknowns = [], []
    try:
        from impact import brief as impact_brief, paths as impact_paths
        impact_paths.set_repo_root(str(root))
        view = impact_brief.build_view(opp_id, "2026-07-13T00:00:00Z")
        risks = list(view.get("risks") or [])
    except Exception:
        risks = []
    try:
        from impact import gaps as impact_gaps
        gaps = impact_gaps.build_portfolio("2026-07-13T00:00:00Z")
        unknowns = [f"{g['question']}" for g in gaps.get("gaps", [])
                    if g.get("opportunity_id") == opp_id][:8]
    except Exception:
        unknowns = []

    envelope = opp.get("brief_envelope") or None
    actions = []
    if envelope and (envelope.get("recommended_action") or {}).get("text"):
        actions.append(envelope["recommended_action"]["text"])
    if opp.get("next_action") and opp["next_action"] != "—" and opp["next_action"] not in actions:
        actions.append(opp["next_action"])

    # sources appendix — unique external sources behind the cited evidence
    seen, sources = set(), []
    for e in evidence_rows:
        key = (e.get("source_title"), e.get("source_url"))
        if key == (None, None) or key in seen:
            continue
        seen.add(key)
        sources.append({"source_title": e.get("source_title"), "publisher": e.get("publisher"),
                        "source_url": e.get("source_url"), "retrieved_at": e.get("retrieved_at"),
                        "access_label": e.get("access_label"),
                        "evidence_ids": [x["ev_id"] for x in evidence_rows
                                         if (x.get("source_title"), x.get("source_url")) == key]})

    import datetime
    return {
        "opportunity_id": opp_id,
        "title": opp["name"],
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "classification": opp["classification"],
        "classification_label": opp["classification_label"],
        "is_archived": opp["is_archived"],
        "segment": opp["segment"],
        "jtbd": opp["jtbd"],
        "hypothesis": opp["hypothesis"],
        "confidence": opp["confidence"],
        "score_summary": {"raw_score": opp["raw_score"], "raw_max": opp["raw_max"],
                          "composite": opp["composite"],
                          "assumption_count": opp["assumption_count"],
                          "critical_flags": opp["critical_flags"]},
        "brief_envelope": envelope,
        "brief_markdown": brief["body"] if brief else None,
        "evidence": evidence_rows,
        "contradictory_evidence": opp["contradictory_evidence"],
        "assumptions": assumptions,
        "predictions": predictions,
        "monitoring": {"state": mon["summary_state"], "events": mon_events},
        "merchant_voice": _approved_merchant_findings(opp_id, root),
        "risks": risks,
        "unknowns": unknowns,
        "recommended_next_actions": actions,
        "sources": sources,
        "decision_banner": DECISION_BANNER,
    }


# --------------------------------------------------------------------------- #
# Web brief for a USER-created opportunity (Phase 6)
# --------------------------------------------------------------------------- #
def user_brief_payload(store, opp_id):
    """The web-report read model for a persisted user opportunity draft.

    Honest by construction: a draft has no engine score, no evidence
    citations, and no classification — missing sections are reported as not
    yet defined, never fabricated. Raises user_store.StoreError (404/400)
    for unknown/invalid ids."""
    import datetime
    opp = store.get(opp_id)
    monitoring = store.monitoring_get(opp_id)
    return {
        "record_type": "user_opportunity",
        "opportunity_id": opp["id"],
        "title": opp["title"],
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": opp["status"],
        "is_archived": opp["status"] == "archived",
        "classification": "unscored",
        "classification_label": {
            "draft": "Draft — unvalidated, not scored",
            "saved": "Saved opportunity — unvalidated, not scored",
            "archived": "Archived",
        }[opp["status"]],
        "product_definition": opp["product_definition"],
        "problem_statement": opp["problem_statement"],
        "target_segment": opp["target_segment"],
        "customer_description": opp["customer_description"],
        "value_proposition": opp["value_proposition"],
        "assumptions": opp["assumptions"],
        "risks": opp["risks"],
        "unknowns": opp["unknowns"],
        "next_actions": opp["next_actions"],
        "monitoring": monitoring,
        "source_conversation_id": opp["source_conversation_id"],
        "created_from_analysis": opp["created_from_analysis"],
        "created_at": opp["created_at"],
        "updated_at": opp["updated_at"],
        "version": opp["version"],
        "decision_banner": DECISION_BANNER,
    }


def monitoring_summary_payload(event_id, root=None):
    """{"event_id", "markdown", "truncated"} for a committed summary, None if
    absent. Raises ValueError for an invalid id (the API returns 400)."""
    if not isinstance(event_id, str) or not EVENT_ID_RE.match(event_id):
        raise ValueError("invalid monitoring event id")
    root = Path(root or REPO)
    summaries_dir = (root / "knowledge-base" / "monitoring" / "summaries").resolve()
    target = (summaries_dir / f"{event_id}.md").resolve()
    # defense in depth — the strict id regex above already prevents traversal
    if summaries_dir not in target.parents:
        raise ValueError("invalid monitoring event id")
    if not target.is_file():
        return None
    raw = target.read_bytes()
    truncated = len(raw) > MONITORING_SUMMARY_MAX_BYTES
    text = raw[:MONITORING_SUMMARY_MAX_BYTES].decode("utf-8", errors="replace")
    return {"event_id": event_id, "markdown": text, "truncated": truncated}
