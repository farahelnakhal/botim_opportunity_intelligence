"""Wording validation for model prose (reuses the impact overclaim list).

Returns the violating phrase (so the orchestrator can fall back to the
deterministic grounded text and add a warning) or None. It validates; it does
not silently rewrite authoritative numbers or classifications.
"""

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
          "merchants will pay", "merchant demand is validated", "ready to build")


def check_wording(text):
    low = (text or "").lower()
    for phrase in tuple(OVERCLAIMS) + _EXTRA:
        if phrase in low:
            return phrase
    return None
