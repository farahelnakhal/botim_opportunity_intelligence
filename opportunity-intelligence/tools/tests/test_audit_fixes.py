"""Adversarial tests specified by AUDIT.md Phase 13, covering the audit fixes:
R-1 (calibration contamination), C-2 (sync mapping semantics), S-1/S-2 (input
plausibility), S-3 (overlapping thresholds), S-4 (inverted cases), C-1/C-3
(subsidy honesty), D-1 (ramp), D-2/AG-2 (classification canonicalisation),
A-1 (write-guard bypass shapes)."""

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
from opportunity_engine import backlog, commercial, journal, ramp, results, scoring, subsidy, sync  # noqa: E402

OPP001 = json.loads((REPO_ROOT / "knowledge-base/commercial-models/opp-001-inputs.json").read_text())
BASE = OPP001["cases"]["base"]


def _case(**overrides):
    case = json.loads(json.dumps(BASE))
    case.update(overrides)
    return case


class TestJournalDecontamination(unittest.TestCase):
    """Audit R-1."""

    def test_same_day_resolution_rejected(self):
        data = {"predictions": []}
        journal.add(data, "x happens", 0.4, "2026-07-11", "2026-09-01")
        with self.assertRaises(commercial.InputError):
            journal.resolve(data, "PRED-001", True, "2026-07-11")
        with self.assertRaises(commercial.InputError):
            journal.resolve(data, "PRED-001", True, "2026-07-10")  # before made
        journal.resolve(data, "PRED-001", True, "2026-07-12")      # next day OK

    def test_excluded_predictions_never_scored(self):
        data = {"predictions": []}
        e = journal.add(data, "contaminated", 0.9, "2026-07-11", "2026-09-01")
        e.update(outcome=True, resolved_on="2026-07-11",
                 excluded_from_calibration=True, exclusion_reason="audit R-1 fixture")
        cal = journal.calibration(data)
        self.assertEqual(cal["n_resolved"], 0)
        self.assertIsNone(cal["brier"])
        self.assertEqual(len(cal["excluded"]), 1)

    def test_unexcluded_contamination_flagged(self):
        data = {"predictions": []}
        e = journal.add(data, "sneaky", 0.9, "2026-07-11", "2026-09-01")
        e.update(outcome=True, resolved_on="2026-07-11")  # bypasses resolve()
        cal = journal.calibration(data)
        self.assertEqual(len(cal["contaminated"]), 1)
        self.assertEqual(cal["n_resolved"], 0)  # never scored even before exclusion
        self.assertIn("CONTAMINATED", journal.render_markdown(cal))

    def test_exclusion_requires_reason(self):
        data = {"predictions": []}
        e = journal.add(data, "x", 0.4, "2026-07-11", "2026-09-01")
        e.update(outcome=True, resolved_on="2026-08-01", excluded_from_calibration=True)
        with self.assertRaises(commercial.InputError):
            journal.validate(data)

    def test_repo_journal_decontaminated(self):
        data = journal.load(REPO_ROOT / "knowledge-base/product-ideas/decision-journal.json")
        cal = journal.calibration(data)
        self.assertEqual(cal["contaminated"], [])
        self.assertEqual(len(cal["excluded"]), 2)   # PRED-004/005
        self.assertEqual(cal["n_resolved"], 0)      # Brier is honestly unearned again


class TestSyncMappingSemantics(unittest.TestCase):
    """Audit C-2: breadth is not temporal frequency."""

    def test_frequency_is_unmapped(self):
        self.assertNotIn("frequency", sync.AXIS_TO_DIMENSION)
        self.assertIn("frequency", sync.UNMAPPED_AXES)
        self.assertNotIn("pain_frequency", sync.AXIS_TO_DIMENSION.values())

    def test_high_breadth_low_recurrence_pain_generates_no_frequency_suggestion(self):
        # a pain hitting many merchants once a year: A's frequency axis = 5;
        # the bridge must NOT present that as evidence for B's pain_frequency
        card = json.loads((REPO_ROOT / "knowledge-base/opportunity-scores/opp-001-scorecard.json").read_text())
        card["scores"]["pain_frequency"]["basis"] = "see EV-2026-W01-001"
        records = {"EV-2026-W01-001": {"id": "EV-2026-W01-001", "status": "active", "scores": {
            "frequency": 5, "severity": 3, "financial cost": 3, "urgency": 2,
            "dissatisfaction": 3, "workaround cost": 3, "switching intent": 2,
            "willingness to pay": 3, "botim relevance": 5, "evidence strength": 4}}}
        report = sync.suggestions_for_scorecard(card, records)
        self.assertNotIn("pain_frequency", {s["dimension"] for s in report["suggestions"]})


