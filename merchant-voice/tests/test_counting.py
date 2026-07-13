"""Denominator foundation tests — each count has one fixed definition;
see app/counting.py for the exact semantics."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import RESEARCHER, make_active_campaign_with_approved_guide, make_dbs, make_participant

from app import counting, responses, suppression


class CountingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn, self.identity_conn, self.config = make_dbs(self.tmp.name)
        self.clock_n = 0
        self.camp, self.guide = make_active_campaign_with_approved_guide(
            self.conn, self.config, self._clock)
        self.q1 = self.guide["questions"][0]["question_id"]

    def _clock(self):
        self.clock_n += 1
        return f"2026-01-01T00:00:{self.clock_n:02d}Z"

    def test_all_zero_for_empty_campaign(self):
        counts = counting.compute(self.conn, self.camp["campaign_id"])
        self.assertEqual(counts["invited_count"], 0)
        self.assertEqual(counts["enrolled_count"], 0)
        self.assertEqual(counts["submitted_response_count"], 0)
        self.assertEqual(counts["excluded_or_suppressed_count"], 0)

    def test_invited_counts_all_participants_regardless_of_status(self):
        make_participant(self.conn, self.identity_conn, self.config, self._clock, self.camp["campaign_id"])
        make_participant(self.conn, self.identity_conn, self.config, self._clock, self.camp["campaign_id"])
        counts = counting.compute(self.conn, self.camp["campaign_id"])
        self.assertEqual(counts["invited_count"], 2)
        self.assertEqual(counts["enrolled_count"], 0)  # no responses yet

    def test_enrolled_and_included_after_response_submitted(self):
        p = make_participant(self.conn, self.identity_conn, self.config, self._clock, self.camp["campaign_id"])
        responses.create(self.conn, self.config, RESEARCHER, {
            "campaign_id": self.camp["campaign_id"], "participant_id": p["participant_id"],
            "guide_id": self.guide["guide_id"], "method": "interview",
            "answers": [{"question_id": self.q1, "answer": "a synthetic answer"}]}, self._clock())
        counts = counting.compute(self.conn, self.camp["campaign_id"])
        self.assertEqual(counts["invited_count"], 1)
        self.assertEqual(counts["enrolled_count"], 1)
        self.assertEqual(counts["submitted_response_count"], 1)
        self.assertEqual(counts["valid_participant_count"], 1)
        self.assertEqual(counts["included_participant_count"], 1)
        self.assertEqual(counts["excluded_or_suppressed_count"], 0)

    def test_suppressed_participant_excluded_from_valid_and_included(self):
        p1 = make_participant(self.conn, self.identity_conn, self.config, self._clock, self.camp["campaign_id"])
        p2 = make_participant(self.conn, self.identity_conn, self.config, self._clock, self.camp["campaign_id"])
        for p in (p1, p2):
            responses.create(self.conn, self.config, RESEARCHER, {
                "campaign_id": self.camp["campaign_id"], "participant_id": p["participant_id"],
                "guide_id": self.guide["guide_id"], "method": "interview",
                "answers": [{"question_id": self.q1, "answer": f"answer for {p['participant_id']}"}]},
                self._clock())
        suppression.suppress_participant(self.conn, RESEARCHER, p1["participant_id"], "withdrawn",
                                         self._clock(), transcript_dir=self.config.transcript_dir)
        counts = counting.compute(self.conn, self.camp["campaign_id"])
        self.assertEqual(counts["invited_count"], 2)
        self.assertEqual(counts["valid_participant_count"], 1)
        self.assertEqual(counts["included_participant_count"], 1)
        self.assertEqual(counts["excluded_or_suppressed_count"], 1)

    def test_invited_but_not_enrolled_counts_as_excluded(self):
        make_participant(self.conn, self.identity_conn, self.config, self._clock, self.camp["campaign_id"])
        counts = counting.compute(self.conn, self.camp["campaign_id"])
        self.assertEqual(counts["excluded_or_suppressed_count"], 1)

    def test_no_sample_size_field_exposed(self):
        counts = counting.compute(self.conn, self.camp["campaign_id"])
        self.assertNotIn("sample_size", counts)


if __name__ == "__main__":
    unittest.main(verbosity=2)
