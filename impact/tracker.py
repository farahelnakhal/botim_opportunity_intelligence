"""Assumption & Evidence-Gap Tracker — generated read model.

Authoritative mutation store:  knowledge-base/impact/assumptions/<opp>.json
   (changed ONLY by approved impacts via impact/apply.py)
Generated read model (this):   knowledge-base/impact/assumption-registers/<opp>.json
   (derived, regenerable, read-only, NEVER a second source of truth)

The rich register is assembled read-only from: the scorecard (+ engine
evaluate), the authoritative register, cited EV records (Part A parser),
score history, linked validation experiments, and an optional human-authored
metadata sidecar (assumption-metadata/<opp>.json). Nothing here recomputes
scores or mutates any source.
"""

import json
import re
from pathlib import Path

from . import assumptions as store
from . import categories, genmeta, history, paths

EV_RE = re.compile(r"\bEV-\d{4}-W\d{2}-\d{3}\b")
SEG_RE = re.compile(r"\bSEG-[a-z0-9][a-z0-9-]*\b")
IP_RE = re.compile(r"\bIP-\d{4}-\d{3}\b")
_ORDER = {"low": 0, "medium": 1, "high": 2}

_STATUS_TO_UI = {"partially supported": "partially_supported"}
_STATUS_TO_STORE = {v: k for k, v in _STATUS_TO_UI.items()}


def status_to_ui(s):
    return _STATUS_TO_UI.get(s, s)


def status_to_store(s):
    return _STATUS_TO_STORE.get(s, s)


def _conf_token(rec):
    v = (rec or {}).get("evidence_confidence", "") or ""
    return v.strip().split()[0].lower() if v.strip() else None


def _slug(opp_id):
    return opp_id.lower()


def scorecard_path(opp_id):
    return paths.KB / "opportunity-scores" / f"{_slug(opp_id)}-scorecard.json"


