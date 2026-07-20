"""Wording validation for model prose (reuses the impact overclaim list).

Returns the violating phrase (so the orchestrator can fall back to the
deterministic grounded text and add a warning) or None. It validates; it does
not silently rewrite authoritative numbers or classifications.
"""

import re
import sys

from .config import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))
from impact.wording import OVERCLAIMS  # noqa: E402

_EXTRA = ("management approved", "board approved", "we have selected",
          "the product has been chosen", "green-lit", "greenlit",
          # Merchant Voice (Phase 5) overclaims — a research signal is never
          # a proof of demand, and a concept reaction is never proof of
          # willingness to pay.
          "market validated", "demand is validated", "demand validated",
          "merchants will pay", "merchant demand is validated", "ready to build",
          # New-opportunity analysis (Phase 2) — a brand-new idea has no
          # scorecard and no committed evidence; these are never true of it.
          "proven demand", "demand is proven", "proven the demand")


def check_wording(text):
    low = (text or "").lower()
    for phrase in tuple(OVERCLAIMS) + _EXTRA:
        if phrase in low:
            return phrase
    return None


# Phase C1 — numeric-fidelity guard for deterministic-calculation answers.
# The calculator computes every number and grounding renders them into the
# facts block; the model may only NARRATE those numbers, never compute. Any
# large figure (>= 1000, i.e. a computed output — not a year, a small count,
# or a percent) that appears in the prose but not in the grounded facts is a
# fabricated/miscopied number: the orchestrator falls back to the exact facts.
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _canonical_numbers(text):
    out = set()
    for tok in _NUM.findall(text or ""):
        digits = tok.replace(",", "").split(".")[0]
        out.add(digits.lstrip("0") or "0")
    return out


def check_numeric_fidelity(prose, facts_block):
    """Return the first prose number (>= 4 integer digits) that is absent from
    the grounded facts, or None. Small numbers are ignored — they are
    restatements of years / small counts / percentages, not computed outputs."""
    allowed = _canonical_numbers(facts_block)
    for tok in _NUM.findall(prose or ""):
        digits = (tok.replace(",", "").split(".")[0]).lstrip("0") or "0"
        if len(digits) >= 4 and digits not in allowed:
            return tok
    return None
