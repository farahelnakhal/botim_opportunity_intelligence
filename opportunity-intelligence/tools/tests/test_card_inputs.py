"""Tests for the optional card/acquiring inputs added after the module audit:
acquiring_revenue_monthly, the online/offline blend trio, and
avg_credit_duration_days — including full backwards compatibility."""

import json
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
BASE = OPP001["cases"]["base"]


def _case(**overrides):
    case = json.loads(json.dumps(BASE))
    case.update(overrides)
    return case


class TestBackwardsCompatibility(unittest.TestCase):
    def test_models_without_optional_inputs_unchanged(self):
        r = commercial.compute_case("base", BASE)
        self.assertAlmostEqual(r.contribution, 136.5, delta=1)
        self.assertEqual(r.acquiring_revenue, 0.0)
        self.assertIsNone(r.monthly_originations)
        self.assertAlmostEqual(r.effective_payment_take_bps, 30)

    def test_full_repo_still_green(self):
        results = commercial.compute_model(OPP001)
        self.assertAlmostEqual(results["base"].contribution, 136.5, delta=1)


class TestAcquiringRevenue(unittest.TestCase):
    def test_flows_to_total(self):
        r = commercial.compute_case("x", _case(acquiring_revenue_monthly=50))
        base = commercial.compute_case("base", BASE)
        self.assertAlmostEqual(r.acquiring_revenue, 50)
        self.assertAlmostEqual(r.contribution, base.contribution + 50, places=6)


class TestBlend(unittest.TestCase):
    def test_blended_take(self):
        # 60% offline at 100bps, 40% online at 150bps -> 120bps effective
        r = commercial.compute_case("x", _case(
            payment_take_bps=0,
            offline_share=0.6,
            payment_take_bps_offline=100,
            payment_take_bps_online=150,
        ))
        self.assertAlmostEqual(r.effective_payment_take_bps, 120)
        self.assertAlmostEqual(r.payment_revenue, r.routed_flow * 0.012, places=6)

    def test_partial_trio_rejected(self):
        with self.assertRaises(commercial.InputError):
            commercial.compute_case("x", _case(payment_take_bps=0, offline_share=0.6))

    def test_double_count_rejected(self):
        with self.assertRaises(commercial.InputError):
            commercial.compute_case("x", _case(
                offline_share=0.6, payment_take_bps_offline=100, payment_take_bps_online=150,
            ))  # payment_take_bps still 30 -> double count

    def test_offline_share_fraction_enforced(self):
        with self.assertRaises(commercial.InputError):
            commercial.compute_case("x", _case(
                payment_take_bps=0, offline_share=1.4,
                payment_take_bps_offline=100, payment_take_bps_online=150,
            ))


class TestDuration(unittest.TestCase):
    def test_derived_metrics(self):
        r = commercial.compute_case("x", _case(avg_credit_duration_days=60))
        self.assertAlmostEqual(r.monthly_originations, r.drawn_balance * 30 / 60, places=6)
        self.assertAlmostEqual(r.credit_turns_per_year, 365 / 60, places=6)
        # reporting-only: contribution unchanged
        base = commercial.compute_case("base", BASE)
        self.assertAlmostEqual(r.contribution, base.contribution, places=6)

    def test_nonpositive_rejected(self):
        with self.assertRaises(commercial.InputError):
            commercial.compute_case("x", _case(avg_credit_duration_days=0))

    def test_render_includes_duration_rows_only_when_present(self):
        model = json.loads(json.dumps(OPP001))
        plain = commercial.render_markdown(model, commercial.compute_model(model))
        self.assertNotIn("Monthly originations", plain)
        for c in commercial.CASES:
            model["cases"][c]["avg_credit_duration_days"] = 60
        with_dur = commercial.render_markdown(model, commercial.compute_model(model))
        self.assertIn("Monthly originations", with_dur)


class TestDownstreamModules(unittest.TestCase):
    def _model_with_optional(self):
        model = json.loads(json.dumps(OPP001))
        for c in commercial.CASES:
            model["cases"][c]["acquiring_revenue_monthly"] = {"value": 40, "label": "A"}
        return model

    def test_montecarlo_samples_optional_inputs(self):
        model = self._model_with_optional()
        sim = montecarlo.simulate(model, n=500, seed=42)
        plain = montecarlo.simulate(OPP001, n=500, seed=42)
        # constant +40 revenue shifts the whole distribution up by 40
        self.assertAlmostEqual(sim.contribution_mean, plain.contribution_mean + 40, delta=0.5)

    def test_montecarlo_rejects_half_specified_optional(self):
        model = json.loads(json.dumps(OPP001))
        model["cases"]["base"]["acquiring_revenue_monthly"] = 40  # base only
        with self.assertRaises(commercial.InputError):
            montecarlo.simulate(model, n=500)

    def test_sensitivity_includes_optional_and_skips_duration(self):
        model = self._model_with_optional()
        for c in commercial.CASES:
            model["cases"][c]["avg_credit_duration_days"] = 60
        _, rows = sensitivity.analyse(model, "base", 0.5)
        names = {r.input_name for r in rows}
        self.assertIn("acquiring_revenue_monthly", names)
        self.assertNotIn("avg_credit_duration_days", names)

    def test_stress_can_shock_used_optional_only(self):
        model = self._model_with_optional()
        _, rows = stress.run(model, "base", {
            "acq_loss": {"description": "acquiring margin halves",
                         "shocks": {"acquiring_revenue_monthly": {"mul": 0.5}}},
        })
        self.assertAlmostEqual(rows[0].contribution_delta, -20, delta=0.5)
        with self.assertRaises(commercial.InputError):
            stress.run(OPP001, "base", {  # OPP-001 doesn't use acquiring
                "bad": {"shocks": {"acquiring_revenue_monthly": {"mul": 0.5}}},
            })


if __name__ == "__main__":
    unittest.main()