class TestInputPlausibility(unittest.TestCase):
    """Audit S-1/S-2/S-4."""

    def test_negative_cost_hard_fails(self):
        with self.assertRaises(commercial.InputError):
            commercial.compute_case("x", _case(servicing_cost_monthly=-500))

    def test_negative_revenue_hard_fails(self):
        with self.assertRaises(commercial.InputError):
            commercial.compute_case("x", _case(other_revenue_monthly={"value": -10, "label": "A"}))

    def test_absurd_rate_warns_but_computes(self):
        r = commercial.compute_case("x", _case(financing_rate_annual=5.0))
        self.assertTrue(any("financing_rate_annual" in w for w in r.warnings))

    def test_high_ecl_warns(self):
        r = commercial.compute_case("x", _case(ecl_rate_annual=0.6))
        self.assertTrue(any("ecl_rate_annual" in w for w in r.warnings))

    def test_inverted_cases_flagged(self):
        model = json.loads(json.dumps(OPP001))
        model["cases"]["downside"], model["cases"]["upside"] = (
            model["cases"]["upside"], model["cases"]["downside"])
        rendered = commercial.render_markdown(model, commercial.compute_model(model))
        self.assertIn("probably inverted", rendered)

    def test_subsidy_negative_input_hard_fails(self):
        s = json.loads((REPO_ROOT / "knowledge-base/commercial-models/opp-002-subsidy-inputs.json").read_text())
        case = s["cases"]["base"]
        case["processing_bps"] = -10
        with self.assertRaises(commercial.InputError):
            subsidy.compute_case("base", case)


class TestThresholdRegions(unittest.TestCase):
    """Audit S-3: the exact failure from the audit probe."""

    def _result(self, success, failure, observed=50):
        return {
            "experiment_id": "VE-900", "proposition": "OPP-900",
            "metrics": [{"name": "m", "observed": observed, "success": success, "failure": failure}],
            "on_pass": "p", "on_fail": "f", "on_inconclusive": "i",
        }

    def test_overlapping_regions_rejected(self):
        with self.assertRaises(commercial.InputError):
            results.evaluate(self._result({"op": ">=", "value": 40}, {"op": ">=", "value": 45}))
        with self.assertRaises(commercial.InputError):
            results.evaluate(self._result({"op": "<=", "value": 40}, {"op": "<=", "value": 30}))

    def test_disjoint_regions_still_work(self):
        ev = results.evaluate(self._result({"op": ">=", "value": 40}, {"op": "<=", "value": 15}, observed=50))
        self.assertEqual(ev["verdict"], "pass")
        ev = results.evaluate(self._result({"op": ">=", "value": 20}, {"op": "<", "value": 20}, observed=20))
        self.assertEqual(ev["verdict"], "pass")  # boundary belongs to success only

    def test_committed_result_files_all_disjoint(self):
        for path in sorted((REPO_ROOT / "knowledge-base/validation").glob("*-result.json")):
            results.evaluate(json.loads(path.read_text()))  # raises if overlapping


class TestSubsidyHonesty(unittest.TestCase):
    """Audit C-1/C-3."""

    def test_pre_credit_cost_caption_when_ecl_absent(self):
        model = json.loads((REPO_ROOT / "knowledge-base/commercial-models/opp-002-subsidy-inputs.json").read_text())
        rendered = subsidy.render_markdown(model, subsidy.compute_model(model))
        self.assertIn("PRE-CREDIT-COST", rendered)
        self.assertIn("GRACE DAYS", rendered)  # renamed, incommensurable-label fix

    def test_ecl_inputs_reduce_margin_and_drop_caption(self):
        model = json.loads((REPO_ROOT / "knowledge-base/commercial-models/opp-002-subsidy-inputs.json").read_text())
        for c in commercial.CASES:
            model["cases"][c]["ecl_bps"] = {"value": 30, "label": "A"}
            model["cases"][c]["servicing_bps"] = {"value": 10, "label": "A"}
        res = subsidy.compute_model(model)
        self.assertAlmostEqual(res["base"].net_margin_bps, 70)  # 110 - 40
        self.assertNotIn("PRE-CREDIT-COST", subsidy.render_markdown(model, res))

    def test_commercial_free_days_label_renamed(self):
        rendered = commercial.render_markdown(OPP001, commercial.compute_model(OPP001))
        self.assertIn("drawn-balance funding", rendered)
        self.assertNotIn("Max free-credit days", rendered)


