"""Tests for montecarlo.py, stress.py, and the grid — plus fuzz/property tests
that hammer the core engine with randomized inputs and assert invariants."""

import json
import random
import sys
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from opportunity_engine import commercial, montecarlo, sensitivity, stress  # noqa: E402

OPP001 = json.loads(
    (REPO_ROOT / "knowledge-base/commercial-models/opp-001-inputs.json").read_text()
)


class TestMonteCarlo(unittest.TestCase):
    def setUp(self):
        self.sim = montecarlo.simulate(OPP001, n=2000, seed=42)

    def test_deterministic(self):
        again = montecarlo.simulate(OPP001, n=2000, seed=42)
        self.assertEqual(self.sim.contribution_mean, again.contribution_mean)
        self.assertEqual(self.sim.p_loss, again.p_loss)

    def test_seed_changes_result(self):
        other = montecarlo.simulate(OPP001, n=2000, seed=7)
        self.assertNotEqual(self.sim.contribution_mean, other.contribution_mean)

    def test_percentiles_ordered(self):
        c = self.sim.contribution_percentiles
        self.assertLessEqual(c[5], c[25])
        self.assertLessEqual(c[25], c[50])
        self.assertLessEqual(c[50], c[75])
        self.assertLessEqual(c[75], c[95])
        self.assertLessEqual(self.sim.worst_draw, c[5])
        self.assertLessEqual(c[95], self.sim.best_draw)

    def test_opp001_has_real_but_small_loss_probability(self):
        # downside is loss-making, so losses must appear in the tail — but with
        # INDEPENDENT sampling they're rare (~1%: several inputs must be bad at
        # once). Stable across seeds at ~0.8–1.0%. Correlated adversity is
        # stress.py's job, which is why both exist.
        self.assertGreater(self.sim.p_loss, 0.001)
        self.assertLess(self.sim.p_loss, 0.10)
        self.assertAlmostEqual(self.sim.p_never_breakeven, self.sim.p_loss, places=9)

    def test_draws_respect_input_ranges(self):
        # P95 of contribution can't exceed the all-upside deterministic case
        upside = commercial.compute_case("upside", OPP001["cases"]["upside"])
        downside = commercial.compute_case("downside", OPP001["cases"]["downside"])
        self.assertLessEqual(self.sim.best_draw, upside.contribution + 1e-6)
        self.assertGreaterEqual(self.sim.worst_draw, downside.contribution - 1e-6)

    def test_small_n_rejected(self):
        with self.assertRaises(commercial.InputError):
            montecarlo.simulate(OPP001, n=50)

    def test_render(self):
        report = montecarlo.render_markdown(OPP001, self.sim)
        self.assertIn("P(loss-making unit economics)", report)
        self.assertIn("correlations NOT modelled", report)


