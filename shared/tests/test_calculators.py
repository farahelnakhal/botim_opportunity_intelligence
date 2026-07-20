"""Phase C1 — deterministic calculator engine tests. All offline, pure."""

import json
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from shared.calculators import compute, catalog, render_markdown, CalculatorError
from shared.calculators.base import worst_label, _apply_op, _close


class CatalogTests(unittest.TestCase):
    def test_catalog_lists_declared_inputs(self):
        cat = {c["id"]: c for c in catalog()}
        self.assertIn("market_sizing", cat)
        self.assertIn("payments_take", cat)
        ms = cat["market_sizing"]
        names = [i["name"] for i in ms["inputs"]]
        self.assertEqual(names, ["population", "annual_value_per_unit",
                                 "serviceable_fraction", "obtainable_share"])
        # every input declares a unit + kind
        for c in cat.values():
            for i in c["inputs"]:
                self.assertTrue(i["unit"])
                self.assertIn(i["kind"], ("number", "integer", "currency", "fraction",
                                          "percent", "multiplier", "bps", "count"))


class GoldenValueTests(unittest.TestCase):
    def test_market_sizing_chain(self):
        env = compute("market_sizing", {
            "population": 500000, "annual_value_per_unit": 12000,
            "serviceable_fraction": 0.4, "obtainable_share": 0.1})
        self.assertEqual(env["outputs"]["tam"]["value"], 6_000_000_000)
        self.assertEqual(env["outputs"]["sam"]["value"], 2_400_000_000)
        self.assertEqual(env["outputs"]["som"]["value"], 240_000_000)

    def test_bottomup(self):
        env = compute("market_sizing_bottomup", {
            "num_customers": 1000, "units_per_customer_per_year": 12, "price_per_unit": 50})
        self.assertEqual(env["outputs"]["market_value"]["value"], 600_000)

    def test_growth_projection(self):
        env = compute("growth_projection", {
            "present_value": 1000, "annual_growth_rate_pct": 10, "years": 3})
        self.assertTrue(_close(env["outputs"]["future_value"]["value"], 1331.0))

    def test_implied_cagr(self):
        env = compute("implied_cagr", {"start_value": 1000, "end_value": 1331, "years": 3})
        self.assertTrue(_close(env["outputs"]["cagr"]["value"], 0.10))
        self.assertEqual(env["outputs"]["cagr"]["display"], "10.00%")

    def test_adoption(self):
        env = compute("adoption_forecast", {"addressable_population": 200000, "adoption_rate": 0.15})
        self.assertEqual(env["outputs"]["adopters"]["value"], 30000)

    def test_unit_contribution_and_margin(self):
        env = compute("unit_contribution", {"revenue_per_unit": 100, "variable_cost_per_unit": 60})
        self.assertEqual(env["outputs"]["contribution"]["value"], 40)
        self.assertTrue(_close(env["outputs"]["margin"]["value"], 0.4))

    def test_breakeven(self):
        env = compute("breakeven", {"fixed_costs": 100000, "contribution_per_unit": 5})
        self.assertEqual(env["outputs"]["breakeven_units"]["value"], 20000)

    def test_payback(self):
        env = compute("payback_period", {"acquisition_cost": 240, "monthly_contribution": 20})
        self.assertEqual(env["outputs"]["payback_months"]["value"], 12)

    def test_payments_take(self):
        env = compute("payments_take", {"routed_flow": 1_000_000, "net_take_bps": 50})
        self.assertEqual(env["outputs"]["revenue"]["value"], 5000)


