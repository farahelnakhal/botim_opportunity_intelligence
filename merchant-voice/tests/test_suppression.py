"""Suppression routine tests: withdrawal, retention expiry, deletion
request, and the recoverable transcript-deletion workflow (success,
failure, pending-remains-inaccessible, retry-success)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (ADMIN, RESEARCHER, make_active_campaign_with_approved_guide, make_dbs,
                      make_participant)

from app import participants, responses, suppression, transcripts
from app.db import DbError


class SuppressionTests(unittest.TestCase):
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
        self.response = responses.create(self.conn, self.config, RESEARCHER, {
            "campaign_id": self.camp["campaign_id"], "participant_id": self.participant["participant_id"],
            "guide_id": self.guide["guide_id"], "method": "interview",
            "answers": [{"question_id": self.q1, "answer": "a synthetic pain point"}]}, self._clock())

    def _clock(self):
        self.clock_n += 1
        return f"2026-01-01T00:00:{self.clock_n:02d}Z"

    def test_withdrawal_suppresses_content_without_purging(self):
        suppression.suppress_participant(self.conn, RESEARCHER, self.participant["participant_id"],
                                         "withdrawn", self._clock(), transcript_dir=self.config.transcript_dir)
        p = participants.get(self.conn, self.participant["participant_id"])
        self.assertEqual(p["suppression_status"], "suppressed")
        self.assertEqual(p["consent_status"], "withdrawn")
        self.assertFalse(p["quote_permission"])
        resp = responses.get(self.conn, self.response["response_id"])
        self.assertEqual(resp["processing_status"], "suppressed")
        self.assertFalse(resp["answers"][0]["content_visible"])
        self.assertIsNone(resp["answers"][0]["original_answer"])
        # withdrawal does NOT purge the underlying storage
        self.assertFalse(resp["answers"][0]["content_purged"])

    def test_retention_expiry_purges_content(self):
        suppression.suppress_participant(self.conn, RESEARCHER, self.participant["participant_id"],
                                         "retention_expired", self._clock(), transcript_dir=self.config.transcript_dir)
        resp = responses.get(self.conn, self.response["response_id"])
        self.assertTrue(resp["answers"][0]["content_purged"])
        self.assertIsNone(resp["answers"][0]["original_answer"])

    def test_deletion_request_purges_content(self):
        suppression.suppress_participant(self.conn, RESEARCHER, self.participant["participant_id"],
                                         "deletion_request", self._clock(), transcript_dir=self.config.transcript_dir)
        resp = responses.get(self.conn, self.response["response_id"])
        self.assertTrue(resp["answers"][0]["content_purged"])
        p = participants.get(self.conn, self.participant["participant_id"])
        self.assertEqual(p["suppression_cause"], "deletion_request")

    def test_expire_retention_maintenance_sweep(self):
        # simulate an already-expired retention window on the identity/participant
        from app import identity as identity_service
        participants.update(self.conn, self.identity_conn, self.config, RESEARCHER,
                            self.participant["participant_id"],
                            {"retention_expires_at": "2020-01-01T00:00:00Z"}, self._clock())
        result = suppression.expire_retention(self.conn, ADMIN, self.config.transcript_dir, self._clock())
        self.assertEqual(result["expired_count"], 1)
        p = participants.get(self.conn, self.participant["participant_id"])
        self.assertEqual(p["suppression_status"], "suppressed")
        self.assertEqual(p["suppression_cause"], "retention_expired")

    def test_expire_retention_ignores_future_dates(self):
        participants.update(self.conn, self.identity_conn, self.config, RESEARCHER,
                            self.participant["participant_id"],
                            {"retention_expires_at": "2099-01-01T00:00:00Z"}, self._clock())
        result = suppression.expire_retention(self.conn, ADMIN, self.config.transcript_dir, self._clock())
        self.assertEqual(result["expired_count"], 0)

    def test_suppression_is_audited_without_raw_content(self):
        from app import audit
        suppression.suppress_participant(self.conn, RESEARCHER, self.participant["participant_id"],
                                         "withdrawn", self._clock(), transcript_dir=self.config.transcript_dir)
        events = audit.list_for_object(self.conn, "participant", self.participant["participant_id"])
        suppress_event = next(e for e in events if e["action"] == "suppress")
        self.assertNotIn("a synthetic pain point", str(suppress_event))


class RecoverableTranscriptDeletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn, self.identity_conn, self.config = make_dbs(self.tmp.name)
        self.clock_n = 0
        self.camp, self.guide = make_active_campaign_with_approved_guide(
            self.conn, self.config, self._clock)
        self.participant = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                            self.camp["campaign_id"])
        q1 = self.guide["questions"][0]["question_id"]
        self.response = responses.create(self.conn, self.config, RESEARCHER, {
            "campaign_id": self.camp["campaign_id"], "participant_id": self.participant["participant_id"],
            "guide_id": self.guide["guide_id"], "method": "interview",
            "answers": [{"question_id": q1, "answer": "a synthetic pain point"}]}, self._clock())
        transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
            "extension": "txt", "transcript_text": "synthetic transcript body"}, self._clock())
        self.file_path = self.config.transcript_dir / f"{self.response['response_id']}.txt"

    def _clock(self):
        self.clock_n += 1
        return f"2026-01-01T00:00:{self.clock_n:02d}Z"

    def test_successful_deletion_removes_file_and_marks_deleted(self):
        self.assertTrue(self.file_path.exists())
        result = suppression.suppress_participant(self.conn, RESEARCHER, self.participant["participant_id"],
                                                  "deletion_request", self._clock(),
                                                  transcript_dir=self.config.transcript_dir)
        self.assertTrue(result["deletion_results"][self.response["response_id"]])
        self.assertFalse(self.file_path.exists())
        meta = transcripts.get_metadata(self.conn, self.response["response_id"])
        self.assertEqual(meta["storage_status"], "deleted")

    def test_failed_deletion_stays_pending_and_is_recorded_safely(self):
        original_unlink = Path.unlink

        def failing_unlink(self, missing_ok=False):
            raise OSError("simulated filesystem failure")

        Path.unlink = failing_unlink
        try:
            result = suppression.suppress_participant(
                self.conn, RESEARCHER, self.participant["participant_id"], "deletion_request", self._clock(),
                transcript_dir=self.config.transcript_dir)
        finally:
            Path.unlink = original_unlink

        self.assertFalse(result["deletion_results"][self.response["response_id"]])
        meta = transcripts.get_metadata(self.conn, self.response["response_id"])
        self.assertEqual(meta["storage_status"], "deletion_failed")

        from app import audit
        events = audit.list_for_object(self.conn, "transcript", self.response["response_id"])
        for e in events:
            self.assertNotIn("synthetic transcript body", str(e))
            self.assertNotIn(str(self.file_path), str(e))

    def test_pending_transcript_remains_inaccessible_after_failure(self):
        original_unlink = Path.unlink
        Path.unlink = lambda self, missing_ok=False: (_ for _ in ()).throw(OSError("boom"))
        try:
            suppression.suppress_participant(self.conn, RESEARCHER, self.participant["participant_id"],
                                             "deletion_request", self._clock(),
                                             transcript_dir=self.config.transcript_dir)
        finally:
            Path.unlink = original_unlink
        resp = responses.get(self.conn, self.response["response_id"])
        self.assertFalse(resp["answers"][0]["content_visible"])
        self.assertNotIn("stored", [resp["transcript_status"]])  # never reported as available again

    def test_retry_succeeds_after_transient_failure(self):
        original_unlink = Path.unlink
        Path.unlink = lambda self, missing_ok=False: (_ for _ in ()).throw(OSError("boom"))
        try:
            suppression.suppress_participant(self.conn, RESEARCHER, self.participant["participant_id"],
                                             "deletion_request", self._clock(),
                                             transcript_dir=self.config.transcript_dir)
        finally:
            Path.unlink = original_unlink

        meta = transcripts.get_metadata(self.conn, self.response["response_id"])
        self.assertEqual(meta["storage_status"], "deletion_failed")

        retry_result = suppression.retry_pending_transcript_deletions(
            self.conn, RESEARCHER, self.config.transcript_dir, self._clock())
        self.assertEqual(retry_result, {"attempted": 1, "succeeded": 1, "failed": 0})
        meta2 = transcripts.get_metadata(self.conn, self.response["response_id"])
        self.assertEqual(meta2["storage_status"], "deleted")
        self.assertFalse(self.file_path.exists())

    def test_retry_with_nothing_pending_is_a_no_op(self):
        result = suppression.retry_pending_transcript_deletions(
            self.conn, RESEARCHER, self.config.transcript_dir, self._clock())
        self.assertEqual(result, {"attempted": 0, "succeeded": 0, "failed": 0})


if __name__ == "__main__":
    unittest.main(verbosity=2)
