"""Tests for the opportunity_engine package.

Run from repo root:
  python3 -m unittest discover -s opportunity-intelligence/tools/tests -v

The commercial/subsidy expectations pin the engine to the hand-built OPP-001
markdown model and the OPP-002 test-case table, so drift between code and the
published numbers is caught.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from opportunity_engine import commercial, evidence, scoring, subsidy  # noqa: E402

OPP001 = json.loads(
    (REPO_ROOT / "knowledge-base/commercial-models/opp-001-inputs.json").read_text()
)
OPP002 = json.loads(
    (REPO_ROOT / "knowledge-base/commercial-models/opp-002-subsidy-inputs.json").read_text()
)
SCORECARD = json.loads(
    (REPO_ROOT / "knowledge-base/opportunity-scores/opp-001-scorecard.json").read_text()
)


class TestCommercialModel(unittest.TestCase):
    def setUp(self):
        self.results = commercial.compute_model(OPP001)

    def test_base_case_matches_published_model(self):
        b = self.results["base"]
        self.assertAlmostEqual(b.routed_flow, 36_000, delta=1)
        self.assertAlmostEqual(b.drawn_balance, 17_500, delta=5)
        self.assertAlmostEqual(b.financing_revenue, 291.7, delta=1)
        self.assertAlmostEqual(b.payment_revenue, 108, delta=1)
        # markdown model: contribution +137 base
        self.assertAlmostEqual(b.contribution, 137, delta=2)
        self.assertAlmostEqual(b.contribution_pct, 33, delta=1)
        # markdown model: break-even ~1,100 merchants
        self.assertAlmostEqual(b.breakeven_merchants, 1100, delta=15)

    def test_downside_is_loss_making(self):
        d = self.results["downside"]
        self.assertAlmostEqual(d.contribution, -59, delta=2)
        self.assertIsNone(d.breakeven_merchants)

    def test_upside_case(self):
        u = self.results["upside"]
        self.assertAlmostEqual(u.contribution, 977, delta=3)
        self.assertAlmostEqual(u.breakeven_merchants, 123, delta=3)

    def test_free_day_ceiling_base(self):
        b = self.results["base"]
        # 108 payment margin / (17.5k * 8% / 365) per-day funding cost ~ 28 gross days
        self.assertAlmostEqual(b.max_free_days_gross, 28.2, delta=0.5)
        self.assertLess(b.max_free_days_net, b.max_free_days_gross)

    def test_missing_case_rejected(self):
        broken = {"opportunity_id": "X", "name": "x", "cases": {"base": OPP001["cases"]["base"]}}
        with self.assertRaises(commercial.InputError):
            commercial.compute_model(broken)

    def test_missing_input_rejected(self):
        case = dict(OPP001["cases"]["base"])
        del case["ecl_rate_annual"]
        with self.assertRaises(commercial.InputError):
            commercial.compute_case("base", case)

    def test_bad_label_rejected(self):
        case = dict(OPP001["cases"]["base"])
        case["ecl_rate_annual"] = {"value": 0.06, "label": "X"}
        with self.assertRaises(commercial.InputError):
            commercial.compute_case("base", case)

    def test_render_markdown_runs(self):
        report = commercial.render_markdown(OPP001, self.results)
        self.assertIn("OPP-001", report)
        self.assertIn("Break-even merchants", report)
        self.assertIn("never", report)  # downside


class TestSubsidyModel(unittest.TestCase):
    def setUp(self):
        self.results = subsidy.compute_model(OPP002)

    def test_net_margins_match_test_case_table(self):
        # opportunity-intelligence/test-cases/02-supplier-payment-card.md: 25 / 60 / 90 bps
        self.assertAlmostEqual(self.results["downside"].net_margin_bps, 25)
        self.assertAlmostEqual(self.results["base"].net_margin_bps, 60)
        self.assertAlmostEqual(self.results["upside"].net_margin_bps, 90)

    def test_max_free_days_match_test_case(self):
        # test case: ~11 / ~27 / ~41 days at 8% funding
        self.assertAlmostEqual(self.results["downside"].max_free_days_alone, 11.4, delta=0.3)
        self.assertAlmostEqual(self.results["base"].max_free_days_alone, 27.4, delta=0.3)
        self.assertAlmostEqual(self.results["upside"].max_free_days_alone, 41.1, delta=0.3)

    def test_offered_20_day_package(self):
        # 20 free days: affordable at base/upside payment margin, not at downside
        self.assertFalse(self.results["downside"].package_affordable)
        self.assertTrue(self.results["base"].package_affordable)
        self.assertTrue(self.results["upside"].package_affordable)

    def test_cashback_stacking_is_charged_to_same_budget(self):
        case = dict(OPP002["cases"]["base"])
        case["offered_cashback_pct"] = {"value": 2.0, "label": "A"}  # the OPP-003 error
        r = subsidy.compute_case("base", case)
        self.assertFalse(r.package_affordable)  # 200bps cashback >> 60bps margin


class TestScoring(unittest.TestCase):
    def test_opp001_scorecard(self):
        ev = scoring.evaluate(SCORECARD)
        self.assertEqual(ev["assumption_count"], 15)
        self.assertTrue(ev["assumption_capped"])
        self.assertEqual(ev["max_classification"], "promising")
        self.assertEqual(ev["composite_indicative"], 3.5)
        self.assertEqual(ev["violations"], [])  # proposed 'promising' is allowed

    def test_strong_blocked_when_assumption_capped(self):
        card = json.loads(json.dumps(SCORECARD))
        card["proposed_classification"] = "strong"
        ev = scoring.evaluate(card)
        self.assertEqual(len(ev["violations"]), 1)

    def test_all_17_dimensions_required(self):
        card = json.loads(json.dumps(SCORECARD))
        del card["scores"]["credit_need"]
        with self.assertRaises(commercial.InputError):
            scoring.evaluate(card)

    def test_half_points_rejected(self):
        card = json.loads(json.dumps(SCORECARD))
        card["scores"]["credit_need"]["score"] = 4.5
        with self.assertRaises(commercial.InputError):
            scoring.evaluate(card)

    def test_critical_floor_flags(self):
        card = json.loads(json.dumps(SCORECARD))
        card["scores"]["switching_intent"]["score"] = 2
        card["scores"]["credit_risk_visibility"]["score"] = 1
        ev = scoring.evaluate(card)
        self.assertIn("switching_intent <= 2", ev["critical_flags"])
        self.assertIn("credit_risk_visibility <= 2 on a lending product", ev["critical_flags"])


FIXTURE_RECORD = """# Records 2026-W28

