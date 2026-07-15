"""Tests for shared/freshness.py — deterministic bands, threshold
boundaries, reference-date priority, and honest unknowns (Phase 4)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared import freshness  # noqa: E402

TODAY = "2026-07-15"


class TestBands(unittest.TestCase):
    def test_fresh_at_zero_days(self):
        out = freshness.compute({"last_verified_at": TODAY}, today=TODAY)
        self.assertEqual(out["freshness_status"], "fresh")
        self.assertEqual(out["freshness_age_days"], 0)
        self.assertEqual(out["freshness_reference_date"], TODAY)

    def test_fresh_at_exact_boundary(self):
        out = freshness.compute({"last_verified_at": "2026-04-16"}, today=TODAY)  # 90 days
        self.assertEqual(out["freshness_age_days"], 90)
        self.assertEqual(out["freshness_status"], "fresh")

    def test_aging_one_past_fresh_boundary(self):
        out = freshness.compute({"last_verified_at": "2026-04-15"}, today=TODAY)  # 91 days
        self.assertEqual(out["freshness_age_days"], 91)
        self.assertEqual(out["freshness_status"], "aging")

    def test_aging_at_exact_stale_boundary(self):
        out = freshness.compute({"last_verified_at": "2026-01-16"}, today=TODAY)  # 180 days
        self.assertEqual(out["freshness_age_days"], 180)
        self.assertEqual(out["freshness_status"], "aging")

    def test_stale_one_past_boundary(self):
        out = freshness.compute({"last_verified_at": "2026-01-15"}, today=TODAY)  # 181 days
        self.assertEqual(out["freshness_age_days"], 181)
        self.assertEqual(out["freshness_status"], "stale")
        self.assertIn("staleness threshold", out["freshness_reason"])

    def test_stale_reason_wording(self):
        out = freshness.compute({"last_verified_at": "2025-12-13"}, today=TODAY)  # 214 days
        self.assertEqual(out["freshness_status"], "stale")
        self.assertIn("Last verified 214 days ago.", out["freshness_reason"])

    def test_future_reference_date_clamped_to_zero(self):
        out = freshness.compute({"last_verified_at": "2026-08-01"}, today=TODAY)
        self.assertEqual(out["freshness_age_days"], 0)
        self.assertEqual(out["freshness_status"], "fresh")


class TestPriorityOrder(unittest.TestCase):
    def test_last_verified_wins_over_everything(self):
        out = freshness.compute({
            "last_verified_at": "2026-07-10", "retrieved_at": "2020-01-01",
            "publication_date": "2020-01-01", "created_at": "2020-01-01",
        }, today=TODAY)
        self.assertEqual(out["freshness_reference_date"], "2026-07-10")
        self.assertEqual(out["freshness_status"], "fresh")

    def test_retrieved_next(self):
        out = freshness.compute({"retrieved_at": "2026-07-01",
                                 "publication_date": "2020-01-01"}, today=TODAY)
        self.assertEqual(out["freshness_reference_date"], "2026-07-01")
        self.assertIn("Retrieved 14 days ago.", out["freshness_reason"])
        self.assertIn("No verification date is available.", out["freshness_reason"])

    def test_publication_then_date_of_evidence_then_created(self):
        out = freshness.compute({"publication_date": "2025-12-07"}, today=TODAY)  # 220 days
        self.assertEqual(out["freshness_status"], "stale")
        self.assertIn("Published 220 days ago.", out["freshness_reason"])
        out = freshness.compute({"date_of_evidence": "2026-07-14"}, today=TODAY)
        self.assertIn("Evidence dated 1 day ago.", out["freshness_reason"])
        out = freshness.compute({"created_at": "2026-07-13"}, today=TODAY)
        self.assertIn("Record created 2 days ago.", out["freshness_reason"])

    def test_unparseable_dates_fall_through(self):
        out = freshness.compute({
            "last_verified_at": "unknown", "retrieved_at": None,
            "publication_date": "Undated (2025-2026 search index)",
            "created_at": "2026-07-10",
        }, today=TODAY)
        self.assertEqual(out["freshness_reference_date"], "2026-07-10")


class TestUnknown(unittest.TestCase):
    def test_no_dates_is_unknown_not_invented(self):
        for dates in ({}, None, {"last_verified_at": None}, {"created_at": "not a date"}):
            out = freshness.compute(dates, today=TODAY)
            self.assertEqual(out["freshness_status"], "unknown")
            self.assertIsNone(out["freshness_reference_date"])
            self.assertIsNone(out["freshness_age_days"])
            self.assertIn("No verification, retrieval, publication, or creation date",
                          out["freshness_reason"])


class TestDateParsing(unittest.TestCase):
    def test_iso_timestamp_prefix_accepted(self):
        self.assertEqual(str(freshness.parse_iso_date("2026-07-10T12:00:00Z")), "2026-07-10")

    def test_invalid_calendar_date_rejected(self):
        self.assertIsNone(freshness.parse_iso_date("2026-13-45"))

    def test_non_string_rejected(self):
        self.assertIsNone(freshness.parse_iso_date(20260710))


if __name__ == "__main__":
    unittest.main()
