"""Tests for sensitivity.py, results.py, and their check-sweep integration."""

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import run as cli  # noqa: E402
from opportunity_engine import commercial, results, sensitivity  # noqa: E402

OPP001 = json.loads(
    (REPO_ROOT / "knowledge-base/commercial-models/opp-001-inputs.json").read_text()
)
VE001_RESULT = json.loads(
    (REPO_ROOT / "knowledge-base/validation/VE-001-result.json").read_text()
)


class TestSensitivity(unittest.TestCase):
    def setUp(self):
        self.baseline, self.rows = sensitivity.analyse(OPP001, "base", 0.5)

    def test_all_deltas_non_positive(self):
        for r in self.rows:
            self.assertLessEqual(r.contribution_delta, 1e-9, r.input_name)

    def test_big_drivers_rank_high(self):
        top5 = {r.input_name for r in self.rows[:5]}
        # drawn-balance and rate drivers dominate OPP-001's economics
        self.assertIn("financing_rate_annual", top5)
        self.assertTrue(
            {"routed_share", "utilisation", "limit_multiple_of_routed_flow",
             "monthly_revenue_per_merchant"} & top5
        )

    def test_zero_inputs_skipped(self):
        names = {r.input_name for r in self.rows}
        self.assertNotIn("rewards_monthly", names)       # 0 in base case
        self.assertNotIn("scheme_fees_monthly", names)   # 0 in base case

    def test_fraction_clamped(self):
        # routed_share 0.30 * 1.5 = 0.45 <= 1; force a case that would exceed 1
        model = json.loads(json.dumps(OPP001))
        model["cases"]["base"]["routed_share"] = {"value": 0.9, "label": "A"}
        _, rows = sensitivity.analyse(model, "base", 0.5)
        row = next(r for r in rows if r.input_name == "routed_share")
        self.assertLessEqual(row.worst_value, 1.0)

    def test_bad_degrade_rejected(self):
        with self.assertRaises(commercial.InputError):
            sensitivity.analyse(OPP001, "base", 1.5)

    def test_render(self):
        report = sensitivity.render_markdown(OPP001, "base", 0.5, self.baseline, self.rows)
        self.assertIn("Validate first", report)
        self.assertIn(self.rows[0].input_name, report)


def _with_observed(*values):
    result = json.loads(json.dumps(VE001_RESULT))
    for metric, value in zip(result["metrics"], values):
        metric["observed"] = value
    return result


class TestVerdicts(unittest.TestCase):
    def test_template_is_pending(self):
        ev = results.evaluate(VE001_RESULT)
        self.assertEqual(ev["verdict"], "pending")

    def test_pass(self):
        # 45% completion, 10/15 costly workaround, 3/15 none
        ev = results.evaluate(_with_observed(45, 10, 3))
        self.assertEqual(ev["verdict"], "pass")
        self.assertIn("concierge MVP", ev["action"])

    def test_fail_on_kill_threshold(self):
        # completion 10% <= 15 kills regardless of the interview metrics
        ev = results.evaluate(_with_observed(10, 10, 3))
        self.assertEqual(ev["verdict"], "fail")
        self.assertIn("Weak", ev["action"])

    def test_fail_on_secondary_kill(self):
        # completion fine but 9/15 interviews show no costly workaround
        ev = results.evaluate(_with_observed(45, 5, 9))
        self.assertEqual(ev["verdict"], "fail")

    def test_inconclusive_between_thresholds(self):
        # 25% completion: above kill (15), below success (40)
        ev = results.evaluate(_with_observed(25, 10, 3))
        self.assertEqual(ev["verdict"], "inconclusive")
        self.assertIn("Redesign", ev["action"])

    def test_fail_beats_pending(self):
        ev = results.evaluate(_with_observed(10, None, None))
        self.assertEqual(ev["verdict"], "fail")

    def test_ve002_strict_less_than_failure(self):
        ve2 = json.loads((REPO_ROOT / "knowledge-base/validation/VE-002-result.json").read_text())
        ve2["metrics"][0]["observed"] = 20   # exactly 20 must NOT fail ('<' op)
        ve2["metrics"][1]["observed"] = 25   # coverage below 30 -> inconclusive
        ev = results.evaluate(ve2)
        self.assertEqual(ev["verdict"], "inconclusive")
        ve2["metrics"][1]["observed"] = 35
        self.assertEqual(results.evaluate(ve2)["verdict"], "pass")
        ve2["metrics"][0]["observed"] = 19.9
        self.assertEqual(results.evaluate(ve2)["verdict"], "fail")

    def test_structural_errors(self):
        broken = json.loads(json.dumps(VE001_RESULT))
        del broken["on_fail"]
        with self.assertRaises(commercial.InputError):
            results.evaluate(broken)
        broken = json.loads(json.dumps(VE001_RESULT))
        broken["metrics"][0]["success"] = {"op": "==", "value": 40}
        with self.assertRaises(commercial.InputError):
            results.evaluate(broken)
        broken = json.loads(json.dumps(VE001_RESULT))
        broken["metrics"][0]["success"] = None
        broken["metrics"][0]["failure"] = None
        with self.assertRaises(commercial.InputError):
            results.evaluate(broken)


class TestCheckIncludesResults(unittest.TestCase):
    def test_real_repo_still_passes_with_result_files(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.run_check(REPO_ROOT)
        output = buf.getvalue()
        self.assertEqual(code, 0, output)
        self.assertIn("VE-001-result.json: verdict PENDING", output)
        self.assertIn("VE-002-result.json: verdict PENDING", output)


if __name__ == "__main__":
    unittest.main()
