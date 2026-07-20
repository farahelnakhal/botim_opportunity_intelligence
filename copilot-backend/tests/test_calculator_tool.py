"""Phase C1 — copilot deterministic-calculator tool, intent, grounding, and the
numeric-fidelity guard. The model may only narrate the computed numbers; it
never does the arithmetic itself."""

import os
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[0]
for p in (str(BACKEND), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("COPILOT_PROVIDER", "mock")

from app import grounding, intents, tools_registry, wordguard  # noqa: E402


class CalculatorTool(unittest.TestCase):
    def test_list_calculators_lists_required_inputs(self):
        result = tools_registry.list_calculators()
        ids = [c["id"] for c in result["calculators"]]
        self.assertIn("market_sizing", ids)
        ms = next(c for c in result["calculators"] if c["id"] == "market_sizing")
        self.assertTrue(all("unit" in i for i in ms["inputs"]))

    def test_run_calculator_returns_shown_working(self):
        result = tools_registry.run_calculator("market_sizing", {
            "population": 500000, "annual_value_per_unit": 12000,
            "serviceable_fraction": 0.4, "obtainable_share": 0.1})
        env = result["calculation"]
        self.assertEqual(env["outputs"]["tam"]["value"], 6_000_000_000)
        self.assertIn("###", result["shown_working"])

    def test_run_calculator_unknown_is_not_found_toolerror(self):
        with self.assertRaises(tools_registry.ToolError) as cm:
            tools_registry.run_calculator("nope", {})
        self.assertTrue(cm.exception.not_found)

    def test_run_calculator_rejects_bad_inputs(self):
        with self.assertRaises(tools_registry.ToolError):
            tools_registry.run_calculator("market_sizing", "not-an-object")
        with self.assertRaises(tools_registry.ToolError):
            # unknown input key rejected by the engine, surfaced as ToolError
            tools_registry.run_calculator("adoption_forecast",
                                          {"addressable_population": 1, "adoption_rate": 0.5, "x": 1})

    def test_tool_registered_and_shaped(self):
        specs = {s["name"]: s for s in tools_registry.tool_specs()}
        self.assertIn("run_calculator", specs)
        self.assertIn("list_calculators", specs)
        self.assertEqual(specs["run_calculator"]["input_schema"]["required"],
                         ["calculator_id", "inputs"])


class CalculatorIntent(unittest.TestCase):
    def _ids(self):
        return intents.extract_ids("")

    def test_calc_vocabulary_routes_to_deterministic_calculation(self):
        for msg in ["calculate the TAM for UAE SMEs",
                    "what's the break-even volume?",
                    "compute the payback period",
                    "size the market"]:
            self.assertEqual(intents.classify(msg, self._ids()), "deterministic_calculation", msg)

    def test_plan_seeds_the_catalog(self):
        plan = intents.tool_plan("deterministic_calculation", self._ids(), "calculate the TAM")
        self.assertEqual(plan[0][0], "list_calculators")

    def test_strategic_question_still_routes_elsewhere(self):
        # a non-calculation strategic ask must NOT be captured by the calc rule
        self.assertNotEqual(
            intents.classify("explain the risks of OPP-001",
                             intents.extract_ids("explain the risks of OPP-001")),
            "deterministic_calculation")


class CalculatorGrounding(unittest.TestCase):
    def _ids(self):
        return intents.extract_ids("")

    def test_grounding_presents_shown_working_and_flags_illustrative(self):
        result = tools_registry.run_calculator("market_sizing", {
            "population": 500000, "annual_value_per_unit": 12000,
            "serviceable_fraction": 0.4, "obtainable_share": 0.1})
        pack = grounding.build("deterministic_calculation",
                               [("run_calculator", result)], self._ids())
        facts = "\n".join(pack.facts)
        self.assertIn("DETERMINISTIC CALCULATION", facts)
        self.assertIn("6,000,000,000", facts)   # the computed TAM appears as a fact
        self.assertTrue(pack.needs_no_decision)
        self.assertTrue(pack.has_calculation)
        self.assertEqual(pack.conf_sources["deterministic calculation"], "low")
        self.assertTrue(any("illustrative" in w.lower() for w in pack.warnings))
        self.assertTrue(pack.assumptions)   # assumption-labelled inputs surfaced

    def test_payments_take_grounds_the_not_gross_mdr_warning(self):
        result = tools_registry.run_calculator("payments_take",
                                               {"routed_flow": 1_000_000, "net_take_bps": 500})
        pack = grounding.build("deterministic_calculation",
                               [("run_calculator", result)], self._ids())
        self.assertTrue(any("gross MDR" in w for w in pack.warnings))
        self.assertTrue(any("issuer" in w for w in pack.warnings))


class NumericFidelityGuard(unittest.TestCase):
    def test_number_absent_from_facts_is_flagged(self):
        facts = "- OUTPUT tam = 6,000,000,000 AED/year"
        # a fabricated large figure the model injected
        self.assertIsNotNone(wordguard.check_numeric_fidelity(
            "The market is worth 9,500,000,000 dirhams.", facts))

    def test_grounded_number_passes(self):
        facts = "- OUTPUT tam = 6,000,000,000 AED/year"
        self.assertIsNone(wordguard.check_numeric_fidelity(
            "The TAM is 6,000,000,000 AED.", facts))

    def test_small_numbers_ignored(self):
        facts = "- OUTPUT som = 240,000,000 AED/year"
        # "3 years", "40%" are restatements, not computed outputs -> not flagged
        self.assertIsNone(wordguard.check_numeric_fidelity(
            "Over 3 years at a 40% share, SOM is 240,000,000.", facts))


if __name__ == "__main__":
    unittest.main()
