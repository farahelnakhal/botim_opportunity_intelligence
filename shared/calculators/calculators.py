"""The deterministic calculator registry (Phase C1).

Each calculator is a pure spec + function over a `Working` dataflow. Adding a
calculator is a new entry here — no other layer changes. Every formula is fixed
in code: callers supply only numbers, never an expression to evaluate.

The set serves the SME validation case (market sizing, unit economics, a
payments-take calculator that enforces the not-a-bank / net-take-not-gross-MDR
discipline) while staying generic and reusable for any opportunity.
"""

from .base import (
    CalculatorError, InputSpec, Working, _norm, _check_spec, _close,
    _apply_op, worst_label, MAX_INPUTS,
)

# ------------------------------------------------------------------ framework #

ENGINE_VERSION = 1


class Calculator:
    def __init__(self, id, title, description, inputs, fn, version=1, notes=()):
        self.id = id
        self.title = title
        self.description = description
        self.inputs = list(inputs)
        self.fn = fn
        self.version = version
        self.notes = list(notes)

    def spec(self):
        return {
            "id": self.id, "title": self.title, "description": self.description,
            "version": self.version, "notes": self.notes,
            "inputs": [s.as_dict() for s in self.inputs],
        }

    def _normalize(self, raw_inputs):
        if not isinstance(raw_inputs, dict):
            raise CalculatorError("inputs must be an object")
        if len(raw_inputs) > MAX_INPUTS:
            raise CalculatorError(f"too many inputs (max {MAX_INPUTS})")
        allowed = {s.name for s in self.inputs}
        unknown = [k for k in raw_inputs if k not in allowed]
        if unknown:
            raise CalculatorError(f"unknown input(s): {', '.join(sorted(unknown))}")
        norm = {}
        for spec in self.inputs:
            if spec.name not in raw_inputs or raw_inputs[spec.name] is None:
                if spec.required:
                    raise CalculatorError(f"missing required input '{spec.name}' ({spec.unit})")
                continue
            n = _norm(raw_inputs[spec.name], spec.name)
            _check_spec(spec, n)
            norm[spec.name] = n
        return norm

    def compute(self, raw_inputs):
        norm = self._normalize(raw_inputs)
        w = Working(norm)
        self.fn(w, {k: v["value"] for k, v in norm.items()})
        result_label = worst_label([o.get("label", "A") for o in w.outputs.values()] or ["A"])
        envelope = {
            "calculator_id": self.id,
            "calculator_version": self.version,
            "title": self.title,
            "normalized_inputs": norm,
            "steps": w.steps,
            "outputs": w.outputs,
            "warnings": w.warnings,
            "result_label": result_label,
            "disclaimers": _disclaimers(self.id, result_label),
        }
        _self_check(envelope)
        return envelope


def _self_check(envelope):
    """Re-evaluate every step from its own operands and confirm each declared
    output equals the step that produced it. Turns 'formula shown' into 'formula
    verified' — a rendering/typo bug becomes a 500, never a wrong number shown."""
    produced = {}
    for step in envelope["steps"]:
        recomputed = _apply_op(step["op"], [o["value"] for o in step["operands"]])
        if not _close(recomputed, step["result"]):
            raise CalculatorError("internal: step self-check failed", status=500)
        produced[step["output"]] = step["result"]
    for key, out in envelope["outputs"].items():
        if out.get("value") is None:
            continue
        # an output must trace to a produced quantity or an untouched input value
        candidates = list(produced.values()) + [
            n["value"] for n in envelope["normalized_inputs"].values()]
        if not any(_close(out["value"], c) for c in candidates):
            raise CalculatorError("internal: output self-check failed", status=500)


# --------------------------------------------------------------- disclaimers #

_ILLUSTRATIVE = ("Illustrative / preliminary — a calculation over assumed or "
                 "estimated inputs, not a validated figure. Every number is only "
                 "as sound as the inputs shown.")
_NOT_A_BANK = ("This sizes a market opportunity, not BOTIM's right to serve it. "
               "BOTIM is not assumed to be a bank, card issuer, or lender; any "
               "issuer/lender/program-manager/distributor role is a separate, "
               "evidence-gated question.")


def _disclaimers(calc_id, result_label):
    out = []
    if result_label in ("A", "E"):
        out.append(_ILLUSTRATIVE)
    if calc_id in ("market_sizing", "market_sizing_bottomup", "payments_take"):
        out.append(_NOT_A_BANK)
    return out


# ---------------------------------------------------------------- calculators #

def _market_sizing(w, v):
    w.step("tam", "mul", ["population", "annual_value_per_unit"],
           "AED/year", "population × annual_value_per_unit", kind="currency")
    w.step("sam", "mul", ["tam", "serviceable_fraction"],
           "AED/year", "TAM × serviceable_fraction", kind="currency")
    w.step("som", "mul", ["sam", "obtainable_share"],
           "AED/year", "SAM × obtainable_share", kind="currency")
    w.output("tam", "tam", kind="currency", note="total addressable market (annual value)")
    w.output("sam", "sam", kind="currency", note="serviceable available market")
    w.output("som", "som", kind="currency", note="serviceable obtainable market")
    if v["serviceable_fraction"] >= 0.9:
        w.warn("serviceable_fraction >= 0.9 — almost the whole market is assumed serviceable; verify.")
    if v["obtainable_share"] >= 0.5:
        w.warn("obtainable_share >= 0.5 — assumes capturing half or more of the serviceable market; aggressive.")


