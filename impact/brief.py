"""Executive Decision Brief — Markdown, JSON (UI envelope) and terminal, all
rendered from one normalized view object (guaranteed substantive parity).

Consumes (read-only): scorecard + engine evaluate, segment profile, cited EV
records, IP records, the assumption read model, score history, monitoring
summaries and validation experiments. Never recomputes scores, upgrades
evidence, invents demand, modifies sources, or applies impacts.
"""

import json
import re
from pathlib import Path

from . import genmeta, paths, tracker, uicontract, wording

EV_RE = tracker.EV_RE
SEG_RE = tracker.SEG_RE
IP_RE = tracker.IP_RE


def _read_segment(seg_id):
    p = paths.KB / "segments" / f"{seg_id}.md"
    if not p.exists():
        return None
    t = p.read_text(encoding="utf-8")
    title = ""
    m = re.search(r"^#\s+(.+)$", t, re.M)
    if m:
        title = m.group(1).split("—", 1)[-1].strip()
    conf = None
    mc = re.search(r"\*\*Confidence:\*\*\s*([A-Za-z]+)", t)
    if mc:
        conf = mc.group(1)
    job = ""
    mj = re.search(r"Main jobs-to-be-done\s*\|\s*(.+?)\s*\|", t)
    if mj:
        job = mj.group(1).strip()
    return {"segment_id": seg_id, "title": title, "confidence": conf, "job": job, "path": p}


def _ip_titles(ip_ids):
    out = {}
    for ip in ip_ids:
        p = paths.KB / "inflection-points" / f"{ip}.md"
        if p.exists():
            m = re.search(r"^#\s+(.+)$", p.read_text(encoding="utf-8"), re.M)
            out[ip] = m.group(1) if m else ip
    return out


def _recent_changes(opp_id):
    from . import history
    out = []
    for e in history.read_all():
        if e.get("opportunity_id") == opp_id:
            out.append({"source": "score-history", "history_id": e.get("history_id"),
                        "kind": e.get("kind"), "timestamp": e.get("timestamp"),
                        "summary": e.get("explanation", "")})
    mon = paths.MONITORING_DIR / f"{opp_id.lower()}-summary.md"
    if mon.exists():
        out.append({"source": "impact-monitoring", "path": str(mon.relative_to(paths.REPO_ROOT))})
    return out


