"""17-dimension opportunity scorecard: validation, caps, floors.

Implements opportunity-intelligence/frameworks/opportunity-scoring.md.
The engine does NOT classify (the stress test does, with human judgement);
it validates scores, computes the indicative composite, applies the
assumption-load cap, raises critical-dimension flags, and checks a proposed
classification against the cap.

Input JSON schema (see knowledge-base/opportunity-scores/*-scorecard.json):

{
  "opportunity_id": "OPP-001",
  "name": "...",
  "is_lending_product": true,
  "proposed_classification": "promising",   # strong|promising|weak|reject
  "evidence_confidence": "low",             # high|medium|low
  "scores": {
    "<dimension>": {"score": 1..5, "assumption": true|false, "basis": "EV-... or rationale"},
    ...all 17...
  }
}
"""

from .commercial import InputError

DIMENSIONS = (
    "pain_severity",
    "pain_frequency",
    "financial_impact",
    "workaround_cost",
    "switching_intent",
    "willingness_to_pay",
    "digital_readiness",
    "payment_volume",
    "credit_need",
    "botim_distribution_advantage",
    "transaction_data_advantage",
    "payment_revenue_potential",
    "lending_revenue_potential",
    "credit_risk_visibility",
    "competitive_defensibility",
    "ease_of_validation",
    "mvp_feasibility_7wk",
)

CLASSIFICATIONS = ("strong", "promising", "weak", "reject")
ASSUMPTION_CAP = 6  # >6 of 17 assumption-based scores caps classification at "promising"


def evaluate(card):
    """Validate a scorecard dict and return an evaluation dict."""
    for key in ("opportunity_id", "scores"):
        if key not in card:
            raise InputError(f"scorecard missing top-level key '{key}'")

    scores = card["scores"]
    missing = [d for d in DIMENSIONS if d not in scores]
    if missing:
        raise InputError(
            f"scorecard missing {len(missing)} of 17 dimensions: {', '.join(missing)} "
            "(all 17 individual scores are mandatory — a composite alone is never valid)"
        )
    unknown = [d for d in scores if d not in DIMENSIONS]
    if unknown:
        raise InputError(f"unknown dimensions: {', '.join(unknown)}")

    parsed = {}
    for dim in DIMENSIONS:
        entry = scores[dim]
        if not isinstance(entry, dict) or "score" not in entry:
            raise InputError(f"dimension '{dim}': expected {{score, assumption, basis}}")
        s = entry["score"]
        if not isinstance(s, int) or isinstance(s, bool) or not 1 <= s <= 5:
            raise InputError(f"dimension '{dim}': score must be an integer 1..5 (no half points), got {s!r}")
        parsed[dim] = {
            "score": s,
            "assumption": bool(entry.get("assumption", True)),
            "basis": str(entry.get("basis", "")),
        }

    assumption_count = sum(1 for e in parsed.values() if e["assumption"])
    composite = round(sum(e["score"] for e in parsed.values()) / len(DIMENSIONS), 1)

    # critical-dimension floors -> flags for stress-test scrutiny
    flags = []
    if parsed["pain_severity"]["score"] <= 2:
        flags.append("pain_severity <= 2")
    if parsed["switching_intent"]["score"] <= 2:
        flags.append("switching_intent <= 2")
    if card.get("is_lending_product", True) and parsed["credit_risk_visibility"]["score"] <= 2:
        flags.append("credit_risk_visibility <= 2 on a lending product")
    if parsed["mvp_feasibility_7wk"]["score"] == 1:
        flags.append("mvp_feasibility_7wk == 1")

    capped = assumption_count > ASSUMPTION_CAP
    max_classification = "promising" if capped else "strong"

    violations = []
    proposed = card.get("proposed_classification")
    if proposed is not None:
        if proposed not in CLASSIFICATIONS:
            raise InputError(f"proposed_classification must be one of {CLASSIFICATIONS}, got {proposed!r}")
        if capped and proposed == "strong":
            violations.append(
                f"classification 'strong' not allowed: {assumption_count}/17 scores are assumption-based "
                f"(cap is {ASSUMPTION_CAP}); maximum is 'promising' (but unvalidated)"
            )

    return {
        "opportunity_id": card["opportunity_id"],
        "scores": parsed,
        "composite_indicative": composite,
        "assumption_count": assumption_count,
        "assumption_capped": capped,
        "max_classification": max_classification,
        "critical_flags": flags,
        "proposed_classification": proposed,
        "violations": violations,
        "evidence_confidence": card.get("evidence_confidence"),
    }


def render_markdown(card, ev):
    lines = [
        f"# Computed scorecard — {ev['opportunity_id']} {card.get('name', '')}".rstrip(),
        "",
        "| Dimension | Score | (A)? | Basis |",
        "|---|---|---|---|",
    ]
    for dim in DIMENSIONS:
        e = ev["scores"][dim]
        lines.append(
            f"| {dim} | {e['score']} | {'A' if e['assumption'] else ''} | {e['basis']} |"
        )
    lines += [
        "",
        f"- Composite (indicative only, shown last): **{ev['composite_indicative']}**",
        f"- Assumption-based scores: **{ev['assumption_count']}/17**"
        + (f" → classification capped at 'promising'" if ev["assumption_capped"] else ""),
        f"- Critical-dimension flags: {'; '.join(ev['critical_flags']) or 'none'}",
        f"- Evidence confidence: {ev['evidence_confidence'] or 'not stated'}",
        f"- Proposed classification: {ev['proposed_classification'] or 'not stated'}"
        + (" — **VIOLATIONS: " + "; ".join(ev["violations"]) + "**" if ev["violations"] else " — consistent with caps"),
    ]
    return "\n".join(lines) + "\n"
