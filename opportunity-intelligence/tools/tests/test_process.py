"""Tests for experiments.py, backlog.py, and the `check` sweep.

The RealRepo tests run the validators against the repo's actual knowledge-base
files, so the check command doubles as CI for the knowledge base itself.
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import run as cli  # noqa: E402
from opportunity_engine import backlog, experiments  # noqa: E402

GOOD_VE = """# VE-101 — Fixture experiment

- **Experiment ID:** VE-101
- **Proposition tested:** OPP-101
- **Hypothesis:** ≥40% of merchants will sign up.
- **Target participants:** F&B merchants
- **Recruitment criteria:**
  - Include: owners
  - Exclude: friendlies
- **Method:** interviews
- **Sample size:** 15 interviews
- **Success threshold (pre-committed):** ≥40% completion
- **Failure threshold (pre-committed):** ≤15% completion
- **Duration:** 3 weeks
- **Data collected:** verbatims
- **Decision informed:** go/no-go on pilot
"""

GOOD_BACKLOG = """# Backlog

## Backlog

| ID | Proposition | Segment | Classification | Composite | Evidence confidence | Top invalidation risk | Next action | Owner | Last updated |
|---|---|---|---|---|---|---|---|---|---|
| OPP-101 | Thing | F&B | Promising but unvalidated | 3.5 | Low | risk | VE-101 | B | 2026-07-10 |

## Evidence-request queue (cross-module)

| Req ID | For proposition | Evidence needed | Why it matters | Status |
|---|---|---|---|---|
| REQ-101 | OPP-101 | pain data | scoring | Open |

## Archive

| ID | Proposition | Rejected/parked on | Decisive reason | Reopen trigger |
|---|---|---|---|---|
| OPP-102 | Bad idea | 2026-07-10 | Reject: fails switching test | strategy change |
"""


class TestExperimentValidator(unittest.TestCase):
    def _validate(self, text, name="VE-101-fixture.md"):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / name
            p.write_text(text, encoding="utf-8")
            return experiments.validate_file(p)

    def test_good_spec_passes(self):
        self.assertEqual(self._validate(GOOD_VE), [])

    def test_missing_failure_threshold(self):
        broken = GOOD_VE.replace("- **Failure threshold (pre-committed):** ≤15% completion\n", "")
        issues = self._validate(broken)
        self.assertTrue(any("failure threshold" in i for i in issues))

    def test_unquantified_hypothesis(self):
        vague = GOOD_VE.replace(
            "- **Hypothesis:** ≥40% of merchants will sign up.",
            "- **Hypothesis:** merchants want credit.",
        )
        issues = self._validate(vague)
        self.assertTrue(any("no number" in i for i in issues))

    def test_multiline_field_counts_as_filled(self):
        fields = None
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "VE-101-x.md"
            p.write_text(GOOD_VE, encoding="utf-8")
            fields = experiments.parse_file(p)
        self.assertIn("Include: owners", fields["recruitment criteria"])

    def test_filename_id_mismatch(self):
        issues = self._validate(GOOD_VE, name="VE-999-wrong.md")
        self.assertTrue(any("does not start with" in i for i in issues))

    def test_real_repo_ve_specs_pass(self):
        results = experiments.validate_dir(REPO_ROOT / "knowledge-base/validation")
        self.assertGreaterEqual(len(results), 2)
        for path, issues in results.items():
            self.assertEqual(issues, [], f"{path}: {issues}")


class TestBacklogChecker(unittest.TestCase):
    def _check(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "BACKLOG.md"
            p.write_text(text, encoding="utf-8")
            return backlog.check(p)

    def test_good_backlog_passes(self):
        data, issues = self._check(GOOD_BACKLOG)
        self.assertEqual(issues, [])
        self.assertEqual(len(data["backlog"]), 1)
        self.assertEqual(len(data["archive"]), 1)
        self.assertEqual(backlog.referenced_experiments(data), {"VE-101"})

    def test_duplicate_id_caught(self):
        dup = GOOD_BACKLOG.replace("OPP-102", "OPP-101")
        _, issues = self._check(dup)
        self.assertTrue(any("duplicate id OPP-101" in i for i in issues))

    def test_reject_in_live_backlog_caught(self):
        bad = GOOD_BACKLOG.replace("Promising but unvalidated", "Reject")
        _, issues = self._check(bad)
        self.assertTrue(any("belongs in the archive" in i for i in issues))

    def test_missing_req_reference_caught(self):
        bad = GOOD_BACKLOG.replace("| VE-101 |", "| REQ-999 |")
        _, issues = self._check(bad)
        self.assertTrue(any("REQ-999" in i for i in issues))

    def test_missing_next_action_caught(self):
        bad = GOOD_BACKLOG.replace("| VE-101 |", "| |")
        _, issues = self._check(bad)
        self.assertTrue(any("no next action" in i for i in issues))

    def test_real_repo_backlog_passes(self):
        data, issues = backlog.check(REPO_ROOT / "knowledge-base/product-ideas/BACKLOG.md")
        self.assertEqual(issues, [], issues)
        self.assertGreaterEqual(len(data["backlog"]), 7)
        self.assertGreaterEqual(len(data["requests"]), 6)
        self.assertEqual(len(data["archive"]), 1)


class TestCheckSweep(unittest.TestCase):
    def test_real_repo_check_passes(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.run_check(REPO_ROOT)
        output = buf.getvalue()
        self.assertEqual(code, 0, output)
        self.assertIn("CHECK PASSED", output)

    def test_check_fails_on_broken_scorecard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scores = root / "knowledge-base" / "opportunity-scores"
            scores.mkdir(parents=True)
            card = json.loads(
                (REPO_ROOT / "knowledge-base/opportunity-scores/opp-001-scorecard.json").read_text()
            )
            card["proposed_classification"] = "strong"  # violates the assumption cap
            (scores / "broken-scorecard.json").write_text(json.dumps(card), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.run_check(root)
            self.assertEqual(code, 1)
            self.assertIn("not allowed", buf.getvalue())

    def test_check_fails_on_dangling_ve_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ideas = root / "knowledge-base" / "product-ideas"
            ideas.mkdir(parents=True)
            (root / "knowledge-base" / "validation").mkdir()
            (ideas / "BACKLOG.md").write_text(GOOD_BACKLOG, encoding="utf-8")  # refs VE-101, no file
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.run_check(root)
            self.assertEqual(code, 1)
            self.assertIn("VE-101", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