def build_view(opp_id, now):
    scoring, evidence = paths.load_engine()
    model = tracker.build(opp_id, now)
    card = json.loads(tracker.scorecard_path(opp_id).read_text(encoding="utf-8"))
    ev = scoring.evaluate(card)
    records = evidence.load_records(paths.KB / "customer-evidence")

    basis_text = " ".join(e.get("basis", "") for e in card["scores"].values())
    cited = sorted(set(EV_RE.findall(basis_text)))
    cite = evidence.check_citations(cited, records)
    weak = set(cite["weak"])
    supporting_primary = [i for i in cite["valid"] if i not in weak]
    supporting_leads = list(cite["weak"])
    detail = {i: {"confidence": (records.get(i, {}).get("evidence_confidence", "") or "").split("—")[0].strip(),
                  "title": records.get(i, {}).get("title", "")} for i in cited if i in records}

    seg_ids = sorted(set(SEG_RE.findall(basis_text)))
    segment = next((s for s in (_read_segment(x) for x in seg_ids) if s), None)
    ip_ids = sorted(set(IP_RE.findall(basis_text)))
    ip_titles = _ip_titles(ip_ids)

    contradicting = sorted({c for a in model["assumptions"] for c in a["contradicting_ev"]})

    conf_dist = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
    for i in cited:
        tok = (records.get(i, {}).get("evidence_confidence", "") or "").split("—")[0].strip().lower()
        conf_dist[tok if tok in conf_dist else "unknown"] += 1

    related_ve = sorted({v for a in model["assumptions"] for v in a["related_ve"]})
    primary_ve = related_ve[0] if related_ve else None
    classification = card.get("proposed_classification")
    promising_unvalidated = classification in ("promising", None)

    raw = model["score"]["raw"]
    comm_model = paths.KB / "commercial-models" / f"{opp_id.lower()}-inputs.json"

    next_text = (f"Run {primary_ve} before any product build decision."
                 if primary_ve else "Define and run a validation experiment before any build decision.")
    decision_text = ("Approve a customer-validation sprint, not product development."
                     if promising_unvalidated else "Review for a scoped go/no-go decision.")

    source_files = [paths.REPO_ROOT / f for f in model["meta"]["source_files"]]
    source_files.append(tracker.scorecard_path(opp_id))
    if segment:
        source_files.append(segment["path"])
    for ip in ip_titles:
        source_files.append(paths.KB / "inflection-points" / f"{ip}.md")

    unresolved_items = [{"assumption_id": a["assumption_id"], "category": a["category"],
                         "status": a["status"], "decision_importance": a["decision_importance"]}
                        for a in model["assumptions"] if a["status"] in ("untested", "partially_supported")]

    risks = list(ev["critical_flags"])
    if card["scores"].get("competitive_defensibility", {}).get("score", 5) <= 2:
        risks.append("competitive_defensibility <= 2 (copyable / funded competitors)")

    return {
        "meta": genmeta.build_meta("executive-brief", source_files, now),
        "opportunity_id": opp_id,
        "name": card.get("name", ""),
        "score": {
            "raw_score": f"{raw}/85", "raw": raw, "raw_max": 85,
            "composite_score": ev["composite_indicative"],
            "assumption_count": ev["assumption_count"],
            "assumption_cap": scoring.ASSUMPTION_CAP,
            "capped": ev["assumption_capped"],
            "classification": classification,
            "critical_flags": ev["critical_flags"],
        },
        "confidence": {
            "segment": {"segment_id": segment["segment_id"] if segment else None,
                        "value": segment["confidence"] if segment else None,
                        "source": "segment profile"},
            "opportunity_assessment": {"value": card.get("evidence_confidence"),
                                       "source": "scorecard.evidence_confidence"},
            "evidence_distribution": {**conf_dist, "source": "cited EV records via Part A parser"},
            "note": "Confidence concepts are exposed separately and never collapsed into one number.",
        },
        "customer": {
            "segment_id": segment["segment_id"] if segment else None,
            "segment_title": segment["title"] if segment else None,
            "segment_confidence": segment["confidence"] if segment else None,
            "job_to_be_done": segment["job"] if segment and segment["job"] else None,
        },
        "supporting_primary": supporting_primary,
        "supporting_leads": supporting_leads,
        "supporting_detail": detail,
        "contradicting": contradicting,
        "inflection_points": ip_titles,
        "assumptions": {
            "total": model["counts"]["total_assumptions"],
            "unresolved": model["counts"]["unresolved"],
            "no_supporting_evidence": model["counts"]["no_supporting_evidence"],
            "contradicted": model["counts"]["contradicted"],
            "items": unresolved_items,
        },
        "recent_changes": _recent_changes(opp_id),
        "commercial": {"has_committed_model": comm_model.exists(),
                       "notes": ("engine-computed model present" if comm_model.exists()
                                 else "no committed commercial model yet")},
        "risks": risks,
        "next_validation": {"ve": primary_ve, "text": next_text},
        "recommended_action": {"ve": primary_ve, "text": next_text},
        "decision_requested": {"text": decision_text,
                               "no_build_decision": wording.NO_DECISION_LINE if promising_unvalidated else None},
        "promising_unvalidated": promising_unvalidated,
        "problems": model["evidence_problems"],
    }


def render_json(view):
    return uicontract.envelope(view)


