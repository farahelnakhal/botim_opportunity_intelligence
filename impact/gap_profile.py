"""Evidence-gap PROFILE for one opportunity (Phase R10, PR10a).

A deterministic, read-only "weakest-link" profile that composes the five gap
signals the codebase already computes — it invents nothing and recomputes no
score:

  1. thin evidence base   — assumptions with no supporting Part A evidence
  2. assumption-capped     — >6 assumption-based scorecard dimensions cap the
                             classification (`scoring.ASSUMPTION_CAP`)
  3. contradicted evidence — assumptions whose status is `contradicted`
  4. stale load-bearing    — supporting EV records older than the freshness
                             `stale` threshold (>180d, `shared.freshness`)
  5. open gaps             — assumptions still untested / partially_supported

Everything here is a *read model*: it reuses `impact.tracker.build` (the rich
per-opportunity assumption register), `opportunity_engine.scoring.evaluate`
(the assumption flags + cap), `impact.gaps._score_gap` (the existing,
documented heuristic ranker — no new scoring is invented), and
`shared.freshness.compute` (the deterministic freshness bands). It never writes
the knowledge base and never proposes an action — it only surfaces where an
opportunity's evidence is weakest, ranked, so a later phase can draft targeted
research questions from it (PR10b). The severity ranking is the same heuristic
`gaps.py` already documents, plus one shown `+1` for stale load-bearing
evidence; weights are exposed in `ranking_method`.
"""

from . import gaps, genmeta, paths, tracker

try:
    from shared import freshness as _freshness
except ImportError:  # repo root not yet on sys.path when imported standalone
    import sys
    sys.path.insert(0, str(paths.REPO_ROOT or ""))
    from shared import freshness as _freshness

# the five signal names, stable for downstream consumers (PR10b)
SIGNALS = ("no_supporting_evidence", "assumption_capped", "contradicted",
           "stale_load_bearing", "open_gap")

STALE_BONUS = 1  # shown weight added when a gap rests on stale load-bearing EV


def _record_freshness(record, now):
    """Freshness for one EV record from its recorded dates only (never
    invented). Reference-date priority is `shared.freshness`'s own."""
    dates = {
        "last_verified_at": record.get("last_verified_at"),
        "publication_date": record.get("publication_date"),
        "date_of_evidence": record.get("date_of_evidence"),
        "created_at": record.get("created_at"),
    }
    return _freshness.compute(dates, today=now)


