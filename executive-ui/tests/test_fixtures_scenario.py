"""EV-TEST-001 synthetic scenario — exercised in an isolated sandbox KB, so
LIVE knowledge-base data is never modified. Also covers score before/after
rendering. The sandbox symlinks the real engine tool dirs (read-only reuse)
and builds a tiny conforming knowledge base in a tmp dir."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
REPO = UI.parents[0]
sys.path.insert(0, str(UI))

from adapter import collect  # noqa: E402
from render import evidence, feed, overview  # noqa: E402

# a conforming synthetic evidence record (the EV-TEST-001 scenario: a second
# independent first-person UAE importer paying for supplier financing)
SYNTH_RECORD = """# Records SANDBOX

## EV-2026-W28-777 — SYNTHETIC (EV-TEST-001): second first-person UAE importer pays for supplier financing

**Status:** active
**Created:** 2026-07-11 · **Last verified:** 2026-07-11

### Who
| Field | Value |
|---|---|
| Customer segment | SEG-uae-importers-upfront-pay |

### Assessment
| Field | Value |
|---|---|
| Evidence confidence | Medium — first-person behavioural, single but dated (synthetic fixture) |

### Scores (1–5)
```
Frequency ................ 3
Severity ................. 4
Financial cost ........... 4
Urgency .................. 3
Dissatisfaction .......... 4
Workaround cost .......... 4
Switching intent ......... 3
Willingness to pay ....... 4
BOTIM relevance .......... 5
Evidence strength ........ 3
```
"""

SCORECARD = {
    "opportunity_id": "OPP-777", "name": "SYNTHETIC import financing (sandbox)",
    "is_lending_product": True, "proposed_classification": "promising",
    "evidence_confidence": "medium",
    "scores": {k: {"score": 3, "assumption": True, "basis": "sandbox"} for k in [
        "pain_severity", "pain_frequency", "financial_impact", "workaround_cost",
        "switching_intent", "willingness_to_pay", "digital_readiness", "payment_volume",
        "credit_need", "botim_distribution_advantage", "transaction_data_advantage",
        "payment_revenue_potential", "lending_revenue_potential", "credit_risk_visibility",
        "competitive_defensibility", "ease_of_validation", "mvp_feasibility_7wk"]},
}
# make two factors cite the synthetic record (behavioural WTP + credit need)
SCORECARD["scores"]["willingness_to_pay"] = {
    "score": 4, "assumption": False, "basis": "EV-2026-W28-777 (pays for financing = behavioural WTP)"}
SCORECARD["scores"]["credit_need"] = {
    "score": 4, "assumption": False, "basis": "EV-2026-W28-777 (recurring 60-day gap)"}

BACKLOG = """# Backlog
## Backlog
| ID | Proposition | Segment | Classification | Composite | Evidence confidence | Top invalidation risk | Next action | Owner | Last updated |
|---|---|---|---|---|---|---|---|---|---|
| OPP-777 | Sandbox import financing | SEG-uae-importers-upfront-pay | Promising but unvalidated | 3.2 | Medium | demand | VE-004 | B | 2026-07-11 |

## Evidence-request queue (cross-module)
| Req ID | For proposition | Evidence needed | Why it matters | Status |
|---|---|---|---|---|
| REQ-777 | OPP-777 | more first-person | segment | Open |

## Archive
| ID | Proposition | Rejected/parked on | Decisive reason | Reopen trigger |
|---|---|---|---|---|
"""

SEGMENT = """# SEG-uae-importers-upfront-pay — sandbox
**Created:** 2026-07-11 · **Last verified:** 2026-07-11 · **Confidence:** Medium
"""


class TestSyntheticScenario(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="exec-ui-sandbox-")
        root = Path(cls.tmp)
        # symlink real engine tool dirs (read-only reuse — the single source of truth)
        (root / "opportunity-intelligence").symlink_to(REPO / "opportunity-intelligence")
        (root / "intelligence-monitoring").symlink_to(REPO / "intelligence-monitoring")
        kb = root / "knowledge-base"
        (kb / "customer-evidence" / "records").mkdir(parents=True)
        (kb / "opportunity-scores").mkdir(parents=True)
        (kb / "product-ideas").mkdir(parents=True)
        (kb / "segments").mkdir(parents=True)
        (kb / "customer-evidence" / "records" / "2026-W28.md").write_text(SYNTH_RECORD, encoding="utf-8")
        import json
        (kb / "opportunity-scores" / "opp-777-scorecard.json").write_text(json.dumps(SCORECARD), encoding="utf-8")
        (kb / "product-ideas" / "BACKLOG.md").write_text(BACKLOG, encoding="utf-8")
        (kb / "segments" / "SEG-uae-importers-upfront-pay.md").write_text(SEGMENT, encoding="utf-8")
        cls.model = collect.build_model(str(root))
        cls.live_records_before = (REPO / "knowledge-base/customer-evidence/records/2026-W28.md").read_text()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_synthetic_opportunity_built(self):
        ids = [o.id for o in self.model.opportunities]
        self.assertEqual(ids, ["OPP-777"])
        o = self.model.opportunities[0]
        self.assertEqual(o.raw_score, sum(f.score for f in o.factors))

    def test_synthetic_evidence_is_primary_and_strong(self):
        ref = next(r for r in self.model.evidence if r.ev_id == "EV-2026-W28-777")
        self.assertTrue(ref.resolved)
        self.assertFalse(ref.weak)          # strength 3 → score-driving
        self.assertEqual(ref.role, "primary")
        self.assertEqual(ref.strength, 3)

    def test_evidence_flows_to_factor(self):
        o = self.model.opportunities[0]
        wtp = next(f for f in o.factors if f.key == "willingness_to_pay")
        self.assertIn("EV-2026-W28-777", wtp.evidence_ids)
        self.assertFalse(wtp.assumption)    # behavioural → not an assumption

    def test_renders_without_error(self):
        self.assertIn("OPP-777", overview.render(self.model))
        self.assertIn("EV-2026-W28-777", evidence.render(self.model))

    def test_before_after_rendering(self):
        # inject a resolved-prediction feed item and assert before/after renders
        from adapter import model as M
        self.model.feed.insert(0, M.FeedItem(
            id="PRED-TEST", kind="prediction-resolved", tier="—",
            title="synthetic prediction", detected_at="2026-07-11",
            before_after={"before": "p=40%", "after": "True"}))
        html = feed.render(self.model)
        self.assertIn("before: p=40%", html)
        self.assertIn("after: True", html)

    def test_live_data_untouched(self):
        after = (REPO / "knowledge-base/customer-evidence/records/2026-W28.md").read_text()
        self.assertEqual(self.live_records_before, after)
        # the synthetic id must NOT have leaked into the live knowledge base
        self.assertNotIn("EV-2026-W28-777", after)


if __name__ == "__main__":
    unittest.main()
