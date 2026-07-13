"""Wording discipline for the executive brief.

Distinguishes fact / inference / assumption / hypothesis, rejects affirmative
overclaims, and requires the bounded no-decision statement when an opportunity
is promising-but-unvalidated.
"""

from .errors import ImpactError

LABELS = ("fact", "inference", "assumption", "hypothesis")

OVERCLAIMS = (
    "product validated", "opportunity validated", "validated opportunity",
    "product selected", "opportunity selected", "ready to launch",
    "launch approved", "build approved",
)
NO_DECISION_LINE = "No product or build decision has been made."


def label(kind, text):
    if kind not in LABELS:
        raise ImpactError(f"unknown claim label '{kind}'")
    return f"[{kind}] {text}"


def guard(text, promising_unvalidated):
    low = text.lower()
    for phrase in OVERCLAIMS:
        if phrase in low:
            raise ImpactError(f"brief overclaim rejected: '{phrase}'")
    if promising_unvalidated and NO_DECISION_LINE not in text:
        raise ImpactError("promising-but-unvalidated brief must include the no-decision statement")
    return text