## EV-2026-W28-001 — Restaurant owner using personal card for stock

**Status:** active
**Created:** 2026-07-08 · **Last verified:** 2026-07-08

### Who

| Field | Value |
|---|---|
| Customer segment | SEG-001 |

### Assessment

| Field | Value |
|---|---|
| Evidence confidence | Medium — single behavioural source |

### Scores (1–5, per frameworks/evidence-scoring.md)

```
Frequency ................ 3
Severity ................. 4
Financial cost ........... 4
Urgency .................. 3
Dissatisfaction .......... 4
Workaround cost .......... 5
Switching intent ......... 2
Willingness to pay ....... 4
BOTIM relevance .......... 5
Evidence strength ........ 2
```

## EV-2026-W28-002 — Second record, minimal

**Status:** needs-more-evidence
"""


class TestEvidenceParser(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        records = Path(self.tmp.name) / "records"
        records.mkdir()
        (records / "2026-W28.md").write_text(FIXTURE_RECORD, encoding="utf-8")
        self.records = evidence.load_records(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parses_records(self):
        self.assertEqual(len(self.records), 2)
        rec = self.records["EV-2026-W28-001"]
        self.assertEqual(rec["status"], "active")
        self.assertEqual(rec["segment"], "SEG-001")
        self.assertEqual(rec["scores"]["evidence strength"], 2)
        self.assertEqual(len(rec["scores"]), 10)

    def test_citation_check(self):
        result = evidence.check_citations(
            ["EV-2026-W28-001", "EV-2026-W28-999", "not-an-id"], self.records
        )
        self.assertEqual(result["valid"], ["EV-2026-W28-001"])
        self.assertEqual(result["missing"], ["EV-2026-W28-999"])
        self.assertEqual(result["malformed"], ["not-an-id"])
        # strength 2 => citable only as a lead
        self.assertIn("EV-2026-W28-001", result["weak"])

    def test_weak_status_flagged(self):
        result = evidence.check_citations(["EV-2026-W28-002"], self.records)
        self.assertIn("EV-2026-W28-002", result["weak"])

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(evidence.load_records(empty), {})


if __name__ == "__main__":
    unittest.main()
