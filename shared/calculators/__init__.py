"""Deterministic calculators — shared runtime layer (Phase C1).

Pure, side-effect-free, fully-shown-working arithmetic exposed at request time
(executive API + copilot) with the honesty discipline of the offline engine.
The `CALC-` persistence store lives in `store.py`; the pure engine here never
touches a database.
"""

from .base import CalculatorError, InputSpec, LABELS, LABEL_NAMES, worst_label
from .calculators import REGISTRY, ENGINE_VERSION, catalog, compute, Calculator
from .render import render_markdown
from .store import CalculatorStore, CALC_RE

__all__ = [
    "CalculatorError", "InputSpec", "LABELS", "LABEL_NAMES", "worst_label",
    "REGISTRY", "ENGINE_VERSION", "catalog", "compute", "Calculator",
    "render_markdown", "CalculatorStore", "CALC_RE",
]
