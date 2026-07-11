"""Fixture-based unit tests for sync.py (the A→B evidence bridge)."""

import json
import sys
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from opportunity_engine import sync  # noqa: E402

SCORECARD = json.loads(
    (REPO_ROOT / "knowledge-base/opportunity-scores/opp-001-scorecard.json").read_text()
)


def _record(rid, strength, severity=4, frequency=5):
    return {
        "id": rid,
        "status": "active",
        "scores": {
            "severity": severity,
            "frequency": frequency,
            "financial cost": 4,
            "urgency": 3,
            "dissatisfaction": 4,
            "workaround cost": 4,
            "switching intent": 3,
            "willingness to pay": 4,
            "botim relevance": 5,
            "evidence strength": strength,
        },
    }


def _card_citing(*ids):
    card = json.loads(json.dumps(SCORECARD))
    card["scores"]["pain_severity"]["basis"] = "supported by " + ", ".join(ids)
    return card


class TestSyncLogic(unittest.TestCase):
    def test_flip_assumption_suggested_for_cited_a_score(self):
        records = {"EV-2026-W01-001": _record("EV-2026-W01-001", strength=4, severity=4)}
        report = sync.suggestions_for_scorecard(_card_citing("EV-2026-W01-001"), records)
        by_dim = {s["dimension"]: s for s in report["suggestions"]}
        # pain_severity is (A)=4 in the card, evidence implies 4 -> flip-assumption only
        self.assertEqual(by_dim["pain_severity"]["kind"], "flip-assumption")
        self.assertEqual(by_dim["pain_severity"]["implied"], 4)

    def test_rescore_when_evidence_diverges(self):
        records = {"EV-2026-W01-001": _record("EV-2026-W01-001", strength=4, severity=2)}
        report = sync.suggestions_for_scorecard(_card_citing("EV-2026-W01-001"), records)
        by_dim = {s["dimension"]: s for s in report["suggestions"]}
        self.assertEqual(by_dim["pain_severity"]["kind"], "both")  # (A) and diverges
        self.assertEqual(by_dim["pain_severity"]["implied"], 2)

    def test_weak_records_never_drive_suggestions(self):
        records = {"EV-2026-W01-001": _record("EV-2026-W01-001", strength=2, severity=1)}
        report = sync.suggestions_for_scorecard(_card_citing("EV-2026-W01-001"), records)
        self.assertEqual(report["suggestions"], [])
        self.assertEqual(report["excluded_weak"], ["EV-2026-W01-001"])

    def test_unresolved_citations_reported(self):
        report = sync.suggestions_for_scorecard(_card_citing("EV-2026-W01-999"), {})
        self.assertEqual(report["unresolved"], ["EV-2026-W01-999"])
        self.assertEqual(report["suggestions"], [])

    def test_multiple_records_averaged_with_rounding(self):
        records = {
            "EV-2026-W01-001": _record("EV-2026-W01-001", 4, severity=3),
            "EV-2026-W01-002": _record("EV-2026-W01-002", 3, severity=4),
        }
        report = sync.suggestions_for_scorecard(
            _card_citing("EV-2026-W01-001", "EV-2026-W01-002"), records
        )
        by_dim = {s["dimension"]: s for s in report["suggestions"]}
        self.assertEqual(by_dim["pain_severity"]["implied"], 4)  # mean 3.5 rounds to 4
        self.assertEqual(by_dim["pain_severity"]["n_records"], 2)

    def test_no_citations_no_suggestions(self):
        card = json.loads(json.dumps(SCORECARD))  # OPP-001 cites nothing
        report = sync.suggestions_for_scorecard(card, {})
        self.assertEqual(report["cited"], [])
        self.assertEqual(report["suggestions"], [])

    def test_render(self):
        text = sync.render_markdown([sync.suggestions_for_scorecard(SCORECARD, {})])
        self.assertIn("OPP-001", text)


if __name__ == "__main__":
    unittest.main()
