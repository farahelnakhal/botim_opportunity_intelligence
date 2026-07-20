"""Diff-to-email for scheduled monitoring (Phase R6, PR6c) — PURE and offline-
testable: no store, no network, no send. The tick resolves claims and versions,
calls `evaluate` to decide materiality, and — only when material — `render` to
build the email body, then hands it to the `shared/email` sender.

Design (see docs/decision-log.md, 2026-07-19 "R6 diff-to-email"):

- Materiality reuses `compare_versions` for the composite delta, then layers a
  claim-TEXT diff on top: every build mints fresh RCAND- ids, so a raw id diff
  is always "all new" and would spam. We compare NORMALIZED claim text instead.
- Material iff there is >=1 genuinely new claim text OR the preliminary
  composite moved by >= COMPOSITE_MATERIAL_THRESHOLD. Gap-set changes alone
  (provider flapping) are never material. A degraded run (research failed /
  partial / skipped) is never material.
- The rendered body is honest: everything is labelled PRELIMINARY, each claim
  carries its current review status, numbers are never restated as validated,
  and an overclaim guard (same discipline as impact/email.py) aborts the render
  rather than ever emailing an overclaim.
"""

import re

from shared.workspace import compare_versions

# 0.01 is the smallest meaningful unit at the scoring engine's current
# two-decimal composite precision — a move smaller than this is rounding noise,
# not a product-relevant change. (Bare-constant justification, per decision log.)
COMPOSITE_MATERIAL_THRESHOLD = 0.01

# gap markers that mean the analysis chain did NOT fully run — a degraded/
# partial result we must not present as an "update".
DEGRADED_MARKERS = ("external research failed", "external research was partial",
                    "external research skipped")

# affirmative overclaims that must NEVER appear in a monitoring email — reused
# discipline from impact/email.py, extended with monitoring-specific wording.
OVERCLAIMS = (
    "product validated", "opportunity validated", "product selected",
    "ready to launch", "launch approved", "build approved",
    "confirmed finding", "verified finding", "validated finding",
)


class DigestError(Exception):
    """Raised when the rendered body fails the overclaim guard — a fail-safe
    that aborts the send rather than emailing an overclaim."""


def _normalize(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _composite(version):
    score = (version or {}).get("preliminary_score") or {}
    return score.get("composite")


def is_degraded(version):
    gaps = (version or {}).get("gaps") or []
    return any(marker in gap for gap in gaps for marker in DEGRADED_MARKERS)


def evaluate(baseline_version, new_version, baseline_claims, new_claims):
    """Decide whether the new version is a MATERIAL change over the baseline.

    `baseline_claims`/`new_claims` are lists of {'id','claim','status'} resolved
    from the research store by the caller. Returns a dict with `material`,
    `degraded`, `reason`, the surviving `new_claims`, and composite figures.
    Never sends or renders anything."""
    if is_degraded(new_version):
        return {"material": False, "degraded": True, "reason": "partial",
                "new_claims": [], "composite_before": _composite(baseline_version),
                "composite_after": _composite(new_version), "composite_delta": None}

    diff = compare_versions(baseline_version, new_version)   # reuse the one diff
    base_texts = {_normalize(c.get("claim")) for c in (baseline_claims or [])}
    new_items = [c for c in (new_claims or [])
                 if c.get("status") != "rejected"
                 and _normalize(c.get("claim")) and _normalize(c.get("claim")) not in base_texts]
    delta = diff.get("composite_delta")
    composite_moved = delta is not None and abs(delta) >= COMPOSITE_MATERIAL_THRESHOLD
    material = bool(new_items) or composite_moved
    reason = ("new_claims" if new_items
              else "composite_move" if composite_moved else "no_change")
    return {"material": material, "degraded": False, "reason": reason,
            "new_claims": new_items, "composite_before": diff.get("composite_before"),
            "composite_after": diff.get("composite_after"),
            "composite_delta": delta}


def _claim_label(status):
    if status == "approved":
        return "[approved by a reviewer — still preliminary evidence]"
    return "[pending review — not confirmed]"


def _guard(text):
    low = text.lower()
    for phrase in OVERCLAIMS:
        if phrase in low:
            raise DigestError(f"monitoring email overclaim rejected: '{phrase}'")
    return text


def render(opp, baseline_version, new_version, evaluation,
           workspace_url, unsubscribe_url):
    """Build the monitoring digest email {'subject','text_body'} for a MATERIAL
    change. Everything is labelled preliminary; the body passes the overclaim
    guard before it is returned (a trip raises DigestError — no send)."""
    if not evaluation.get("material"):
        raise DigestError("render called for a non-material change")
    title = opp.get("title") or opp.get("id") or "this opportunity"
    lines = [
        f'Scheduled monitoring re-ran the preliminary analysis for "{title}" and '
        "found changes since the version you last saw.",
        "",
        "IMPORTANT: nothing below is validated. Every item is machine-generated "
        "and PRELIMINARY until a human reviews it. This is a notification, not an "
        "approval — no decision has been made.",
        "",
        f"Changes since analysis v{baseline_version.get('version')} → "
        f"v{new_version.get('version')} ({new_version.get('completed_at')}):",
    ]

    new_items = evaluation.get("new_claims") or []
    if new_items:
        lines += ["", "New preliminary claims to review:"]
        for c in new_items:
            lines.append(f'  - "{c.get("claim")}"   {_claim_label(c.get("status"))}')

    delta = evaluation.get("composite_delta")
    if delta is not None and abs(delta) >= COMPOSITE_MATERIAL_THRESHOLD:
        lines += [
            "",
            f"Preliminary machine score: {evaluation.get('composite_before')} → "
            f"{evaluation.get('composite_after')}",
            '  (17-dimension engine on an all-assumption card; capped at '
            '"promising", low confidence — this is not a validated score.)',
        ]

    gaps = (new_version.get("gaps") or [])
    if gaps:
        lines += ["", "Open gaps in this analysis (missing information, not findings):"]
        lines += [f"  - {g}" for g in gaps]

    lines += [
        "",
        "Review the full analysis — sources, logic, and every label — here:",
        f"  {workspace_url}",
        "",
        "—",
        "You confirmed monitoring email for this opportunity.",
        f"Unsubscribe: {unsubscribe_url}",
        "",
    ]
    body = _guard("\n".join(lines))
    subject = f"[Monitoring] New preliminary changes to review — {title}"
    return {"subject": subject, "text_body": body}
