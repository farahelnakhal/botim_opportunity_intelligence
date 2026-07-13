"""UIModel + engine outputs -> JSON-ready dicts.

Pure transformation. No scoring, no writes, no reinterpretation. Everything
here is derived from the read-only adapter (`adapter.collect.build_model`) or
from a direct read-only engine call. Absent data becomes an explicit sentinel
("—") or null — never a fabricated value.
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
REPO = UI.parents[0]
for _p in (str(UI), str(REPO / "opportunity-intelligence" / "tools"),
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
def monitoring_payload(root=None):
    root = Path(root or REPO)
    mdir = root / "knowledge-base" / "monitoring"
    out = {"events": [], "alerts": [], "summaries": []}
    try:
        from monitoring_engine import alerts, events, summaries
    except Exception:
        return out
    try:
        evs = events.load_events(mdir / "events")
        out["events"] = sorted(evs, key=lambda e: e.get("detected_at", ""), reverse=True)
    except Exception:
        pass
    try:
        out["alerts"] = alerts.load_alerts(mdir / "alerts")
    except Exception:
        pass
    try:
        sm = summaries.load_summaries(mdir / "summaries")
        # normalise to a list of {id, text}
        if isinstance(sm, dict):
            out["summaries"] = [{"id": k, "text": v} for k, v in sm.items()]
        else:
            out["summaries"] = sm
    except Exception:
        pass
    return out
