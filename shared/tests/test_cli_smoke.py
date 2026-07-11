"""CLI smoke matrix: every engine command executed as a real subprocess
against the real repository — success paths, failure paths (typed exit
codes), and determinism. This is the closest layer to how a human (or the
agent) actually drives the tools."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN = [sys.executable, "opportunity-intelligence/tools/run.py"]

MODELS = "knowledge-base/commercial-models"
SCORES = "knowledge-base/opportunity-scores"

# (args, expected_exit, must_contain_in_stdout)
SUCCESS_MATRIX = (
    (["model", f"{MODELS}/opp-001-inputs.json"], "Contribution / merchant"),
    (["model", f"{MODELS}/opp-009-inputs.json"], "Contribution / merchant"),
    (["model", f"{MODELS}/opp-010-inputs.json"], "Effective payment take"),
    (["subsidy", f"{MODELS}/opp-002-subsidy-inputs.json"], "Net payment margin"),
    (["score", f"{SCORES}/opp-001-scorecard.json"], "15/17"),
    (["score", f"{SCORES}/opp-009-scorecard.json"], "capped at 'promising'"),
    (["score", f"{SCORES}/opp-010-scorecard.json"], "7/17"),
    (["sensitivity", f"{MODELS}/opp-001-inputs.json"], "Validate first"),
    (["sensitivity", f"{MODELS}/opp-010-inputs.json", "--degrade", "0.25"], "Validate first"),
    (["simulate", f"{MODELS}/opp-001-inputs.json", "--n", "300"], "P(loss-making"),
    (["stress", f"{MODELS}/opp-001-inputs.json"], "perfect_storm"),
    (["stress", f"{MODELS}/opp-010-inputs.json", "--case", "downside"], "scenarios kill"),
    (["grid", f"{MODELS}/opp-001-inputs.json", "--x", "routed_share",
      "--y", "ecl_rate_annual", "--steps", "3"], "viability frontier"),
    (["evidence"], "Evidence records loaded: 19"),
    (["cite", "EV-2026-W28-009,EV-2026-W28-004"], '"missing": []'),
    (["verdict", "knowledge-base/validation/VE-001-result.json"], "PENDING"),
    (["verdict", "knowledge-base/validation/VE-003-result.json"], "PENDING"),
    (["calibration"], "Brier score"),
    (["sync"], "Report-only"),
    (["check"], "CHECK PASSED"),
)


def run_cli(args, cwd=REPO_ROOT):
    return subprocess.run(RUN + list(args), cwd=cwd, capture_output=True, text=True)


class TestSuccessMatrix(unittest.TestCase):
    def test_every_command_succeeds_with_expected_output(self):
        for args, marker in SUCCESS_MATRIX:
            with self.subTest(cmd=" ".join(args)):
                proc = run_cli(args)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn(marker, proc.stdout)


class TestFailurePaths(unittest.TestCase):
    def test_missing_file_fails_nonzero(self):
        proc = run_cli(["model", "does-not-exist.json"])
        self.assertNotEqual(proc.returncode, 0)

    def test_unknown_citation_exits_2(self):
        proc = run_cli(["cite", "EV-2099-W01-001"])
        self.assertEqual(proc.returncode, 2)

    def test_cap_violation_exits_2(self):
        card = json.loads(
            (REPO_ROOT / f"{SCORES}/opp-001-scorecard.json").read_text(encoding="utf-8"))
        card["proposed_classification"] = "strong"
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(card, f)
        proc = run_cli(["score", f.name])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not allowed", proc.stdout)
        Path(f.name).unlink()

    def test_write_into_workstream_a_refused(self):
        proc = run_cli(["model", f"{MODELS}/opp-001-inputs.json",
                        "--write", "knowledge-base/customer-evidence/hijack.md"])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("refusing", proc.stdout + proc.stderr)
        self.assertFalse((REPO_ROOT / "knowledge-base/customer-evidence/hijack.md").exists())

    def test_predict_certainty_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            jpath = Path(tmp) / "j.json"
            proc = run_cli(["predict", "certain thing", "--p", "1.0",
                            "--resolve-by", "2027-01-01", "--journal", str(jpath)])
            self.assertNotEqual(proc.returncode, 0)


class TestDeterminism(unittest.TestCase):
    def test_simulate_identical_across_runs(self):
        a = run_cli(["simulate", f"{MODELS}/opp-001-inputs.json", "--n", "500", "--seed", "9"])
        b = run_cli(["simulate", f"{MODELS}/opp-001-inputs.json", "--n", "500", "--seed", "9"])
        self.assertEqual(a.stdout, b.stdout)

    def test_check_and_sync_idempotent(self):
        for cmd in (["check"], ["sync"]):
            a, b = run_cli(cmd), run_cli(cmd)
            self.assertEqual(a.stdout, b.stdout, cmd)


class TestJournalCliLifecycle(unittest.TestCase):
    def test_same_day_resolution_refused_then_backdated_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            jpath = Path(tmp) / "j.json"
            p1 = run_cli(["predict", "sandbox thing happens", "--p", "0.4",
                          "--resolve-by", "2027-01-01", "--journal", str(jpath)])
            self.assertEqual(p1.returncode, 0)
            self.assertIn("PRED-001", p1.stdout)
            # adversarial test 7 (audit R-1): resolving a prediction the day it
            # was logged is calibration contamination and must be refused
            p2 = run_cli(["resolve", "PRED-001", "true", "--journal", str(jpath)])
            self.assertNotEqual(p2.returncode, 0)
            self.assertIn("contaminat", p2.stdout + p2.stderr)
            # backdate `made` (as a past prediction would be) — then the
            # lifecycle works and Brier computes
            data = json.loads(jpath.read_text())
            data["predictions"][0]["made"] = "2026-01-01"
            jpath.write_text(json.dumps(data))
            p3 = run_cli(["resolve", "PRED-001", "true", "--journal", str(jpath)])
            self.assertEqual(p3.returncode, 0)
            # double-resolve must fail: outcomes are immutable
            p4 = run_cli(["resolve", "PRED-001", "false", "--journal", str(jpath)])
            self.assertNotEqual(p4.returncode, 0)
            cal = run_cli(["calibration", "--journal", str(jpath)])
            self.assertIn("Brier score: 0.360", cal.stdout)  # (0.4-1)^2


if __name__ == "__main__":
    unittest.main()