class TestScenarios(unittest.TestCase):
    def setUp(self):
        self.baseline, self.rows = stress.run(OPP001, "base")
        self.by_name = {r.name: r for r in self.rows}

    def test_all_builtin_scenarios_run(self):
        self.assertEqual(set(self.by_name), set(stress.SCENARIOS))

    def test_all_deltas_negative(self):
        for r in self.rows:
            self.assertLess(r.contribution_delta, 0, r.name)

    def test_credit_and_run_kills(self):
        r = self.by_name["credit_and_run"]
        self.assertFalse(r.survived, f"credit_and_run should kill: {r.contribution}")
        # drawn balance roughly preserved: routed_share*0.3 * multiple*3.33 ≈ 1.0
        # while ECL doubles and payment revenue collapses

    def test_perfect_storm_kills(self):
        self.assertFalse(self.by_name["perfect_storm"].survived)

    def test_rate_compression_is_severe(self):
        # sensitivity ranked financing rate #1; the scenario must agree
        r = self.by_name["rate_compression"]
        self.assertLess(r.contribution, 25)

    def test_single_mild_shocks_survive(self):
        for name in ("cac_blowout", "collections_heavy"):
            self.assertTrue(self.by_name[name].survived, name)

    def test_shock_ops(self):
        case = OPP001["cases"]["base"]
        shocked = stress.apply_scenario(case, {"shocks": {
            "servicing_cost_monthly": {"add": 100},
            "financing_rate_annual": {"set": 0.10},
            "routed_share": {"mul": 10},          # must clamp to 1.0
        }})
        r = commercial.compute_case("x", shocked)
        self.assertAlmostEqual(r.v("servicing_cost_monthly"), 125)
        self.assertAlmostEqual(r.v("financing_rate_annual"), 0.10)
        self.assertAlmostEqual(r.v("routed_share"), 1.0)

    def test_bad_scenarios_rejected(self):
        with self.assertRaises(commercial.InputError):
            stress.run(OPP001, "base", {"x": {"shocks": {}}})
        with self.assertRaises(commercial.InputError):
            stress.run(OPP001, "base", {"x": {"shocks": {"not_an_input": {"mul": 2}}}})
        with self.assertRaises(commercial.InputError):
            stress.run(OPP001, "base", {"x": {"shocks": {"ecl_rate_annual": {"pow": 2}}}})

    def test_render(self):
        report = stress.render_markdown(OPP001, "base", self.baseline, self.rows)
        self.assertIn("credit_and_run", report)
        self.assertIn("scenarios kill unit economics", report)


class TestGrid(unittest.TestCase):
    def test_shape_and_frontier(self):
        xs, ys, matrix = sensitivity.grid(OPP001, "routed_share", "ecl_rate_annual", steps=5)
        self.assertEqual(len(xs), 5)
        self.assertEqual(len(ys), 5)
        self.assertEqual(len(matrix), 5)
        self.assertTrue(all(len(row) == 5 for row in matrix))
        # corners: best (high routed, low ecl) > worst (low routed, high ecl)
        best, worst = matrix[0][-1], matrix[-1][0]
        self.assertGreater(best, worst)

    def test_monotone_along_axes(self):
        xs, ys, matrix = sensitivity.grid(OPP001, "routed_share", "ecl_rate_annual", steps=5)
        for row in matrix:                     # contribution rises with routed_share
            self.assertEqual(row, sorted(row))
        for j in range(5):                     # contribution falls as ECL rises
            column = [matrix[i][j] for i in range(5)]
            self.assertEqual(column, sorted(column, reverse=True))

    def test_validation(self):
        for bad in (("routed_share", "routed_share"), ("nope", "ecl_rate_annual")):
            with self.assertRaises(commercial.InputError):
                sensitivity.grid(OPP001, *bad)
        with self.assertRaises(commercial.InputError):
            sensitivity.grid(OPP001, "routed_share", "ecl_rate_annual", steps=2)

    def test_render(self):
        xs, ys, matrix = sensitivity.grid(OPP001, "routed_share", "ecl_rate_annual", steps=4)
        report = sensitivity.render_grid_markdown(
            OPP001, "routed_share", "ecl_rate_annual", "base", xs, ys, matrix
        )
        self.assertIn("viability frontier", report)
        self.assertIn("combinations are loss-making", report)


