"""End-to-end lifecycle test: a synthetic opportunity (OPP-999) driven through
the ENTIRE agent pipeline in an isolated sandbox — real evidence in, verdict
and backlog action out — without touching the live knowledge base.

Stages exercised: A's real records → B scorecard citing them → engine model →
Monte Carlo → scenarios → sensitivity → sync bridge → experiment spec + result
→ pending verdict → field results → pass verdict → backlog update → journal
prediction + resolution → full knowledge-base sweep on the sandbox.
"""

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "opportunity-intelligence" / "tools"))

import run as cli  # noqa: E402
from opportunity_engine import (  # noqa: E402
    backlog, commercial, evidence, journal, montecarlo, results, scoring,
    sensitivity, stress, sync,
)

VE_SPEC = """# VE-999 — Sandbox experiment

- **Experiment ID:** VE-999
- **Proposition tested:** OPP-999
- **Hypothesis:** ≥30% of contacted merchants complete the waitlist.
- **Target participants:** sandbox merchants
- **Recruitment criteria:** include everyone synthetic
- **Method:** waitlist
- **Sample size:** 40 offers
- **Success threshold (pre-committed):** ≥30%
- **Failure threshold (pre-committed):** ≤10%
- **Duration:** 3 weeks
- **Data collected:** completion rate
- **Decision informed:** sandbox go/no-go
"""

VE_RESULT = {
    "experiment_id": "VE-999",
    "proposition": "OPP-999",
    "metrics": [{
        "name": "waitlist_completion_pct",
        "observed": None,
        "success": {"op": ">=", "value": 30},
        "failure": {"op": "<=", "value": 10},
    }],
    "on_pass": "Proceed to sandbox pilot",
    "on_fail": "Reclassify OPP-999 Weak",
    "on_inconclusive": "Extend by 20 offers",
}

BACKLOG_MD = """# Backlog

## Backlog

| ID | Proposition | Segment | Classification | Composite | Evidence confidence | Top invalidation risk | Next action | Owner | Last updated |
|---|---|---|---|---|---|---|---|---|---|
| OPP-999 | Sandbox settlement product | SEG-uae-online-sme-psp-merchants | Promising but unvalidated | 3.9 | Medium | sandbox risk | VE-999 | B | 2026-07-11 |

## Evidence-request queue (cross-module)

| Req ID | For proposition | Evidence needed | Why it matters | Status |
|---|---|---|---|---|
| REQ-101 | OPP-999 | segment sizing | volume input | Open |

## Archive

| ID | Proposition | Rejected/parked on | Decisive reason | Reopen trigger |
|---|---|---|---|---|
| OPP-998 | Sandbox reject | 2026-07-11 | Reject: fails switching test | none |
"""


class TestFullLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="e2e-sandbox-")
        root = Path(cls.tmp)
        kb = root / "knowledge-base"
        # A's real evidence, copied read-only into the sandbox
        shutil.copytree(REPO_ROOT / "knowledge-base" / "customer-evidence",
                        kb / "customer-evidence")
        for d in ("opportunity-scores", "commercial-models", "product-ideas", "validation"):
            (kb / d).mkdir(parents=True)

        # B artifacts for OPP-999, derived from real OPP-010 inputs/scorecard
        card = json.loads((REPO_ROOT / "knowledge-base/opportunity-scores/opp-010-scorecard.json")
                          .read_text(encoding="utf-8"))
        card["opportunity_id"] = "OPP-999"
        (kb / "opportunity-scores" / "opp-999-scorecard.json").write_text(
            json.dumps(card), encoding="utf-8")

        model = json.loads((REPO_ROOT / "knowledge-base/commercial-models/opp-010-inputs.json")
                           .read_text(encoding="utf-8"))
        model["opportunity_id"] = "OPP-999"
        (kb / "commercial-models" / "opp-999-inputs.json").write_text(
            json.dumps(model), encoding="utf-8")
        cls.model = model

        (kb / "product-ideas" / "BACKLOG.md").write_text(BACKLOG_MD, encoding="utf-8")
        (kb / "validation" / "VE-999-sandbox.md").write_text(VE_SPEC, encoding="utf-8")
        (kb / "validation" / "VE-999-result.json").write_text(
            json.dumps(VE_RESULT), encoding="utf-8")

        data = {"predictions": []}
        journal.add(data, "VE-999 passes its waitlist threshold", 0.5,
                    "2026-07-11", "2027-01-01", ["VE-999", "OPP-999"])
        journal.save(data, kb / "product-ideas" / "decision-journal.json")
        cls.root = root
        cls.kb = kb

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _check(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.run_check(self.root)
        return code, buf.getvalue()

    def test_stage_by_stage(self):
        # 1. Evidence: B's parser reads A's real records inside the sandbox
        records = evidence.load_records(self.kb / "customer-evidence")
        self.assertGreaterEqual(len(records), 19)

        # 2. Scorecard validates and its citations resolve
        card = json.loads((self.kb / "opportunity-scores/opp-999-scorecard.json").read_text())
        ev = scoring.evaluate(card)
        self.assertEqual(ev["violations"], [])
        cited = {m for e in ev["scores"].values()
                 for m in sync.EV_CITE_RE.findall(e["basis"])}
        self.assertTrue(cited and cited <= set(records))

        # 3. Engine: model, Monte Carlo, scenarios, sensitivity all run
        model_results = commercial.compute_model(self.model)
        self.assertGreater(model_results["base"].contribution, 0)
        sim = montecarlo.simulate(self.model, n=300, seed=1)
        self.assertGreaterEqual(sim.p_loss, 0.0)
        _, scenario_rows = stress.run(self.model, "base")
        self.assertEqual(len(scenario_rows), len(stress.SCENARIOS))
        _, tornado = sensitivity.analyse(self.model, "base", 0.5)
        self.assertTrue(tornado)

        # 4. Sync bridge produces a report for the sandbox scorecard
        reports = sync.analyse(self.root)
        self.assertEqual(reports[0]["opportunity_id"], "OPP-999")
        self.assertEqual(reports[0]["unresolved"], [])

        # 5. Pending verdict, then field results arrive, then PASS
        result = json.loads((self.kb / "validation/VE-999-result.json").read_text())
        self.assertEqual(results.evaluate(result)["verdict"], "pending")
        result["metrics"][0]["observed"] = 42
        verdict = results.evaluate(result)
        self.assertEqual(verdict["verdict"], "pass")
        self.assertIn("pilot", verdict["action"])
        (self.kb / "validation/VE-999-result.json").write_text(json.dumps(result))

        # 6. Journal: resolve the prediction on the outcome
        jpath = self.kb / "product-ideas/decision-journal.json"
        data = journal.load(jpath)
        journal.resolve(data, "PRED-001", True, "2026-07-11", "sandbox pass")
        journal.save(data, jpath)
        cal = journal.calibration(data)
        self.assertEqual(cal["n_resolved"], 1)

        # 7. Backlog stays consistent and references resolve
        _, issues = backlog.check(self.kb / "product-ideas/BACKLOG.md")
        self.assertEqual(issues, [])

        # 8. The full knowledge-base sweep passes on the sandbox
        code, output = self._check()
        self.assertEqual(code, 0, output)
        self.assertIn("verdict PASS", output)

    def test_sweep_catches_sandbox_corruption(self):
        # break the sandbox deliberately: dangling VE reference
        broken = BACKLOG_MD.replace("| VE-999 |", "| VE-777 |")
        path = self.kb / "product-ideas/BACKLOG.md"
        original = path.read_text(encoding="utf-8")
        try:
            path.write_text(broken, encoding="utf-8")
            code, output = self._check()
            self.assertEqual(code, 1)
            self.assertIn("VE-777", output)
        finally:
            path.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
