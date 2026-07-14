"""Manual response ingestion tests: validation, consent gating, duplicate
detection, consent snapshot, redaction wiring, no-network guarantee."""

import socket
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (RESEARCHER, VIEWER, make_active_campaign_with_approved_guide,
                      make_dbs, make_participant)

from app import campaigns, responses, suppression
from app.auth import AuthError
from app.db import DbError
from app.models import ValidationError


class ResponseIngestionTests(unittest.TestCase):
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
        self.q2 = self.guide["questions"][1]["question_id"]

    def _clock(self):
        self.clock_n += 1
        return f"2026-01-01T00:00:{self.clock_n:02d}Z"

    def _create(self, **overrides):
        data = {
            "campaign_id": self.camp["campaign_id"], "participant_id": self.participant["participant_id"],
            "guide_id": self.guide["guide_id"], "method": "interview",
            "answers": [{"question_id": self.q1, "answer": "We lose sales every week to late payments."}],
        }
        data.update(overrides)
        return responses.create(self.conn, self.config, RESEARCHER, data, self._clock())

    def test_manual_ingestion_happy_path(self):
        resp = self._create()
        self.assertTrue(resp["response_id"].startswith("MVR-"))
        self.assertEqual(resp["duplicate_status"], "unique")
        self.assertEqual(resp["guide_version"], 1)
        self.assertEqual(len(resp["answers"]), 1)

    def test_viewer_cannot_create_response(self):
        with self.assertRaises(AuthError):
            responses.create(self.conn, self.config, VIEWER, {
                "campaign_id": self.camp["campaign_id"], "participant_id": self.participant["participant_id"],
                "guide_id": self.guide["guide_id"], "method": "interview",
                "answers": [{"question_id": self.q1, "answer": "x"}]}, self._clock())

    def test_campaign_must_be_active(self):
        campaigns.transition(self.conn, RESEARCHER, self.camp["campaign_id"], "paused", self._clock())
        with self.assertRaises(ValidationError):
            self._create()

    def test_participant_must_belong_to_campaign(self):
        other_camp, other_guide = make_active_campaign_with_approved_guide(self.conn, self.config, self._clock)
        with self.assertRaises(ValidationError):
            responses.create(self.conn, self.config, RESEARCHER, {
                "campaign_id": other_camp["campaign_id"], "participant_id": self.participant["participant_id"],
                "guide_id": other_guide["guide_id"], "method": "interview",
                "answers": [{"question_id": other_guide["questions"][0]["question_id"], "answer": "x"}]},
                self._clock())

    def test_question_must_belong_to_guide_version(self):
        with self.assertRaises(ValidationError):
            self._create(answers=[{"question_id": "MVG-BOGUS-Q9", "answer": "x"}])

    def test_guide_must_be_approved(self):
        draft_guide = None
        from app import guides
        draft_guide = guides.create(self.conn, RESEARCHER, self.camp["campaign_id"],
                                    [{"text": "New Q?", "purpose": "trust"}], self._clock())
        with self.assertRaises(ValidationError):
            self._create(guide_id=draft_guide["guide_id"],
                         answers=[{"question_id": draft_guide["questions"][0]["question_id"], "answer": "x"}])

    def test_consent_must_be_valid(self):
        suppression.suppress_participant(self.conn, RESEARCHER, self.participant["participant_id"],
                                         "withdrawn", self._clock())
        with self.assertRaises(ValidationError):
            self._create()

    def test_response_stores_consent_snapshot(self):
        resp = self._create()
        self.assertEqual(resp["consent_snapshot"]["consent_status"], "granted")
        self.assertTrue(resp["consent_snapshot"]["ai_processing_permission"])

    def test_duplicate_response_detected_not_dropped(self):
        self._create()
        dup = self._create()
        self.assertEqual(dup["duplicate_status"], "duplicate")
        # still created — not silently dropped
        self.assertNotEqual(dup["response_id"], "")

    def test_duplicate_normalization_ignores_case_and_whitespace(self):
        self._create(answers=[{"question_id": self.q1, "answer": "We lose sales every week to late payments."}])
        dup = self._create(answers=[{"question_id": self.q1,
                                     "answer": "  WE LOSE   sales every week to late payments.  "}])
        self.assertEqual(dup["duplicate_status"], "duplicate")

    def test_redaction_runs_and_flags_categories(self):
        resp = self._create(answers=[{"question_id": self.q1, "answer": "Call me at merchant@example.com"}])
        self.assertEqual(resp["answers"][0]["redaction_status"], "complete")
        self.assertIn("email", resp["answers"][0]["sensitive_data_flags"])

    def test_processing_status_eligible_when_all_gates_pass(self):
        resp = self._create()
        self.assertEqual(resp["processing_status"], "eligible_for_ai_processing")

    def test_processing_status_received_when_ai_permission_missing(self):
        participant = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                       self.camp["campaign_id"], ai_processing_permission=False)
        resp = responses.create(self.conn, self.config, RESEARCHER, {
            "campaign_id": self.camp["campaign_id"], "participant_id": participant["participant_id"],
            "guide_id": self.guide["guide_id"], "method": "interview",
            "answers": [{"question_id": self.q1, "answer": "plain text answer"}]}, self._clock())
        self.assertEqual(resp["processing_status"], "received")

    def test_participant_enrolled_after_first_response(self):
        self.assertEqual(self.participant["workflow_status"], "invited")
        self._create()
        from app import participants
        refreshed = participants.get(self.conn, self.participant["participant_id"])
        self.assertEqual(refreshed["workflow_status"], "enrolled")

    def test_no_response_becomes_evidence(self):
        resp = self._create()
        self.assertNotIn("evidence_id", resp)
        self.assertNotIn("finding_id", resp)

    def test_response_create_is_audited(self):
        from app import audit
        resp = self._create()
        events = audit.list_for_object(self.conn, "response", resp["response_id"])
        self.assertEqual([e["action"] for e in events], ["create"])

    def test_audit_event_never_contains_raw_answer_text(self):
        from app import audit
        secret_text = "my confidential supplier rate is 12.5 percent, please redact-sensitive-marker"
        resp = self._create(answers=[{"question_id": self.q1, "answer": secret_text}])
        events = audit.list_for_object(self.conn, "response", resp["response_id"])
        self.assertNotIn(secret_text, str(events))

    def test_get_nonexistent_response_raises(self):
        with self.assertRaises(DbError):
            responses.get(self.conn, "MVR-DOES-NOT-EXIST")

    def test_no_network_call_during_ingestion(self):
        original_connect = socket.socket.connect

        def guard(self, *a, **k):
            raise AssertionError("network connection attempted during response ingestion")

        socket.socket.connect = guard
        try:
            self._create()
        finally:
            socket.socket.connect = original_connect


if __name__ == "__main__":
    unittest.main(verbosity=2)
