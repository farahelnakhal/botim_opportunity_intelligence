"""CSV preview/commit tests: writes-nothing preview, token binding, row
errors, duplicate flagging, size limit, transactional commit."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import RESEARCHER, make_active_campaign_with_approved_guide, make_dbs, make_participant

from app import csv_import
from app.models import MAX_CSV_BYTES, ValidationError


class CsvImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn, self.identity_conn, self.config = make_dbs(self.tmp.name)
        self.clock_n = 0
        self.camp, self.guide = make_active_campaign_with_approved_guide(
            self.conn, self.config, self._clock)
        self.participant = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                            self.camp["campaign_id"])
        self.q1 = self.guide["questions"][0]["question_id"]

    def _clock(self):
        self.clock_n += 1
        return f"2026-01-01T00:00:{self.clock_n:02d}Z"

    def _csv(self, answer="A synthetic supplier-payment complaint."):
        return f"participant_ref,question_id,answer\n{self.participant['participant_id']},{self.q1},{answer}\n"

    def test_preview_writes_nothing_to_response_tables(self):
        csv_import.preview(self.conn, self.config, RESEARCHER,
                           {"campaign_id": self.camp["campaign_id"], "guide_id": self.guide["guide_id"],
                            "csv_text": self._csv()}, self._clock())
        count = self.conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
        self.assertEqual(count, 0)
        count_answers = self.conn.execute("SELECT COUNT(*) FROM raw_answers").fetchone()[0]
        self.assertEqual(count_answers, 0)

    def test_preview_returns_row_level_summary(self):
        result = csv_import.preview(self.conn, self.config, RESEARCHER,
                                    {"campaign_id": self.camp["campaign_id"], "guide_id": self.guide["guide_id"],
                                     "csv_text": self._csv()}, self._clock())
        self.assertEqual(result["summary"]["valid_count"], 1)
        self.assertEqual(result["rows"][0]["status"], "valid")

    def test_preview_flags_row_errors_unknown_participant(self):
        csv_text = f"participant_ref,question_id,answer\nMVP-BOGUS,{self.q1},some answer\n"
        result = csv_import.preview(self.conn, self.config, RESEARCHER,
                                    {"campaign_id": self.camp["campaign_id"], "guide_id": self.guide["guide_id"],
                                     "csv_text": csv_text}, self._clock())
        self.assertEqual(result["summary"]["error_count"], 1)
        self.assertIn("unknown participant_ref", result["rows"][0]["errors"][0])

    def test_preview_flags_unknown_question(self):
        csv_text = f"participant_ref,question_id,answer\n{self.participant['participant_id']},MVG-BOGUS-Q9,some answer\n"
        result = csv_import.preview(self.conn, self.config, RESEARCHER,
                                    {"campaign_id": self.camp["campaign_id"], "guide_id": self.guide["guide_id"],
                                     "csv_text": csv_text}, self._clock())
        self.assertEqual(result["summary"]["error_count"], 1)

    def test_csv_size_limit_enforced(self):
        huge = "participant_ref,question_id,answer\n" + ("x" * (MAX_CSV_BYTES + 10))
        with self.assertRaises(ValidationError):
            csv_import.preview(self.conn, self.config, RESEARCHER,
                               {"campaign_id": self.camp["campaign_id"], "guide_id": self.guide["guide_id"],
                                "csv_text": huge}, self._clock())

    def test_commit_requires_preview_token(self):
        with self.assertRaises(csv_import.CsvTokenError):
            csv_import.commit(self.conn, self.config, RESEARCHER,
                              {"campaign_id": self.camp["campaign_id"], "guide_id": self.guide["guide_id"],
                               "csv_text": self._csv(), "preview_token": "MVX-doesnotexist"}, self._clock())

    def test_commit_rejects_changed_file(self):
        preview_result = csv_import.preview(self.conn, self.config, RESEARCHER,
                                            {"campaign_id": self.camp["campaign_id"],
                                             "guide_id": self.guide["guide_id"], "csv_text": self._csv()},
                                            self._clock())
        with self.assertRaises(csv_import.CsvTokenError):
            csv_import.commit(self.conn, self.config, RESEARCHER, {
                "campaign_id": self.camp["campaign_id"], "guide_id": self.guide["guide_id"],
                "csv_text": self._csv("a totally different answer text"),
                "preview_token": preview_result["preview_token"]}, self._clock())

    def test_commit_rejects_expired_token(self):
        short_ttl_config = type(self.config)(env={"MV_TOKENS": "a:t:admin", "MV_CSV_PREVIEW_TTL_S": "0"})
        short_ttl_config.transcript_dir = self.config.transcript_dir
        preview_result = csv_import.preview(self.conn, short_ttl_config, RESEARCHER,
                                            {"campaign_id": self.camp["campaign_id"],
                                             "guide_id": self.guide["guide_id"], "csv_text": self._csv()},
                                            self._clock())
        with self.assertRaises(csv_import.CsvTokenError):
            csv_import.commit(self.conn, short_ttl_config, RESEARCHER, {
                "campaign_id": self.camp["campaign_id"], "guide_id": self.guide["guide_id"],
                "csv_text": self._csv(), "preview_token": preview_result["preview_token"]}, self._clock())

    def test_commit_happy_path_creates_response(self):
        preview_result = csv_import.preview(self.conn, self.config, RESEARCHER,
                                            {"campaign_id": self.camp["campaign_id"],
                                             "guide_id": self.guide["guide_id"], "csv_text": self._csv()},
                                            self._clock())
        result = csv_import.commit(self.conn, self.config, RESEARCHER, {
            "campaign_id": self.camp["campaign_id"], "guide_id": self.guide["guide_id"],
            "csv_text": self._csv(), "preview_token": preview_result["preview_token"]}, self._clock())
        self.assertTrue(result["committed"])
        self.assertEqual(len(result["created_response_ids"]), 1)
        count = self.conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
        self.assertEqual(count, 1)

    def test_commit_is_single_use(self):
        preview_result = csv_import.preview(self.conn, self.config, RESEARCHER,
                                            {"campaign_id": self.camp["campaign_id"],
                                             "guide_id": self.guide["guide_id"], "csv_text": self._csv()},
                                            self._clock())
        body = {"campaign_id": self.camp["campaign_id"], "guide_id": self.guide["guide_id"],
               "csv_text": self._csv(), "preview_token": preview_result["preview_token"]}
        csv_import.commit(self.conn, self.config, RESEARCHER, body, self._clock())
        with self.assertRaises(csv_import.CsvTokenError):
            csv_import.commit(self.conn, self.config, RESEARCHER, body, self._clock())

    def test_commit_flags_duplicate_rows_without_dropping(self):
        preview1 = csv_import.preview(self.conn, self.config, RESEARCHER,
                                      {"campaign_id": self.camp["campaign_id"],
                                       "guide_id": self.guide["guide_id"], "csv_text": self._csv()},
                                      self._clock())
        csv_import.commit(self.conn, self.config, RESEARCHER, {
            "campaign_id": self.camp["campaign_id"], "guide_id": self.guide["guide_id"],
            "csv_text": self._csv(), "preview_token": preview1["preview_token"]}, self._clock())

        preview2 = csv_import.preview(self.conn, self.config, RESEARCHER,
                                      {"campaign_id": self.camp["campaign_id"],
                                       "guide_id": self.guide["guide_id"], "csv_text": self._csv()},
                                      self._clock())
        self.assertEqual(preview2["rows"][0]["status"], "duplicate")
        result = csv_import.commit(self.conn, self.config, RESEARCHER, {
            "campaign_id": self.camp["campaign_id"], "guide_id": self.guide["guide_id"],
            "csv_text": self._csv(), "preview_token": preview2["preview_token"]}, self._clock())
        # duplicates are still committed, not silently dropped
        self.assertEqual(len(result["created_response_ids"]), 1)

    def test_commit_is_transactional_on_row_error(self):
        # mix one valid + one row that will raise validation, verify no partial commit if forced to fail
        csv_text = (f"participant_ref,question_id,answer\n"
                   f"{self.participant['participant_id']},{self.q1},First valid answer here.\n")
        preview_result = csv_import.preview(self.conn, self.config, RESEARCHER,
                                            {"campaign_id": self.camp["campaign_id"],
                                             "guide_id": self.guide["guide_id"], "csv_text": csv_text},
                                            self._clock())
        before_count = self.conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]

        import app.csv_import as csv_import_mod
        original = csv_import_mod.participants.mark_enrolled_if_invited

        def boom(*a, **k):
            raise RuntimeError("simulated failure mid-commit")

        csv_import_mod.participants.mark_enrolled_if_invited = boom
        try:
            with self.assertRaises(RuntimeError):
                csv_import.commit(self.conn, self.config, RESEARCHER, {
                    "campaign_id": self.camp["campaign_id"], "guide_id": self.guide["guide_id"],
                    "csv_text": csv_text, "preview_token": preview_result["preview_token"]}, self._clock())
        finally:
            csv_import_mod.participants.mark_enrolled_if_invited = original

        after_count = self.conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
        self.assertEqual(before_count, after_count)  # rolled back, no partial write

    def test_no_formula_execution_cell_sanitized(self):
        csv_text = (f"participant_ref,question_id,answer\n"
                   f"{self.participant['participant_id']},{self.q1},=SUM(A1:A9)\n")
        result = csv_import.preview(self.conn, self.config, RESEARCHER,
                                    {"campaign_id": self.camp["campaign_id"], "guide_id": self.guide["guide_id"],
                                     "csv_text": csv_text}, self._clock())
        self.assertTrue(result["rows"][0]["answer"].startswith("'="))

    def test_utf8_only_content(self):
        with self.assertRaises(ValidationError):
            csv_import.preview(self.conn, self.config, RESEARCHER,
                               {"campaign_id": self.camp["campaign_id"], "guide_id": self.guide["guide_id"],
                                "csv_text": 12345}, self._clock())

    def test_required_columns_enforced(self):
        csv_text = "participant_ref,answer\nP1,hello\n"
        with self.assertRaises(ValidationError):
            csv_import.preview(self.conn, self.config, RESEARCHER,
                               {"campaign_id": self.camp["campaign_id"], "guide_id": self.guide["guide_id"],
                                "csv_text": csv_text}, self._clock())


if __name__ == "__main__":
    unittest.main(verbosity=2)
