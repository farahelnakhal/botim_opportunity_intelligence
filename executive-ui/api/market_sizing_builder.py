"""Verified-source market-sizing composition (Phase C2, PR2).

Orchestration layer (executive-ui/api, per decision D1/H1 — so `shared/` never
imports up). Deterministic at build time: NO model runs here. It reads a run's
already-extracted, verified figures (shared/research/figures.py, persisted in
the research store), corroborates them (shared/research/corroboration.py), and
wires the results into C1's `market_sizing` calculator — populating each input's
`source_id` so the calculator's typed-step provenance traces TAM/SAM/SOM back to
sources.

Evidence-strength labels (decision-log C2 · H3): a **corroborated** sourced
input carries F, a **low-confidence** sourced input carries A, and the analyst
fractions (serviceable/obtainable) are always A — so a low-confidence figure and
a corroborated one are NEVER identical inside the calculator's own label
propagation, not merely on a UI badge. Review status (pending_review/approved)
is a SEPARATE axis handled by the store, never collapsed into the label.

A sourced input with NO figures is an honest gap: the sizing cannot compute and
the build is refused with the missing quantity named — never an invented number.
"""

from shared.research.corroboration import corroborate

# per method: which calculator, which inputs are source-verified vs analyst
# assumptions. Top-down verifies the market-size DRIVERS (population × value);
# the serviceable/obtainable SHARES stay analyst assumptions (as in C1).
METHODS = {
    "top_down": {"calculator": "market_sizing",
                 "sourced": ("population", "annual_value_per_unit"),
                 "assumption": ("serviceable_fraction", "obtainable_share")},
    "bottom_up": {"calculator": "market_sizing_bottomup",
                  "sourced": ("num_customers", "units_per_customer_per_year", "price_per_unit"),
                  "assumption": ()},
}


class MarketSizingBuildError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _sourced_input(research_store, run_id, quantity):
    """Corroborate a run's persisted figures for one quantity. Returns
    (calculator_input_dict, corroboration_meta). Raises if no figures exist."""
    figures = research_store.list_figures(run_id, quantity=quantity)
    if not figures:
        raise MarketSizingBuildError(
            f"no verified figures for '{quantity}' in this run — extract/verify it first "
            "(a market-size input is never invented)", status=422)
    # join each figure to its source for the independence (registrable-domain) key
    sources = {s["id"]: s for s in research_store.get_sources([f["source_id"] for f in figures])}
    items = [{"value": f["value"], "source_id": f["source_id"], "unit": f.get("unit"),
              "url": (sources.get(f["source_id"], {}) or {}).get("canonical_url")
                     or (sources.get(f["source_id"], {}) or {}).get("domain") or "",
              "tier": f.get("tier")}
             for f in figures]
    verdict = corroborate(items)
    verified = verdict["status"] == "verified"
    # representative source id: a corroborating one if verified, else the first figure
    src = (verdict["supporting_source_ids"] or [figures[0]["source_id"]])[0]
    calc_input = {
        "value": verdict["value"],
        "label": "F" if verified else "A",       # H3: corroborated -> Fact; else Assumption
        "note": f"{'corroborated' if verified else 'low-confidence'} "
                f"({verdict['independent_t1_t2_count']} independent T1/T2; {verdict['reason']})",
        "source_id": src,
    }
    meta = {"sourced": True, "quantity": quantity, "corroboration": verdict}
    return calc_input, meta


def _assumption_input(name, spec):
    if not isinstance(spec, dict) or not isinstance(spec.get("value"), (int, float)) \
            or isinstance(spec.get("value"), bool):
        raise MarketSizingBuildError(f"assumption input '{name}' needs a numeric 'value'")
    note = spec.get("note")
    calc_input = {"value": float(spec["value"]), "label": "A",
                  "note": (note if isinstance(note, str) else "") or "analyst assumption"}
    return calc_input, {"sourced": False, "assumption": True, "note": calc_input["note"]}


def build_market_sizing(research_store, sizing_store, *, opportunity_id, run_id, method,
                        inputs, owner_user_id=None):
    """Compose and persist a candidate sizing. `inputs` maps each calculator
    input to `{quantity: "..."}` (sourced) or `{value: n, note?}` (assumption).
    Deterministic; raises MarketSizingBuildError on a missing figure / bad input."""
    from shared import calculators as calculators_pkg      # lazy: shared bottom layer

    if method not in METHODS:
        raise MarketSizingBuildError(f"method must be one of {', '.join(METHODS)}")
    spec = METHODS[method]
    if not isinstance(inputs, dict):
        raise MarketSizingBuildError("'inputs' must be an object")

    raw_inputs, inputs_meta = {}, {}
    all_sourced_verified = True
    any_sourced = False
    for name in spec["sourced"]:
        entry = inputs.get(name)
        if not isinstance(entry, dict) or not isinstance(entry.get("quantity"), str):
            raise MarketSizingBuildError(f"sourced input '{name}' needs a 'quantity' string")
        calc_input, meta = _sourced_input(research_store, run_id, entry["quantity"].strip())
        raw_inputs[name] = calc_input
        inputs_meta[name] = meta
        any_sourced = True
        if meta["corroboration"]["status"] != "verified":
            all_sourced_verified = False
    for name in spec["assumption"]:
        entry = inputs.get(name)
        if entry is None:
            raise MarketSizingBuildError(f"assumption input '{name}' is required")
        calc_input, meta = _assumption_input(name, entry)
        raw_inputs[name] = calc_input
        inputs_meta[name] = meta

    try:
        envelope = calculators_pkg.compute(spec["calculator"], raw_inputs)
    except calculators_pkg.CalculatorError as exc:
        raise MarketSizingBuildError(f"calculator rejected the inputs: {exc}", status=exc.status)

    confidence = "verified" if (any_sourced and all_sourced_verified) else "low_confidence"
    sizing = {
        "method": method,
        "calculator": spec["calculator"],
        "envelope": envelope,          # C1 typed-step provenance; inputs carry source_id
        "inputs_meta": inputs_meta,    # per-input corroboration / assumption detail
        "run_id": run_id,
        "overall_confidence": confidence,
        "confidence_basis": ("all source-verified inputs are corroborated by >=2 independent "
                             "T1/T2 sources" if confidence == "verified"
                             else "at least one source-verified input is low-confidence "
                                  "(single-source, lower-tier, or disagreeing) — not validated"),
    }
    return sizing_store.create(opportunity_id, calculator=spec["calculator"],
                               confidence=confidence, sizing=sizing, run_id=run_id,
                               owner_user_id=owner_user_id)