def build_gap_profile(opp_id, now):
    """Return the ranked evidence-gap profile for one opportunity. `now` is
    supplied by the caller (never invented). Raises FileNotFoundError if the
    opportunity has no scorecard."""
    scoring, evidence = paths.load_engine()
    model = tracker.build(opp_id, now)                 # signals 1-3 per assumption
    card = _load_card(opp_id)
    ev = scoring.evaluate(card)                          # assumption flags + cap
    records = evidence.load_records(paths.KB / "customer-evidence")

    capped = model["score"]["capped"]
    ease = None
    if "ease_of_validation" in card["scores"]:
        ease = card["scores"]["ease_of_validation"]["score"]

    weak_links = []
    all_supporting = set()
    stale_load_bearing = []
    for a in model["assumptions"]:
        all_supporting.update(a.get("supporting_ev") or [])
        # a gap is any assumption not already supported
        if a["status"] == "supported":
            continue

        # signal 4 — stale load-bearing: any supporting EV of THIS open
        # assumption that is stale (>180d). Load-bearing = it is cited support
        # for a gap that is still open.
        stale_ev = []
        for ev_id in a.get("supporting_ev") or []:
            rec = records.get(ev_id)
            if rec is None:
                continue
            fresh = _record_freshness(rec, now)
            if fresh["freshness_status"] == _freshness.STATUS_STALE:
                stale_ev.append({"ev_id": ev_id,
                                 "freshness_status": fresh["freshness_status"],
                                 "age_days": fresh["freshness_age_days"],
                                 "reference_date": fresh["freshness_reference_date"]})
        for s in stale_ev:
            if s not in stale_load_bearing:
                stale_load_bearing.append(s)

        # deterministic severity — reuse the existing documented heuristic,
        # then add a shown bonus for stale load-bearing evidence.
        score, band, reasons, inputs, missing = gaps._score_gap(a, capped, ease)
        if stale_ev:
            score += STALE_BONUS
            band = gaps._band(score)
            reasons = reasons + ["load-bearing supporting evidence is stale (>180d)"]

        signals = ["open_gap"]
        if not a.get("supporting_ev"):
            signals.append("no_supporting_evidence")
        if a["status"] == "contradicted":
            signals.append("contradicted")
        # signal 2 — this scorecard dimension is still an assumption AND the
        # opportunity is capped, so resolving it can lift the cap
        factor = a.get("factor")
        if capped and factor in card["scores"] and card["scores"][factor].get("assumption", True):
            signals.append("assumption_capped")
        if stale_ev:
            signals.append("stale_load_bearing")

        weak_links.append({
            "assumption_id": a["assumption_id"],
            "opportunity_id": opp_id,
            "factor": factor,
            "category": a["category"],
            "statement": a["statement"],
            "status": a["status"],
            "decision_importance": a["decision_importance"],
            "signals": signals,
            "supporting_ev": a.get("supporting_ev") or [],
            "contradicting_ev": a.get("contradicting_ev") or [],
            "stale_ev": stale_ev,
            "priority_score": score,
            "priority_band": band,
            "reasons": reasons,
            "missing_inputs": missing,
        })

    weak_links.sort(key=lambda g: (-g["priority_score"], g["opportunity_id"], g["assumption_id"]))
    for i, g in enumerate(weak_links, 1):
        g["priority_rank"] = i

    counts = model["counts"]
    return {
        "meta": genmeta.build_meta(
            "evidence-gap-profile",
            [paths.REPO_ROOT / f for f in model["meta"]["source_files"]], now),
        "opportunity_id": opp_id,
        "name": model.get("name", ""),
        "evidence_base": {
            "supporting_ev_records": len(all_supporting),
            "assumptions_total": counts["total_assumptions"],
            "assumptions_open": counts["unresolved"],
            "assumptions_without_evidence": counts["no_supporting_evidence"],
            "assumptions_contradicted": counts["contradicted"],
            "assumption_count": model["score"]["assumption_count"],
            "assumption_cap": model["score"]["assumption_cap"],
            "assumption_capped": capped,
            "assumptions_to_lift_cap": max(0, model["score"]["assumption_count"] - model["score"]["assumption_cap"]),
            "stale_load_bearing_ev": [s["ev_id"] for s in stale_load_bearing],
        },
        "ranking_method": {
            "type": "heuristic (not statistically objective) — reuses impact.gaps weights",
            "weights": {"importance": gaps.IMPORTANCE_W, "status": gaps.STATUS_W,
                        "confidence": gaps.CONF_W, "cap_bonus": 1, "ease_bonus": 1,
                        "stale_load_bearing_bonus": STALE_BONUS},
            "bands": {"critical": ">=7", "high": "5-6", "medium": "3-4", "low": "<=2"},
            "signals": list(SIGNALS),
        },
        "weak_links": weak_links,
    }


def _load_card(opp_id):
    import json
    return json.loads(tracker.scorecard_path(opp_id).read_text(encoding="utf-8"))


def render_markdown(profile, top=None):
    eb = profile["evidence_base"]
    lines = [
        f"# Evidence-gap profile — {profile['opportunity_id']} {profile['name']}".rstrip(),
        "",
        f"- Supporting Part A records: **{eb['supporting_ev_records']}** · "
        f"assumptions {eb['assumptions_total']} (open **{eb['assumptions_open']}**, "
        f"no-evidence {eb['assumptions_without_evidence']}, contradicted {eb['assumptions_contradicted']})",
        f"- Assumption cap: {eb['assumption_count']}/{eb['assumption_cap']}"
        + (f" — CAPPED; {eb['assumptions_to_lift_cap']} to lift" if eb["assumption_capped"] else " — not capped"),
    ]
    if eb["stale_load_bearing_ev"]:
        lines.append(f"- Stale load-bearing evidence (>180d): {', '.join(eb['stale_load_bearing_ev'])}")
    lines += ["", "_Ranking is heuristic (reuses impact.gaps weights); every input is shown._", "",
              "| # | Band | Assumption | Signals | Priority | Reasons |",
              "|---|---|---|---|---|---|"]
    links = profile["weak_links"][:top] if top else profile["weak_links"]
    for g in links:
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            g["priority_rank"], g["priority_band"], g["assumption_id"],
            ", ".join(g["signals"]), g["priority_score"], "; ".join(g["reasons"])))
    return "\n".join(lines) + "\n"
