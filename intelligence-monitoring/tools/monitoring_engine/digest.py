"""Digest compilation: ranked, thread-collapsed, executive-format markdown.

Digests are intelligence artefacts — they are written into
knowledge-base/monitoring/digests/ and committed, so the alert history is as
auditable as everything else in this repo (DESIGN.md §17 open question,
resolved: yes, auto-commit)."""

from collections import Counter

from .significance import TIERS

TIER_ICON = {"critical": "🔴", "important": "🟠", "informative": "·", "insignificant": ""}
INTERNAL_SIGNALS_CUSTOMER = (
    "new_evidence_record", "evidence_score_change", "evidence_status_change",
    "segment_confidence_change", "new_segment", "ve_verdict_conclusive",
    "ve_observations_progress", "new_experiment",
)


def _rank(e):
    return (-TIERS.index(e["tier"]), -e["scores"]["impact"], e["id"])


def compile_digest(week, events, period="weekly"):
    """Render the digest markdown for a set of events (already filtered to period)."""
    notified = [e for e in events if e["tier"] != "insignificant"]
    notified.sort(key=_rank)
    counts = Counter(e["tier"] for e in events)

    customer = [e for e in notified if e["signal_type"] in INTERNAL_SIGNALS_CUSTOMER]
    portfolio = [e for e in notified if e["signal_type"] in
                 ("new_opportunity", "opportunity_reclassified", "prediction_resolved",
                  "new_inflection_point", "ip_status_change")]
    competitor = [e for e in notified if e["adapter"] != "kb-watcher"]

    headline = notified[0]["title"] if notified else "no notifiable events"
    lines = [
        f"# Intelligence Digest — {week} ({period})",
        "",
        f"**{counts.get('critical', 0)} critical · {counts.get('important', 0)} important · "
        f"{counts.get('informative', 0)} informative** — headline: {headline}",
        "",
    ]

    for e in [x for x in notified if x["tier"] == "critical"]:
        lines += [f"## 🔴 CRITICAL — {e['title']}",
                  f"- Event {e['id']} · {e['entity']} · detected {e['detected_at']} via {e['adapter']}",
                  f"- Scores: impact {e['scores']['impact']}, urgency {e['scores']['urgency']}, "
                  f"confidence {e['scores']['confidence']}",
                  f"- Links: {', '.join(e.get('kb_links', [])) or '—'}",
                  ""]

    def section(title, items):
        if not items:
            return
        lines.append(f"## {title} ({len(items)})")
        lines.append("")
        for e in items:
            lines.append(f"- {TIER_ICON[e['tier']]} **{e['title']}** ({e['id']}, {e['tier']})")
        lines.append("")

    section("Customer intelligence changes", customer)
    section("Portfolio & judgment changes", portfolio)
    section("Competitor moves", competitor)

    insignificant = counts.get("insignificant", 0)
    lines += [f"*{len(events)} events processed; {insignificant} insignificant (archived, not shown). "
              "Tiers are computed mechanically — see intelligence-monitoring/frameworks/significance-scoring.md.*"]
    return "\n".join(lines) + "\n"
