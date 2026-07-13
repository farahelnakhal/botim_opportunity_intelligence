"""Canonical extraction eligibility gate tests. Every scenario here must
fail BEFORE any provider call would ever be made — no network guard is
needed in this file since eligibility.check_eligibility never touches the
provider at all (verified separately in test_extraction.py/test_provider_integration.py)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (RESEARCHER, make_active_campaign_with_approved_guide, make_dbs,
                      make_participant, make_response)

from app import participants, suppression
from app.eligibility import ExtractionError, check_eligibility


class EligibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn, self.identity_conn, self.config = make_dbs(self.tmp.name)
        self.clock_n = 0
        self.camp, self.guide = make_active_campaign_with_approved_guide(
            self.conn, self.config, self._clock,
            campaign_overrides={"linked_opportunities": ["OPP-013"]})
        self.participant = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                            self.camp["campaign_id"])
        self.q1 = self.guide["questions"][0]["question_id"]
        self.response = make_response(self.conn, self.config, self._clock, self.camp, self.guide,
                                      self.participant, [{"question_id": self.q1, "answer": "a synthetic pain point"}])

    def _clock(self):
        self.clock_n += 1
        return f"2026-01-01T00:00:{self.clock_n:02d}Z"

    def test_eligible_response_passes(self):
        response, participant, campaign, eligible_answers = check_eligibility(
            self.conn, self.response["response_id"], self._clock())
        self.assertEqual(response["response_id"], self.response["response_id"])
        self.assertEqual(len(eligible_answers), 1)

    def test_response_not_found(self):
        from app.db import DbError
        with self.assertRaises(DbError):
            check_eligibility(self.conn, "MVR-DOES-NOT-EXIST", self._clock())

    def test_consent_denied_when_suppressed(self):
        suppression.suppress_participant(self.conn, RESEARCHER, self.participant["participant_id"],
                                         "withdrawn", self._clock(), transcript_dir=self.config.transcript_dir)
        with self.assertRaises(ExtractionError) as ctx:
            check_eligibility(self.conn, self.response["response_id"], self._clock())
        self.assertEqual(ctx.exception.code, "consent_denied")

    def test_consent_denied_when_not_granted(self):
        # response ingestion itself requires valid consent, so build one then flip consent after
        r2 = make_response(self.conn, self.config, self._clock, self.camp, self.guide,
                           make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                           self.camp["campaign_id"]),
                           [{"question_id": self.q1, "answer": "another synthetic answer"}])
        participants.update(self.conn, self.identity_conn, self.config, RESEARCHER,
                            r2["participant_id"], {"consent_status": "withdrawn"}, self._clock())
        with self.assertRaises(ExtractionError) as ctx:
            check_eligibility(self.conn, r2["response_id"], self._clock())
        self.assertEqual(ctx.exception.code, "consent_denied")

    def test_ai_processing_denied(self):
        p2 = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                              self.camp["campaign_id"], ai_processing_permission=False)
        r2 = make_response(self.conn, self.config, self._clock, self.camp, self.guide, p2,
                           [{"question_id": self.q1, "answer": "another synthetic answer"}])
        with self.assertRaises(ExtractionError) as ctx:
            check_eligibility(self.conn, r2["response_id"], self._clock())
        self.assertEqual(ctx.exception.code, "ai_processing_denied")

    def test_retention_expired(self):
        participants.update(self.conn, self.identity_conn, self.config, RESEARCHER,
                            self.participant["participant_id"],
                            {"retention_expires_at": "2020-01-01T00:00:00Z"}, self._clock())
        with self.assertRaises(ExtractionError) as ctx:
            check_eligibility(self.conn, self.response["response_id"], self._clock())
        self.assertEqual(ctx.exception.code, "retention_expired")

    def test_redaction_incomplete_blocks(self):
        import app.responses as responses_mod
        original = responses_mod.process_answer
        responses_mod.process_answer = lambda text, known_entities=None: ("failed", [])
        try:
            p2 = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                  self.camp["campaign_id"])
            r2 = make_response(self.conn, self.config, self._clock, self.camp, self.guide, p2,
                               [{"question_id": self.q1, "answer": "another synthetic answer"}])
        finally:
            responses_mod.process_answer = original
        self.assertEqual(r2["processing_status"], "blocked_for_ai")
        with self.assertRaises(ExtractionError) as ctx:
            check_eligibility(self.conn, r2["response_id"], self._clock())
        self.assertEqual(ctx.exception.code, "ai_processing_denied")

    def test_response_purged_after_deletion_request(self):
        suppression.suppress_participant(self.conn, RESEARCHER, self.participant["participant_id"],
                                         "deletion_request", self._clock(), transcript_dir=self.config.transcript_dir)
        with self.assertRaises(ExtractionError) as ctx:
            check_eligibility(self.conn, self.response["response_id"], self._clock())
        # participant suppression is checked first — response_purged would only
        # surface for a purge that occurs independently of suppression, which
        # cannot happen via any current code path; this documents that.
        self.assertEqual(ctx.exception.code, "consent_denied")

    def test_transcript_pending_deletion_blocks(self):
        from app import transcripts
        transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
            "extension": "txt", "transcript_text": "synthetic transcript"}, self._clock())
        self.conn.execute("UPDATE responses SET transcript_status='pending_deletion' WHERE response_id=?",
                          (self.response["response_id"],))
        self.conn.commit()
        with self.assertRaises(ExtractionError) as ctx:
            check_eligibility(self.conn, self.response["response_id"], self._clock())
        self.assertEqual(ctx.exception.code, "transcript_pending_deletion")

    def test_transcript_deletion_failed_also_blocks(self):
        from app import transcripts
        transcripts.ingest(self.conn, self.config, RESEARCHER, self.response["response_id"], {
            "extension": "txt", "transcript_text": "synthetic transcript"}, self._clock())
        self.conn.execute("UPDATE responses SET transcript_status='deletion_failed' WHERE response_id=?",
                          (self.response["response_id"],))
        self.conn.commit()
        with self.assertRaises(ExtractionError) as ctx:
            check_eligibility(self.conn, self.response["response_id"], self._clock())
        self.assertEqual(ctx.exception.code, "transcript_pending_deletion")

    def test_one_canonical_function_used(self):
        # eligibility.check_eligibility is the only gate — verify extraction.py
        # actually calls it rather than re-implementing checks inline.
        import inspect
        from app import extraction
        source = inspect.getsource(extraction.run_extraction)
        self.assertIn("check_eligibility", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
