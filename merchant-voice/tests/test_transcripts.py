"""Transcript ingestion tests: extension/content-type/size/UTF-8 validation,
server-generated filenames, non-web-served storage, viewer boundary is
tested at the API layer (test_phase2_api.py)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import RESEARCHER, make_active_campaign_with_approved_guide, make_dbs, make_participant

from app import responses, transcripts
from app.db import DbError
from app.models import MAX_TRANSCRIPT_BYTES, ValidationError


class TranscriptIngestionTests(unittest.TestCase):
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
            "answers": [{"question_id": q1, "answer": "a plain synthetic answer"}]}, self._clock())

    def _clock(self):
        self.clock_n += 1
        return f"2026-01-01T00:00:{self.clock_n:02d}Z"

    def test_ingest_happy_path(self):
        meta = transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
            "extension": "txt", "content_type": "text/plain", "language": "en",
            "transcript_text": "Interviewer: hi\nMerchant: hello"}, self._clock())
        self.assertEqual(meta["extension"], "txt")
        self.assertEqual(meta["storage_status"], "stored")

    def test_rejects_disallowed_extension(self):
        with self.assertRaises(ValidationError):
            transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
                "extension": "pdf", "transcript_text": "some text"}, self._clock())

    def test_rejects_mismatched_content_type(self):
        with self.assertRaises(ValidationError):
            transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
                "extension": "txt", "content_type": "application/pdf",
                "transcript_text": "some text"}, self._clock())

    def test_rejects_oversized_transcript(self):
        huge = "x" * (MAX_TRANSCRIPT_BYTES + 10)
        with self.assertRaises(ValidationError):
            transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
                "extension": "txt", "transcript_text": huge}, self._clock())

    def test_rejects_non_string_transcript_text(self):
        with self.assertRaises(ValidationError):
            transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
                "extension": "txt", "transcript_text": 12345}, self._clock())

    def test_rejects_binary_control_bytes(self):
        with self.assertRaises(ValidationError):
            transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
                "extension": "txt", "transcript_text": "hello\x00world"}, self._clock())

    def test_rejects_unsupported_language(self):
        with self.assertRaises(ValidationError):
            transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
                "extension": "txt", "language": "klingon", "transcript_text": "hi"}, self._clock())

    def test_storage_filename_is_server_generated_from_response_id(self):
        transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
            "extension": "vtt", "transcript_text": "WEBVTT\n\nhello"}, self._clock())
        expected_path = self.config.transcript_dir / f"{self.response['response_id']}.vtt"
        self.assertTrue(expected_path.exists())

    def test_original_filename_never_used(self):
        # the ingest payload has no "filename" field at all — this is by
        # construction: the API never accepts or reads a client filename.
        meta = transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
            "extension": "md", "transcript_text": "# hi", "filename": "totally-ignored.md"}, self._clock())
        self.assertTrue((self.config.transcript_dir / f"{self.response['response_id']}.md").exists())
        self.assertFalse((self.config.transcript_dir / "totally-ignored.md").exists())

    def test_transcript_content_never_in_metadata_response(self):
        meta = transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
            "extension": "txt", "transcript_text": "super secret merchant statement"}, self._clock())
        self.assertNotIn("transcript_text", meta)
        self.assertNotIn("super secret", str(meta))

    def test_get_metadata_for_missing_transcript_raises(self):
        with self.assertRaises(DbError):
            transcripts.get_metadata(self.conn, "MVR-DOES-NOT-EXIST")

    def test_response_transcript_status_updated(self):
        transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
            "extension": "txt", "transcript_text": "hello"}, self._clock())
        refreshed = responses.get(self.conn, self.response["response_id"])
        self.assertEqual(refreshed["transcript_status"], "stored")

    def test_speaker_map_researcher_editable_via_re_ingest(self):
        transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
            "extension": "txt", "transcript_text": "hello", "speaker_map": {"Speaker 1": "interviewer"}},
            self._clock())
        meta = transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
            "extension": "txt", "transcript_text": "hello",
            "speaker_map": {"Speaker 1": "interviewer", "Speaker 2": "merchant"}}, self._clock())
        self.assertEqual(meta["speaker_map"]["Speaker 2"], "merchant")

    def test_ingestion_failure_leaves_no_partial_state(self):
        import app.transcripts as transcripts_mod

        def boom(*a, **k):
            raise RuntimeError("simulated db failure")

        original_record = transcripts_mod.audit.record
        transcripts_mod.audit.record = boom
        try:
            with self.assertRaises(RuntimeError):
                transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
                    "extension": "txt", "transcript_text": "hello"}, self._clock())
        finally:
            transcripts_mod.audit.record = original_record

        # the DB write is rolled back and the just-written file is removed —
        # no orphan file, no dangling metadata row.
        self.assertFalse((self.config.transcript_dir / f"{self.response['response_id']}.txt").exists())
        with self.assertRaises(DbError):
            transcripts.get_metadata(self.conn, self.response["response_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