class TestRampModel(unittest.TestCase):
    """Audit D-1."""

    def test_hand_computed_case(self):
        # contribution 100, fixed 1000, active 20, ramp 10 -> merchants 2m/mo;
        # net = 200m - 1000 >= 0 at m=5; cumulative: -800-600-400-200+0+200... >= 0 at m=9
        case = _case()
        r = commercial.compute_case("t", case)
        r.contribution = 100.0
        r.inputs["active_merchants"] = (20.0, "A", "")
        r.inputs["fixed_costs_monthly"] = (1000.0, "A", "")
        out = ramp.analyse_case(r, months=24, ramp_months=10)
        self.assertEqual(out.monthly_breakeven_month, 5)
        self.assertEqual(out.cumulative_breakeven_month, 9)
        self.assertAlmostEqual(out.peak_funding_need, 2000.0)  # cumulative low at m=4/5
        self.assertGreater(out.end_cumulative, 0)

    def test_opp001_base_never_breaks_even_monthly(self):
        # 500 merchants x 136.5 < 150k fixed: the ramp makes D-1's point vividly
        ramps = ramp.analyse(OPP001, months=36, ramp_months=12)
        self.assertIsNone(ramps["base"].monthly_breakeven_month)
        self.assertGreater(ramps["base"].peak_funding_need, 1_000_000)
        self.assertIsNotNone(ramps["upside"].monthly_breakeven_month)

    def test_render(self):
        text = ramp.render_markdown(OPP001, ramp.analyse(OPP001))
        self.assertIn("Peak funding need", text)
        self.assertIn("Structurally absent", text)


class TestClassificationCanonicalisation(unittest.TestCase):
    """Audit D-2/AG-2: first enum word stated wins, everywhere."""

    def test_first_word_wins(self):
        self.assertEqual(backlog.classification_enum("Promising but unvalidated (borderline Weak)"), "promising")
        self.assertEqual(backlog.classification_enum("Weak (borderline Promising)"), "weak")
        self.assertEqual(backlog.classification_enum("Unscored (candidate)"), "unscored")
        self.assertIsNone(backlog.classification_enum("TBD"))

    def test_check_catches_cross_artifact_mismatch(self):
        # flip one scorecard's proposed classification in a sandbox and expect check to fail
        import shutil, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(REPO_ROOT / "knowledge-base", root / "knowledge-base")
            card_path = root / "knowledge-base/opportunity-scores/opp-013-scorecard.json"
            card = json.loads(card_path.read_text())
            card["proposed_classification"] = "weak"  # backlog says promising
            card_path.write_text(json.dumps(card))
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.run_check(root)
            self.assertEqual(code, 1)
            self.assertIn("scorecard proposes 'weak'", buf.getvalue())


class TestWriteGuardWhitelist(unittest.TestCase):
    """Audit A-1: bypass shapes must be refused."""

    def test_bypass_shapes(self):
        for bad in (
            "knowledge-base/customer-evidence/x.md",
            "knowledge-base/customer-evidence-2/x.md",     # the audit's bypass shape
            "knowledge-base/segments/x.md",
            "knowledge-base/newfolder/x.md",               # whitelist: unknown kb dir refused
            "customer-intelligence/tools/x.md",
            "shared/x.md",
        ):
            self.assertFalse(cli._write_allowed((REPO_ROOT / bad).resolve()), bad)
        for good in (
            "knowledge-base/commercial-models/x.md",
            "knowledge-base/product-ideas/x.md",
            "knowledge-base/validation/x.md",
            "knowledge-base/opportunity-scores/x.md",
            "opportunity-intelligence/tools/x.md",
        ):
            self.assertTrue(cli._write_allowed((REPO_ROOT / good).resolve()), good)


class TestELabelGate(unittest.TestCase):
    """Audit H-1: (E) labels require a benchmark-citing note — via check."""

    def test_unsourced_e_label_fails_check(self):
        import shutil, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(REPO_ROOT / "knowledge-base", root / "knowledge-base")
            path = root / "knowledge-base/commercial-models/opp-001-inputs.json"
            model = json.loads(path.read_text())
            model["cases"]["base"]["ecl_rate_annual"] = {"value": 0.06, "label": "E"}  # no note
            path.write_text(json.dumps(model))
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.run_check(root)
            self.assertEqual(code, 1)
            self.assertIn("labelled (E)", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