def _market_sizing_bottomup(w, v):
    w.step("revenue_per_customer", "mul",
           ["units_per_customer_per_year", "price_per_unit"],
           "AED/year", "units_per_customer_per_year × price_per_unit", kind="currency")
    w.step("market_value", "mul", ["num_customers", "revenue_per_customer"],
           "AED/year", "num_customers × revenue_per_customer", kind="currency")
    w.output("revenue_per_customer", "revenue_per_customer", kind="currency")
    w.output("market_value", "market_value", kind="currency",
             note="bottom-up annual market value")


def _growth_projection(w, v):
    w.step("rate_fraction", "div", ["annual_growth_rate_pct", 100],
           "fraction", "annual_growth_rate_pct ÷ 100", kind="ratio")
    w.step("growth_base", "add", ["rate_fraction", 1],
           "ratio", "1 + rate_fraction", kind="ratio")
    w.step("growth_factor", "pow", ["growth_base", "years"],
           "ratio", "growth_base ^ years", kind="ratio")
    w.step("future_value", "mul", ["present_value", "growth_factor"],
           "AED", "present_value × growth_factor", kind="currency")
    w.output("future_value", "future_value", kind="currency")
    w.output("growth_factor", "growth_factor", kind="ratio",
             note="cumulative multiple over the period")


def _implied_cagr(w, v):
    if v["start_value"] <= 0:
        w.output_undefined("cagr", "percent",
                           "start_value must be > 0 to compute a growth rate")
        return
    w.step("total_ratio", "div", ["end_value", "start_value"],
           "ratio", "end_value ÷ start_value", kind="ratio")
    w.step("inv_years", "div", [1, "years"], "1/year", "1 ÷ years", kind="ratio")
    w.step("annual_factor", "pow", ["total_ratio", "inv_years"],
           "ratio", "total_ratio ^ (1 ÷ years)", kind="ratio")
    w.step("cagr", "sub", ["annual_factor", 1], "fraction", "annual_factor − 1", kind="percent")
    w.output("cagr", "cagr", kind="percent", note="compound annual growth rate")


def _adoption_forecast(w, v):
    w.step("adopters", "mul", ["addressable_population", "adoption_rate"],
           "users", "addressable_population × adoption_rate", kind="count")
    w.output("adopters", "adopters", kind="count",
             note="expected adopters in the period")


def _unit_contribution(w, v):
    w.step("contribution", "sub", ["revenue_per_unit", "variable_cost_per_unit"],
           "AED/unit", "revenue_per_unit − variable_cost_per_unit", kind="currency")
    w.output("contribution", "contribution", kind="currency",
             note="contribution per unit")
    if v["revenue_per_unit"] <= 0:
        w.output_undefined("margin", "percent",
                           "revenue_per_unit is 0 — a margin percentage is undefined")
    else:
        w.step("margin", "div", ["contribution", "revenue_per_unit"],
               "fraction", "contribution ÷ revenue_per_unit", kind="percent")
        w.output("margin", "margin", kind="percent", note="contribution margin")
    if w.value("contribution") < 0:
        w.warn("contribution per unit is negative — each unit loses money at these inputs.")


def _breakeven(w, v):
    if v["contribution_per_unit"] <= 0:
        w.output_undefined("breakeven_units", "units",
                           "contribution_per_unit is not positive — break-even is never reached",
                           state="never")
        return
    w.step("breakeven_units", "div", ["fixed_costs", "contribution_per_unit"],
           "units", "fixed_costs ÷ contribution_per_unit", kind="count")
    w.output("breakeven_units", "breakeven_units", kind="count",
             note="units to cover fixed costs")


def _payback_period(w, v):
    if v["monthly_contribution"] <= 0:
        w.output_undefined("payback_months", "months",
                           "monthly_contribution is not positive — the cost is never paid back",
                           state="never")
        return
    w.step("payback_months", "div", ["acquisition_cost", "monthly_contribution"],
           "months", "acquisition_cost ÷ monthly_contribution", kind="months")
    w.output("payback_months", "payback_months", kind="months",
             note="months to recover the acquisition cost")


def _payments_take(w, v):
    w.step("take_fraction", "div", ["net_take_bps", 10000],
           "fraction", "net_take_bps ÷ 10,000", kind="ratio")
    w.step("revenue", "mul", ["routed_flow", "take_fraction"],
           "AED", "routed_flow × take_fraction", kind="currency")
    w.output("revenue", "revenue", kind="currency", note="payments revenue on the routed flow")
    w.warn("net_take_bps must be a NET take (a wallet fee or NET interchange share), "
           "never gross MDR: the accepting merchant pays MDR, and BOTIM never earns the full MDR.")
    if v["net_take_bps"] > 300:
        w.warn("net_take_bps > 300 (3%) exceeds a typical NET payments take — this may be "
               "gross-MDR or interchange-capture framing, which would imply an issuer role. "
               "BOTIM is not assumed to be an issuer; confirm the economics and role.")


