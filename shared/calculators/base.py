"""Deterministic calculator engine — shared runtime layer (Phase C1).

Pure, side-effect-free arithmetic with fully **shown working**. Each calculator
declares its inputs and computes a typed dataflow of steps; the engine both
*evaluates* the steps AND *renders* their display strings from the same
structure, so the shown working can never diverge from the computed number.

Honesty invariants (see docs/decision-log.md, the C1 entry):
- **No fabrication.** A calculation over ASSUMED inputs is stamped illustrative /
  preliminary — never a validated market size. Missing required input -> error;
  divide-by-zero -> an honest "never" (a meaningful non-positive denominator) or
  "undefined" (a pure ratio), never a silent 0 or infinity.
- **Determinism.** Pure arithmetic over ORDERED operands; no randomness, no
  wall-clock in results. Raw floats are computed and stored; display formatting
  is a separate presentation step and is NEVER fed back into computation.
- **Provenance.** Every input carries an F/E/A label (Fact / Estimate /
  Assumption), replicating the discipline of
  opportunity-intelligence/tools/opportunity_engine/commercial.py::_norm.
  `shared/` must not import UP into `opportunity-intelligence/`, so the ~14 lines
  are replicated here on purpose. Labels propagate worst-of through each step, so
  the "illustrative" stamp is *derived*, not hand-set. A reserved per-input
  `source_id` field is the C2 hook (accepted, unused in C1).

This module imports nothing from the app, the copilot, or the engines — it is the
bottom layer.
"""

import math
from dataclasses import dataclass, field

# ---- provenance labels ------------------------------------------------------ #

LABELS = ("F", "E", "A")           # Fact, Estimate, Assumption
_LABEL_RANK = {"F": 0, "E": 1, "A": 2}   # higher rank == weaker == "worse"
LABEL_NAMES = {"F": "fact", "E": "estimate", "A": "assumption"}

# ---- bounds ----------------------------------------------------------------- #

MAX_MAGNITUDE = 1e15               # reject absurd inputs (and results) outright
NOTE_MAX = 500
SOURCE_ID_MAX = 64
MAX_INPUTS = 40                    # guard against oversized payloads