class TestEngineInvariantsFuzz(unittest.TestCase):
    """Property tests: hammer compute_case with 300 randomized-but-plausible
    input sets and assert accounting identities and structural invariants."""

    N = 300

    def _random_case(self, rng):
        return {
            "active_merchants": rng.uniform(1, 10_000),
            "monthly_revenue_per_merchant": rng.uniform(1_000, 1_000_000),
            "routed_share": rng.uniform(0, 1),
            "limit_multiple_of_routed_flow": rng.uniform(0, 3),
            "utilisation": rng.uniform(0, 1),
            "financing_rate_annual": rng.uniform(0, 0.5),
            "payment_take_bps": rng.uniform(0, 200),
            "subscription_revenue_monthly": rng.uniform(0, 500),
            "other_revenue_monthly": rng.uniform(0, 500),
            "funding_rate_annual": rng.uniform(0.001, 0.3),
            "ecl_rate_annual": rng.uniform(0, 0.5),
            "fraud_loss_monthly": rng.uniform(0, 200),
            "processing_cost_monthly": rng.uniform(0, 200),
            "scheme_fees_monthly": rng.uniform(0, 100),
            "rewards_monthly": rng.uniform(0, 300),
            "servicing_cost_monthly": rng.uniform(0, 300),
            "cac_amortised_monthly": rng.uniform(0, 300),
            "fixed_costs_monthly": rng.uniform(0, 1_000_000),
        }

    def test_accounting_identities_hold(self):
        rng = random.Random(0)
        for i in range(self.N):
            case = self._random_case(rng)
            r = commercial.compute_case(f"fuzz{i}", case)
            self.assertAlmostEqual(
                r.contribution, r.total_revenue - r.total_cost, places=6, msg=f"fuzz{i}"
            )
            self.assertGreaterEqual(r.total_revenue, -1e-9)
            self.assertGreaterEqual(r.total_cost, -1e-9)
            self.assertAlmostEqual(
                r.routed_flow,
                case["monthly_revenue_per_merchant"] * case["routed_share"],
                places=6,
            )
            # break-even defined iff unit economics positive
            self.assertEqual(r.breakeven_merchants is None, r.contribution <= 0, f"fuzz{i}")
            # ceilings never negative; net free days never exceed gross
            self.assertGreaterEqual(r.max_free_days_gross, 0)
            self.assertGreaterEqual(r.max_free_days_net, 0)
            self.assertLessEqual(r.max_free_days_net, r.max_free_days_gross + 1e-9)
            self.assertGreaterEqual(r.max_cashback_pct, 0)
            self.assertAlmostEqual(r.max_fee_subsidy, max(0.0, r.contribution), places=6)

    def test_cost_monotonicity(self):
        """Raising any pure-cost input never increases contribution."""
        rng = random.Random(1)
        cost_inputs = (
            "ecl_rate_annual", "funding_rate_annual", "fraud_loss_monthly",
            "processing_cost_monthly", "scheme_fees_monthly", "rewards_monthly",
            "servicing_cost_monthly", "cac_amortised_monthly",
        )
        for i in range(60):
            case = self._random_case(rng)
            base = commercial.compute_case("m", case)
            name = cost_inputs[i % len(cost_inputs)]
            worse = dict(case)
            worse[name] = case[name] * 1.5 + 1
            self.assertLessEqual(
                commercial.compute_case("m", worse).contribution,
                base.contribution + 1e-9,
                f"{name} at iteration {i}",
            )

    def test_revenue_monotonicity(self):
        """Raising pure-revenue inputs never decreases contribution."""
        rng = random.Random(2)
        revenue_inputs = ("payment_take_bps", "subscription_revenue_monthly",
                          "other_revenue_monthly", "financing_rate_annual")
        for i in range(60):
            case = self._random_case(rng)
            base = commercial.compute_case("m", case)
            name = revenue_inputs[i % len(revenue_inputs)]
            better = dict(case)
            better[name] = case[name] * 1.5 + 0.001
            self.assertGreaterEqual(
                commercial.compute_case("m", better).contribution,
                base.contribution - 1e-9,
                f"{name} at iteration {i}",
            )

    def test_garbage_rejected(self):
        base = dict(OPP001["cases"]["base"])
        for name, bad in (
            ("routed_share", 1.5),
            ("utilisation", -0.1),
            ("ecl_rate_annual", "six percent"),
            ("ecl_rate_annual", None),
            ("ecl_rate_annual", True),
            ("ecl_rate_annual", {"value": "x"}),
        ):
            case = dict(base)
            case[name] = bad
            with self.assertRaises(commercial.InputError, msg=f"{name}={bad!r}"):
                commercial.compute_case("bad", case)


if __name__ == "__main__":
    unittest.main()