def render_markdown(view):
    s = view["score"]
    c = view["customer"]
    conf = view["confidence"]
    lines = [
        f"# {view['opportunity_id']} — {view['name']}",
        "",
        f"Raw score: **{s['raw_score']}** · Composite: **{s['composite_score']}** · "
        f"Confidence: {conf['opportunity_assessment']['value']} · "
        f"Classification: **{s['classification']}"
        + (" (capped by assumptions)" if s["capped"] else "") + "**",
        f"Unresolved assumptions: **{view['assumptions']['unresolved']}**",
        "",
        "## Executive summary",
        f"[assumption] {view['opportunity_id']} is *{s['classification']}* and unvalidated: "
        f"{view['assumptions']['unresolved']} of {view['assumptions']['total']} assumptions are unresolved. "
        f"Recommendation: {view['recommended_action']['text']}",
        "",
        "## Customer and job-to-be-done",
        f"- Segment: {c['segment_id']} — {c['segment_title'] or 'n/a'} "
        f"(segment confidence: {c['segment_confidence']})",
        f"- Job-to-be-done: {c['job_to_be_done'] or 'see segment profile'}",
        "",
        "## Opportunity status",
        f"- Classification: {s['classification']}"
        + (" — capped at 'promising' by assumption load" if s["capped"] else ""),
        f"- Critical flags: {', '.join(s['critical_flags']) or 'none'}",
        "",
        "## Evidence supporting the thesis",
        "- Primary (behavioural, not weak): "
        + (", ".join(view["supporting_primary"]) or "none yet"),
        "- Leads / context only (weak — not primary support): "
        + (", ".join(view["supporting_leads"]) or "none"),
        "",
        "## Contradictory evidence",
        "- " + (", ".join(view["contradicting"]) or "none recorded (supporting evidence is preserved regardless)"),
        "",
        "## Score and confidence",
        f"- Raw {s['raw_score']} · composite {s['composite_score']} (engine values, unchanged)",
        f"- Segment confidence: {conf['segment']['value']} (source: {conf['segment']['source']})",
        f"- Opportunity-assessment confidence: {conf['opportunity_assessment']['value']} "
        f"(source: {conf['opportunity_assessment']['source']})",
        f"- Cited-evidence distribution: {conf['evidence_distribution']['high']}H / "
        f"{conf['evidence_distribution']['medium']}M / {conf['evidence_distribution']['low']}L",
        "",
        "## Assumption summary",
        f"- {view['assumptions']['unresolved']} unresolved · "
        f"{view['assumptions']['no_supporting_evidence']} with no supporting evidence · "
        f"{view['assumptions']['contradicted']} contradicted",
        "",
        "## Recent intelligence changes",
    ]
    if view["recent_changes"]:
        for ch in view["recent_changes"]:
            lines.append(f"- {ch}")
    else:
        lines.append("- none recorded since scoring")
    lines += [
        "",
        "## Commercial and operational considerations",
        f"- Committed commercial model: {view['commercial']['notes']}",
        "",
        "## Main risks",
    ]
    lines += [f"- {r}" for r in view["risks"]] or ["- none flagged"]
    lines += [
        "",
        "## Next validation action",
        f"- [inference] {view['next_validation']['text']}",
        "",
        "## Decision requested",
        f"- {view['decision_requested']['text']}",
    ]
    if view["decision_requested"]["no_build_decision"]:
        lines.append(f"- {view['decision_requested']['no_build_decision']}")
    text = "\n".join(lines) + "\n"
    return wording.guard(text, view["promising_unvalidated"])


def render_terminal(view):
    s = view["score"]
    out = [
        f"{view['opportunity_id']} — {view['name']}",
        f"  raw {s['raw_score']} | composite {s['composite_score']} | {s['classification']}"
        + (" (capped)" if s["capped"] else ""),
        f"  unresolved assumptions: {view['assumptions']['unresolved']}/{view['assumptions']['total']}",
        f"  recommendation: {view['recommended_action']['text']}",
        f"  decision requested: {view['decision_requested']['text']}",
    ]
    if view["decision_requested"]["no_build_decision"]:
        out.append(f"  {view['decision_requested']['no_build_decision']}")
    return "\n".join(out) + "\n"