class CalculatorError(Exception):
    """Safe, structured error — `status` maps straight to an HTTP status; the
    message never contains a stack trace, SQL, or paths."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def worst_label(labels):
    """Worst-of propagation: any Assumption makes the result an assumption."""
    ranked = [l for l in labels if l in _LABEL_RANK]
    if not ranked:
        return "A"
    return max(ranked, key=lambda l: _LABEL_RANK[l])


# ---- input specs ------------------------------------------------------------ #

@dataclass(frozen=True)
class InputSpec:
    """Declared input. `kind` disambiguates fraction-vs-percent so a share is
    never silently divided by 100."""
    name: str
    unit: str
    kind: str = "number"           # number | integer | currency | fraction | percent | multiplier | bps
    required: bool = True
    description: str = ""
    min: float = None
    max: float = None

    def as_dict(self):
        return {
            "name": self.name, "unit": self.unit, "kind": self.kind,
            "required": self.required, "description": self.description,
            "min": self.min, "max": self.max,
        }


def _as_number(raw, name):
    if isinstance(raw, bool):
        raise CalculatorError(f"input '{name}': expected a number, got a boolean")
    if not isinstance(raw, (int, float)):
        raise CalculatorError(f"input '{name}': expected a number, got {type(raw).__name__}")
    v = float(raw)
    if not math.isfinite(v):
        raise CalculatorError(f"input '{name}': must be a finite number")
    if abs(v) > MAX_MAGNITUDE:
        raise CalculatorError(f"input '{name}': magnitude too large (must be <= {MAX_MAGNITUDE:g})")
    return v


def _norm(raw, name):
    """Normalise a raw input to {value, label, note, source_id}. A bare number
    defaults to an Assumption; the {value,label,note} form carries provenance.
    Mirrors commercial.py::_norm (kept local — shared/ never imports up)."""
    if isinstance(raw, dict):
        if "value" not in raw:
            raise CalculatorError(f"input '{name}': object form needs a numeric 'value'")
        value = _as_number(raw["value"], name)
        label = str(raw.get("label", "A")).upper()
        if label not in LABELS:
            raise CalculatorError(f"input '{name}': label must be F, E or A, got {label!r}")
        note = raw.get("note", "")
        if not isinstance(note, str):
            raise CalculatorError(f"input '{name}': note must be a string")
        if len(note) > NOTE_MAX:
            raise CalculatorError(f"input '{name}': note exceeds {NOTE_MAX} characters")
        source_id = raw.get("source_id")   # reserved for C2 traceability; accepted, unused
        if source_id is not None and (not isinstance(source_id, str) or len(source_id) > SOURCE_ID_MAX):
            raise CalculatorError(f"input '{name}': source_id must be a short string")
        return {"value": value, "label": label, "note": note.strip(), "source_id": source_id}
    return {"value": _as_number(raw, name), "label": "A", "note": "", "source_id": None}


def _check_spec(spec, norm):
    v = norm["value"]
    if spec.kind == "fraction" and not (0.0 <= v <= 1.0):
        raise CalculatorError(
            f"input '{spec.name}' must be a fraction between 0 and 1 "
            f"(a share, not a percent); got {_trim(v)}")
    if spec.kind == "integer" and v != int(v):
        raise CalculatorError(f"input '{spec.name}' must be a whole number; got {_trim(v)}")
    if spec.min is not None and v < spec.min:
        raise CalculatorError(f"input '{spec.name}' must be >= {_trim(spec.min)}; got {_trim(v)}")
    if spec.max is not None and v > spec.max:
        raise CalculatorError(f"input '{spec.name}' must be <= {_trim(spec.max)}; got {_trim(v)}")


# ---- typed step evaluation -------------------------------------------------- #

OP_SYMBOL = {"add": "+", "sub": "−", "mul": "×", "div": "÷", "pow": "^"}


def _apply_op(op, values):
    if op == "add":
        total = 0.0
        for v in values:
            total += v
        return total
    if op == "mul":
        prod = 1.0
        for v in values:
            prod *= v
        return prod
    if op == "sub":
        acc = values[0]
        for v in values[1:]:
            acc -= v
        return acc
    if op == "div":
        num, den = values
        if den == 0:
            # calculators pre-guard non-positive denominators into an honest
            # "never"/"undefined" output; reaching here is a bug, not a 0.
            raise CalculatorError("internal: division by zero reached the evaluator", status=500)
        return num / den
    if op == "pow":
        base, exp = values
        try:
            return float(base) ** float(exp)
        except (ValueError, OverflowError):
            raise CalculatorError("internal: undefined power reached the evaluator", status=500)
    raise CalculatorError(f"internal: unknown op {op!r}", status=500)


def _close(a, b):
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


class Working:
    """Accumulates the typed dataflow. Quantities are inputs and prior step
    outputs; a step evaluates an op over ordered operands and records both the
    raw result and the strings rendered from the same structure."""

    def __init__(self, inputs):
        self.inputs = inputs                    # name -> normalized dict
        self._q = {name: {"value": n["value"], "label": n["label"], "unit": None}
                   for name, n in inputs.items()}
        self.steps = []
        self.outputs = {}
        self.warnings = []

    def value(self, name):
        return self._q[name]["value"]

    def _resolve(self, ref):
        if isinstance(ref, str):
            q = self._q[ref]
            return {"ref": ref, "value": q["value"], "label": q["label"]}
        # a literal constant is an exact Fact
        return {"ref": _trim(ref), "value": float(ref), "label": "F", "const": True}

    def step(self, output, op, refs, unit, expression, kind="number", note=None):
        operands = [self._resolve(r) for r in refs]
        result = _apply_op(op, [o["value"] for o in operands])
        if abs(result) > MAX_MAGNITUDE:
            raise CalculatorError(
                f"result '{output}' magnitude too large — check the inputs", status=400)
        label = worst_label([o["label"] for o in operands])
        rec = {
            "output": output, "op": op, "operands": operands,
            "result": result, "result_display": _fmt(result, kind),
            "label": label, "unit": unit, "kind": kind,
            "expression": expression,
            "substituted": _substituted(op, operands, kind),
        }
        if note:
            rec["note"] = note
        self.steps.append(rec)
        self._q[output] = {"value": result, "label": label, "unit": unit}
        return result

    def output(self, key, quantity, kind="number", note=None):
        q = self._q[quantity]
        rec = {"value": q["value"], "label": q["label"], "unit": q["unit"],
               "kind": kind, "display": _fmt(q["value"], kind)}
        if note:
            rec["note"] = note
        self.outputs[key] = rec

    def output_undefined(self, key, unit, reason, state="undefined"):
        """An honest non-numeric output: 'never' (meaningful non-positive
        denominator) or 'undefined' (a pure ratio with no meaningful value)."""
        self.outputs[key] = {"value": None, "label": "A", "unit": unit,
                             "kind": state, "display": state, "reason": reason}

    def warn(self, message):
        if message not in self.warnings:
            self.warnings.append(message)


# ---- display formatting (presentation only — never fed back) ---------------- #

def _trim(v):
    """Compact number for messages/operand refs."""
    if v is None:
        return "—"
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return f"{int(v):g}"
    return f"{v:g}"


def _fmt(value, kind):
    if value is None:
        return "—"
    if kind == "percent":                       # value is a fraction
        return f"{value * 100:,.2f}%"
    if kind == "bps":
        return f"{value:,.0f} bps"
    if kind == "ratio" or kind == "multiplier":
        return f"{value:,.4f}"
    if kind in ("integer", "count"):
        return f"{value:,.0f}"
    if kind in ("years", "months"):
        return f"{value:,.2f}"
    if kind == "currency":
        if float(value).is_integer():
            return f"{value:,.0f}"
        return f"{value:,.2f}"
    # generic number
    if float(value).is_integer() and abs(value) < 1e15:
        return f"{value:,.0f}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def _fmt_operand(o, kind):
    # operand display uses a neutral numeric format (its own magnitude), not the
    # step's output kind, so e.g. a fraction operand shows 0.2 not 20%.
    v = o["value"]
    if o.get("const"):
        return _trim(v)
    if float(v).is_integer() and abs(v) < 1e15:
        return f"{v:,.0f}"
    return f"{v:g}"


def _substituted(op, operands, kind):
    parts = [_fmt_operand(o, kind) for o in operands]
    sym = f" {OP_SYMBOL[op]} "
    if op == "pow":
        return f"{parts[0]} ^ {parts[1]}"
    return sym.join(parts)