def _load_ve(opp_id):
    out = []
    vdir = paths.KB / "validation"
    if not vdir.is_dir():
        return out
    for rp in sorted(vdir.glob("*-result.json")):
        try:
            data = json.loads(rp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("proposition") == opp_id:
            out.append(data)
    return out


def _rejection_from_ve(ve_list):
    for ve in ve_list:
        fails = []
        for m in ve.get("metrics", []):
            f = m.get("failure")
            if f:
                fails.append(f"{m['name']} {f['op']} {f['value']}")
        if fails:
            return f"{ve['experiment_id']} failure: " + " or ".join(fails) + f" → {ve.get('on_fail', '')}".rstrip()
    return None


def _next_validation_from_ve(ve_list):
    if not ve_list:
        return ""
    ve = ve_list[0]
    descs = [m.get("description", m.get("name", "")) for m in ve.get("metrics", [])]
    return f"{ve['experiment_id']}: " + "; ".join(d for d in descs if d)


def _change_history(opp_id, factor):
    out = []
    for e in history.read_all():
        if e.get("opportunity_id") != opp_id:
            continue
        prev = (e.get("prev_factor_values") or {}).get(factor)
        upd = (e.get("updated_factor_values") or {}).get(factor)
        if prev is None and upd is None:
            continue
        out.append({
            "history_id": e.get("history_id"), "kind": e.get("kind"),
            "timestamp": e.get("timestamp"), "ev_ids": e.get("ev_ids", []),
            "approved_by": e.get("approved_by"),
            "from": prev, "to": upd,
        })
    return out


def build(opp_id, now, source_extra=None):
    """Return the rich read model for one opportunity. `now` is supplied by the
    caller (never invented). Read-only."""
    scoring, evidence = paths.load_engine()
    sc_path = scorecard_path(opp_id)
    if not sc_path.exists():
        raise FileNotFoundError(f"no scorecard for {opp_id}: {sc_path}")
    card = json.loads(sc_path.read_text(encoding="utf-8"))
    ev = scoring.evaluate(card)
    scores = card["scores"]
    raw = sum(e["score"] for e in scores.values())

    records = evidence.load_records(paths.KB / "customer-evidence")

    store_path = paths.ASSUMPTIONS_DIR / f"{_slug(opp_id)}.json"
    reg = json.loads(store_path.read_text(encoding="utf-8")) if store_path.exists() else None
    reg_by_factor = {a["factor"]: a for a in (reg or {}).get("assumptions", [])}

    meta_path = paths.IMPACT_KB / "assumption-metadata" / f"{_slug(opp_id)}.json"
    sidecar = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    imp_override = sidecar.get("decision_importance", {})
    field_override = sidecar.get("fields", {})  # {factor: {validation_owner,target_date,rejection_condition,...}}

    ve_list = _load_ve(opp_id)
    related_ve = [v["experiment_id"] for v in ve_list]

    source_files = [sc_path]
    if store_path.exists():
        source_files.append(store_path)
    if meta_path.exists():
        source_files.append(meta_path)
    if paths.SCORE_HISTORY.exists():
        source_files.append(paths.SCORE_HISTORY)
    source_files += [p for p in source_files if False]  # keep order stable
    for v in ve_list:
        vp = paths.KB / "validation" / f"{v['experiment_id']}-result.json"
        if vp.exists():
            source_files.append(vp)
    for p in (source_extra or []):
        source_files.append(p)

    problems = []
    items = []
    # Union of (scorecard factors still flagged assumption:true) and (factors
    # tracked in the authoritative register). A factor de-assumed by an approved
    # impact stays visible with its evidenced status — removing the flag updates
    # the register, it does not hide the assumption.
    factor_list = [f for f in scores if scores[f].get("assumption", True)]
    factor_list += [f for f in reg_by_factor if f not in factor_list and f in scores]
    for factor in factor_list:
        e = scores[factor]
        rentry = reg_by_factor.get(factor)
        basis_ev = EV_RE.findall(e.get("basis", ""))
        reg_support = list(rentry.get("supporting_ev", [])) if rentry else []
        supporting = list(dict.fromkeys(reg_support + basis_ev))
        provenance = {i: ("impact" if i in reg_support else "scorecard_basis") for i in supporting}
        contradicting = list((rentry or {}).get("contradicting_ev", []))
        contradicting += [c for c in field_override.get(factor, {}).get("contradicting_ev", []) if c not in contradicting]

        for i in supporting + contradicting:
            if i not in records:
                problems.append({"assumption_id": f"ASM-{opp_id}-{factor}", "ev_id": i,
                                 "problem": "unresolved evidence reference (not found in Part A records)"})

        conf_map = {i: _conf_token(records.get(i)) for i in supporting if i in records}
        present = [c for c in conf_map.values() if c]
        derived_conf = min(present, key=lambda c: _ORDER.get(c, 0)) if present else None

        status_store = (rentry or {}).get("status", "untested")
        fo = field_override.get(factor, {})
        rejection = fo.get("rejection_condition") or _rejection_from_ve(ve_list)
        nextval = (rentry or {}).get("next_validation") or fo.get("next_validation_method") or _next_validation_from_ve(ve_list)

        count = ev["assumption_count"]
        cap = scoring.ASSUMPTION_CAP
        items.append({
            "assumption_id": f"ASM-{opp_id}-{factor}",
            "opportunity_id": opp_id,
            "statement": e.get("basis", "").strip() or f"{factor} assumption",
            "category": categories.category_for(factor),
            "status": status_to_ui(status_store),
            "source": (rentry and "scorecard factor") or "scorecard factor",
            "factor": factor,
            "supporting_ev": supporting,
            "supporting_ev_provenance": provenance,
            "contradicting_ev": contradicting,
            "evidence_confidence": {
                "rule": "lowest confidence among cited supporting EV; null if none cited",
                "cited_ev_confidences": conf_map,
                "derived": derived_conf,
            },
            "decision_importance": imp_override.get(factor, categories.default_importance(factor)),
            "score_impact": {
                "current_contribution_raw": e["score"],
                "raw_max": 85,
                "raw_swing_per_point": 1,
                "composite_swing_per_point": round(1 / 17, 3),
                "assumption_cap": {
                    "count": count, "cap": cap, "capped": count > cap,
                    "resolving_this_lifts_cap": (count - 1) <= cap,
                    "assumptions_to_lift_cap": max(0, count - cap),
                },
                "decision_sensitivity": None,
                "score_impact_explanation": (
                    "Scorecard is an unweighted 1-5 average: per-point swings are exact "
                    "(raw +/-1/85, composite +/-1/17=0.059). Decision-level sensitivity is "
                    "null - no weighting/decision model exists to quantify go/no-go movement, "
                    "so it is not invented."),
            },
            "sensitivity": (rentry or {}).get("sensitivity", ""),
            "next_validation_method": nextval,
            "validation_owner": fo.get("validation_owner"),
            "target_date": fo.get("target_date"),
            "last_updated": (_change_history(opp_id, factor)[-1]["timestamp"]
                             if _change_history(opp_id, factor) else None),
            "change_history": _change_history(opp_id, factor),
            "related_ve": related_ve,
            "rejection_condition": rejection,
        })

    # manual / non-scorecard assumptions from the sidecar (e.g. regulatory, risk)
    for m in sidecar.get("manual_assumptions", []):
        m = dict(m)
        m.setdefault("opportunity_id", opp_id)
        m.setdefault("source", "manual entry")
        m.setdefault("supporting_ev", [])
        m.setdefault("contradicting_ev", [])
        for i in m["supporting_ev"] + m["contradicting_ev"]:
            if i not in records:
                problems.append({"assumption_id": m.get("assumption_id", "?"), "ev_id": i,
                                 "problem": "unresolved evidence reference (not found in Part A records)"})
        items.append(m)

    unresolved = [a for a in items if a["status"] in ("untested", "partially_supported")]

    return {
        "meta": genmeta.build_meta("assumption-register", source_files, now),
        "opportunity_id": opp_id,
        "name": card.get("name", ""),
        "score": {
            "raw_score": f"{raw}/85", "raw": raw, "raw_max": 85,
            "composite_score": ev["composite_indicative"],
            "assumption_count": ev["assumption_count"],
            "assumption_cap": scoring.ASSUMPTION_CAP,
            "capped": ev["assumption_capped"],
            "classification": card.get("proposed_classification"),
            "critical_flags": ev["critical_flags"],
        },
        "counts": {
            "total_assumptions": len(items),
            "unresolved": len(unresolved),
            "no_supporting_evidence": sum(1 for a in items if not a["supporting_ev"]),
            "contradicted": sum(1 for a in items if a["status"] == "contradicted"),
        },
        "assumptions": items,
        "evidence_problems": problems,
    }


def render_markdown(model):
    s = model["score"]
    lines = [
        f"# Assumption register — {model['opportunity_id']} {model['name']}".rstrip(),
        "",
        f"- Raw score: **{s['raw_score']}** · composite {s['composite_score']} · "
        f"classification {s['classification']}"
        + (" (capped by assumptions)" if s["capped"] else ""),
        f"- Assumptions: {model['counts']['total_assumptions']} · unresolved "
        f"**{model['counts']['unresolved']}** · no-evidence {model['counts']['no_supporting_evidence']} · "
        f"contradicted {model['counts']['contradicted']}",
        "",
        "| Assumption | Category | Status | Importance | Supporting EV | Contradicting EV | Next validation |",
        "|---|---|---|---|---|---|---|",
    ]
    for a in model["assumptions"]:
        lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            a["assumption_id"], a["category"], a["status"], a["decision_importance"],
            ", ".join(a["supporting_ev"]) or "—", ", ".join(a["contradicting_ev"]) or "—",
            (a["next_validation_method"] or "—")[:60]))
    if model["evidence_problems"]:
        lines += ["", "## Evidence problems (reported, not ignored)"]
        for p in model["evidence_problems"]:
            lines.append(f"- {p['assumption_id']}: {p['ev_id']} — {p['problem']}")
    return "\n".join(lines) + "\n"