REGISTRY = {c.id: c for c in [
    Calculator(
        "market_sizing", "Market sizing (top-down TAM/SAM/SOM)",
        "Top-down annual market value: TAM from population × per-unit value, then "
        "SAM and SOM by serviceable and obtainable shares.",
        [
            InputSpec("population", "units", "count", min=0,
                      description="addressable population / accounts / merchants"),
            InputSpec("annual_value_per_unit", "AED/unit/year", "currency", min=0,
                      description="annual value per unit — annualise before entering"),
            InputSpec("serviceable_fraction", "fraction", "fraction",
                      description="share of TAM that is serviceable (0..1)"),
            InputSpec("obtainable_share", "fraction", "fraction",
                      description="share of SAM realistically obtainable (0..1)"),
        ], _market_sizing,
        notes=["Sizes the market, not BOTIM's right to serve it.",
               "obtainable_share is a market-capture share; it is not an adoption rate."]),
    Calculator(
        "market_sizing_bottomup", "Market sizing (bottom-up)",
        "Bottom-up annual market value from customer count × per-customer revenue.",
        [
            InputSpec("num_customers", "customers", "count", min=0),
            InputSpec("units_per_customer_per_year", "units/year", "number", min=0),
            InputSpec("price_per_unit", "AED/unit", "currency", min=0),
        ], _market_sizing_bottomup,
        notes=["A bottom-up cross-check for the top-down TAM; reconciling the two "
               "is a later (C2) judgment, not attempted here."]),
    Calculator(
        "growth_projection", "Growth projection (forward CAGR)",
        "Compound a present value forward N years at a constant annual rate.",
        [
            InputSpec("present_value", "AED", "currency", min=0),
            InputSpec("annual_growth_rate_pct", "percent", "percent", min=-100,
                      description="annual growth rate in percent (e.g. 12 = 12%)"),
            InputSpec("years", "years", "number", min=0),
        ], _growth_projection),
    Calculator(
        "implied_cagr", "Implied CAGR (from endpoints)",
        "The compound annual growth rate implied by a start value, end value, and period.",
        [
            InputSpec("start_value", "AED", "currency", min=0),
            InputSpec("end_value", "AED", "currency", min=0),
            InputSpec("years", "years", "number", min=0.0001,
                      description="period length in years (> 0)"),
        ], _implied_cagr),
    Calculator(
        "adoption_forecast", "Adoption forecast (single-period)",
        "Expected adopters = addressable population × adoption rate.",
        [
            InputSpec("addressable_population", "users", "count", min=0),
            InputSpec("adoption_rate", "fraction", "fraction",
                      description="share of the addressable population that adopts (0..1)"),
        ], _adoption_forecast,
        notes=["adoption_rate is not the same as market-sizing's obtainable_share; "
               "do not multiply the two without a reason."]),
    Calculator(
        "unit_contribution", "Unit contribution & margin",
        "Contribution per unit and the contribution margin.",
        [
            InputSpec("revenue_per_unit", "AED/unit", "currency", min=0),
            InputSpec("variable_cost_per_unit", "AED/unit", "currency", min=0),
        ], _unit_contribution),
    Calculator(
        "breakeven", "Break-even units",
        "Units needed to cover fixed costs at a given unit contribution.",
        [
            InputSpec("fixed_costs", "AED", "currency", min=0),
            InputSpec("contribution_per_unit", "AED/unit", "currency"),
        ], _breakeven,
        notes=["A non-positive unit contribution means break-even is never reached — "
               "reported honestly, not as 0."]),
    Calculator(
        "payback_period", "Payback period (months)",
        "Months to recover an acquisition cost from monthly contribution.",
        [
            InputSpec("acquisition_cost", "AED", "currency", min=0,
                      description="cost to acquire one customer (CAC)"),
            InputSpec("monthly_contribution", "AED/month", "currency"),
        ], _payback_period),
    Calculator(
        "payments_take", "Payments take (net)",
        "Payments revenue on routed flow at a NET take (bps). Enforces the "
        "not-gross-MDR / not-an-issuer discipline.",
        [
            InputSpec("routed_flow", "AED", "currency", min=0,
                      description="payment flow routed through BOTIM in the period"),
            InputSpec("net_take_bps", "bps", "bps", min=0,
                      description="NET take in basis points (wallet fee or net interchange, never gross MDR)"),
        ], _payments_take,
        notes=["The accepting merchant pays MDR; issuers earn interchange or a "
               "programme share. BOTIM never earns the full MDR."]),
]}


def catalog():
    return [c.spec() for c in REGISTRY.values()]


def compute(calculator_id, raw_inputs):
    if not isinstance(calculator_id, str) or calculator_id not in REGISTRY:
        raise CalculatorError(f"unknown calculator '{calculator_id}'", status=404)
    return REGISTRY[calculator_id].compute(raw_inputs)