class HonestyTests(unittest.TestCase):
    def test_determinism_byte_identical(self):
        args = ("market_sizing", {"population": {"value": 500000, "label": "E", "note": "x"},
                                  "annual_value_per_unit": 12000,
                                  "serviceable_fraction": 0.4, "obtainable_share": 0.1})
        a = json.dumps(compute(*args), sort_keys=True)
        b = json.dumps(compute(*args), sort_keys=True)
        self.assertEqual(a, b)

    def test_label_propagation_any_assumption_is_illustrative(self):
        # a bare number is an assumption -> illustrative disclaimer present
        env = compute("market_sizing", {"population": 1, "annual_value_per_unit": 1,
                                        "serviceable_fraction": 0.5, "obtainable_share": 0.5})
        self.assertEqual(env["result_label"], "A")
        self.assertTrue(any("Illustrative" in d for d in env["disclaimers"]))

    def test_all_fact_inputs_not_illustrative(self):
        f = lambda v: {"value": v, "label": "F"}
        env = compute("unit_contribution", {"revenue_per_unit": f(100), "variable_cost_per_unit": f(60)})
        self.assertEqual(env["result_label"], "F")
        self.assertFalse(any("Illustrative" in d for d in env["disclaimers"]))

    def test_breakeven_never_not_zero(self):
        env = compute("breakeven", {"fixed_costs": 100000, "contribution_per_unit": 0})
        out = env["outputs"]["breakeven_units"]
        self.assertIsNone(out["value"])
        self.assertEqual(out["display"], "never")

    def test_margin_undefined_when_no_revenue(self):
        env = compute("unit_contribution", {"revenue_per_unit": 0, "variable_cost_per_unit": 0})
        self.assertIsNone(env["outputs"]["margin"]["value"])
        self.assertEqual(env["outputs"]["margin"]["display"], "undefined")

    def test_payback_never_on_nonpositive_contribution(self):
        env = compute("payback_period", {"acquisition_cost": 240, "monthly_contribution": 0})
        self.assertEqual(env["outputs"]["payback_months"]["display"], "never")

    def test_market_sizing_carries_not_a_bank_disclaimer(self):
        env = compute("market_sizing", {"population": 1, "annual_value_per_unit": 1,
                                        "serviceable_fraction": 0.5, "obtainable_share": 0.5})
        self.assertTrue(any("not assumed to be a bank" in d for d in env["disclaimers"]))

    def test_payments_take_flags_gross_mdr_and_issuer(self):
        env = compute("payments_take", {"routed_flow": 1_000_000, "net_take_bps": 500})
        self.assertTrue(any("gross MDR" in w for w in env["warnings"]))
        self.assertTrue(any("issuer" in w for w in env["warnings"]))

    def test_shown_working_self_consistent(self):
        # every step's rendered result equals a re-evaluation of its operands
        env = compute("growth_projection", {"present_value": 2500,
                                             "annual_growth_rate_pct": 7.5, "years": 5})
        for s in env["steps"]:
            self.assertTrue(_close(_apply_op(s["op"], [o["value"] for o in s["operands"]]),
                                   s["result"]))

    def test_render_contains_every_output_number(self):
        env = compute("market_sizing", {"population": 500000, "annual_value_per_unit": 12000,
                                        "serviceable_fraction": 0.4, "obtainable_share": 0.1})
        md = render_markdown(env)
        for out in env["outputs"].values():
            self.assertIn(out["display"], md)


class ErrorTests(unittest.TestCase):
    def test_unknown_calculator_404(self):
        with self.assertRaises(CalculatorError) as cm:
            compute("nope", {})
        self.assertEqual(cm.exception.status, 404)

    def test_missing_required_input(self):
        with self.assertRaises(CalculatorError):
            compute("market_sizing", {"population": 1})

    def test_unknown_input_rejected(self):
        with self.assertRaises(CalculatorError):
            compute("adoption_forecast", {"addressable_population": 1, "adoption_rate": 0.5, "junk": 1})

    def test_fraction_over_one_rejected_with_hint(self):
        with self.assertRaises(CalculatorError) as cm:
            compute("adoption_forecast", {"addressable_population": 1, "adoption_rate": 20})
        self.assertIn("not a percent", str(cm.exception))

    def test_negative_rejected(self):
        with self.assertRaises(CalculatorError):
            compute("market_sizing", {"population": -5, "annual_value_per_unit": 1,
                                     "serviceable_fraction": 0.5, "obtainable_share": 0.5})

    def test_boolean_rejected(self):
        with self.assertRaises(CalculatorError):
            compute("adoption_forecast", {"addressable_population": True, "adoption_rate": 0.5})

    def test_non_finite_rejected(self):
        with self.assertRaises(CalculatorError):
            compute("adoption_forecast", {"addressable_population": float("inf"), "adoption_rate": 0.5})

    def test_absurd_magnitude_rejected(self):
        with self.assertRaises(CalculatorError):
            compute("adoption_forecast", {"addressable_population": 1e18, "adoption_rate": 0.5})

    def test_bad_label_rejected(self):
        with self.assertRaises(CalculatorError):
            compute("adoption_forecast",
                    {"addressable_population": {"value": 1, "label": "Z"}, "adoption_rate": 0.5})

    def test_implied_cagr_zero_start_undefined(self):
        env = compute("implied_cagr", {"start_value": 0, "end_value": 100, "years": 2})
        self.assertIsNone(env["outputs"]["cagr"]["value"])


class LabelHelperTests(unittest.TestCase):
    def test_worst_label(self):
        self.assertEqual(worst_label(["F", "F"]), "F")
        self.assertEqual(worst_label(["F", "E"]), "E")
        self.assertEqual(worst_label(["F", "A"]), "A")
        self.assertEqual(worst_label([]), "A")


if __name__ == "__main__":
    unittest.main()
