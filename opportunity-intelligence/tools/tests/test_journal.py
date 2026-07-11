"""Tests for the calibrated decision journal (journal.py)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from opportunity_engine import journal  # noqa: E402
from opportunity_engine.commercial import InputError  # noqa: E402


def _fresh():
    return {"predictions": []}


class TestJournalLifecycle(unittest.TestCase):
    def test_add_assigns_sequential_ids(self):
        data = _fresh()
        a = journal.add(data, "thing A happens", 0.3, "2026-07-11", "2026-08-01")
        b = journal.add(data, "thing B happens", 0.7, "2026-07-11", "2026-08-01")
        self.assertEqual((a["id"], b["id"]), ("PRED-001", "PRED-002"))

    def test_resolve_and_no_reresolve(self):
        data = _fresh()
        journal.add(data, "x", 0.3, "2026-07-11", "2026-08-01")
        p = journal.resolve(data, "PRED-001", True, "2026-08-02", "it happened")
        self.assertTrue(p["outcome"])
        with self.assertRaises(InputError):
            journal.resolve(data, "PRED-001", False, "2026-08-03")

    def test_certainty_rejected(self):
        data = _fresh()
        for bad_p in (0, 1, 1.5, -0.1):
            with self.assertRaises(InputError):
                journal.add(data, "x", bad_p, "2026-07-11", "2026-08-01")

    def test_validation_catches_garbage(self):
        for broken in (
            {"predictions": [{"id": "PRED-001", "statement": "x", "p": 0.5, "made": "2026-07-11"}]},  # no resolve_by
            {"predictions": [{"id": "BAD-1", "statement": "x", "p": 0.5, "made": "2026-07-11", "resolve_by": "2026-08-01"}]},
            {"predictions": [{"id": "PRED-001", "statement": " ", "p": 0.5, "made": "2026-07-11", "resolve_by": "2026-08-01"}]},
            {"predictions": [{"id": "PRED-001", "statement": "x", "p": 0.5, "made": "July 11", "resolve_by": "2026-08-01"}]},
            {"predictions": [
                {"id": "PRED-001", "statement": "x", "p": 0.5, "made": "2026-07-11", "resolve_by": "2026-08-01"},
                {"id": "PRED-001", "statement": "y", "p": 0.5, "made": "2026-07-11", "resolve_by": "2026-08-01"},
            ]},
            {"predictions": [{"id": "PRED-001", "statement": "x", "p": 0.5, "made": "2026-07-11",
                              "resolve_by": "2026-08-01", "outcome": True}]},  # resolved without date
        ):
            with self.assertRaises(InputError):
                journal.validate(broken)

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "j.json"
            data = _fresh()
            journal.add(data, "x", 0.3, "2026-07-11", "2026-08-01", ["VE-001"])
            journal.save(data, path)
            again = journal.load(path)
            self.assertEqual(again["predictions"][0]["links"], ["VE-001"])

    def test_load_missing_file_is_empty_journal(self):
        self.assertEqual(journal.load("/nonexistent/journal.json"), {"predictions": []})


class TestCalibration(unittest.TestCase):
    def _resolved(self, pairs):
        data = _fresh()
        for i, (p, outcome) in enumerate(pairs):
            journal.add(data, f"pred {i}", p, "2026-07-11", "2026-08-01")
            journal.resolve(data, f"PRED-{i+1:03d}", outcome, "2026-08-02")
        return data

    def test_brier_perfect_and_coinflip(self):
        sharp = self._resolved([(0.9, True), (0.1, False)])
        self.assertAlmostEqual(journal.calibration(sharp)["brier"], 0.01, places=6)
        vague = self._resolved([(0.5, True), (0.5, False)])
        self.assertAlmostEqual(journal.calibration(vague)["brier"], 0.25, places=6)

    def test_buckets(self):
        data = self._resolved([(0.3, False), (0.3, True), (0.7, True)])
        cal = journal.calibration(data)
        b_low = next(b for b in cal["buckets"] if b["range"] == "20%–40%")
        self.assertEqual(b_low["n"], 2)
        self.assertAlmostEqual(b_low["observed"], 0.5)

    def test_overdue_flagging(self):
        data = _fresh()
        journal.add(data, "late", 0.5, "2026-07-01", "2026-07-05")
        journal.add(data, "future", 0.5, "2026-07-01", "2026-12-31")
        cal = journal.calibration(data, today="2026-07-11")
        self.assertEqual([p["statement"] for p in cal["overdue"]], ["late"])

    def test_render(self):
        cal = journal.calibration(self._resolved([(0.3, False)]))
        report = journal.render_markdown(cal)
        self.assertIn("Brier score", report)


class TestSeededJournal(unittest.TestCase):
    def test_repo_journal_valid_and_open(self):
        data = journal.load(REPO_ROOT / "knowledge-base/product-ideas/decision-journal.json")
        self.assertGreaterEqual(len(data["predictions"]), 5)
        cal = journal.calibration(data)
        self.assertEqual(cal["n_resolved"], 0)
        # every seeded prediction links to a real artefact id
        for p in data["predictions"]:
            self.assertTrue(p["links"], p["id"])


if __name__ == "__main__":
    unittest.main()
