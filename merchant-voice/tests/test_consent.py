"""Deterministic consent/privacy gate tests — the gate Phase 3 extraction
will eventually have to pass through (no provider call exists yet)."""

import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND.parent))

from app import consent  # noqa: E402

BASE_PARTICIPANT = {
    "consent_status": "granted", "ai_processing_permission": True, "quote_permission": True,
    "suppression_status": "none", "retention_expires_at": None,
}


class ConsentGateTests(unittest.TestCase):
    def test_consent_valid_when_granted_and_not_suppressed(self):
        self.assertTrue(consent.consent_is_valid(BASE_PARTICIPANT, "2026-01-01T00:00:00Z"))

    def test_consent_invalid_when_withdrawn(self):
        p = {**BASE_PARTICIPANT, "consent_status": "withdrawn"}
        self.assertFalse(consent.consent_is_valid(p, "2026-01-01T00:00:00Z"))

    def test_consent_invalid_when_retention_expired(self):
        p = {**BASE_PARTICIPANT, "retention_expires_at": "2025-01-01T00:00:00Z"}
        self.assertFalse(consent.consent_is_valid(p, "2026-01-01T00:00:00Z"))

    def test_consent_valid_when_retention_in_future(self):
        p = {**BASE_PARTICIPANT, "retention_expires_at": "2027-01-01T00:00:00Z"}
        self.assertTrue(consent.consent_is_valid(p, "2026-01-01T00:00:00Z"))

    def test_consent_invalid_when_suppressed(self):
        p = {**BASE_PARTICIPANT, "suppression_status": "suppressed"}
        self.assertFalse(consent.consent_is_valid(p, "2026-01-01T00:00:00Z"))

    def test_quote_allowed_requires_both_permission_and_flag(self):
        answer = {"is_direct_quote": True, "content_purged": False}
        self.assertTrue(consent.quote_allowed(BASE_PARTICIPANT, answer))
        self.assertFalse(consent.quote_allowed(BASE_PARTICIPANT, {**answer, "is_direct_quote": False}))
        no_quote_participant = {**BASE_PARTICIPANT, "quote_permission": False}
        self.assertFalse(consent.quote_allowed(no_quote_participant, answer))

    def test_quote_not_allowed_when_purged(self):
        answer = {"is_direct_quote": True, "content_purged": True}
        self.assertFalse(consent.quote_allowed(BASE_PARTICIPANT, answer))

    def test_ai_processing_requires_all_gates(self):
        response = {"processing_status": "received"}
        answers = [{"redaction_status": "complete", "content_purged": False}]
        self.assertTrue(consent.ai_processing_allowed(BASE_PARTICIPANT, response, answers, "2026-01-01T00:00:00Z"))

    def test_ai_processing_blocked_without_permission(self):
        p = {**BASE_PARTICIPANT, "ai_processing_permission": False}
        response = {"processing_status": "received"}
        answers = [{"redaction_status": "complete", "content_purged": False}]
        self.assertFalse(consent.ai_processing_allowed(p, response, answers, "2026-01-01T00:00:00Z"))

    def test_ai_processing_blocked_by_incomplete_redaction(self):
        response = {"processing_status": "received"}
        answers = [{"redaction_status": "pending", "content_purged": False}]
        self.assertFalse(consent.ai_processing_allowed(BASE_PARTICIPANT, response, answers, "2026-01-01T00:00:00Z"))

    def test_ai_processing_blocked_by_failed_redaction(self):
        response = {"processing_status": "received"}
        answers = [{"redaction_status": "failed", "content_purged": False}]
        self.assertFalse(consent.ai_processing_allowed(BASE_PARTICIPANT, response, answers, "2026-01-01T00:00:00Z"))

    def test_ai_processing_blocked_when_response_suppressed(self):
        response = {"processing_status": "suppressed"}
        answers = [{"redaction_status": "complete", "content_purged": False}]
        self.assertFalse(consent.ai_processing_allowed(BASE_PARTICIPANT, response, answers, "2026-01-01T00:00:00Z"))

    def test_ai_processing_blocked_with_no_answers(self):
        response = {"processing_status": "received"}
        self.assertFalse(consent.ai_processing_allowed(BASE_PARTICIPANT, response, [], "2026-01-01T00:00:00Z"))

    def test_compute_processing_status_blocked_on_any_failed_answer(self):
        answers = [{"redaction_status": "complete"}, {"redaction_status": "failed"}]
        status = consent.compute_processing_status(BASE_PARTICIPANT, {}, answers, "2026-01-01T00:00:00Z")
        self.assertEqual(status, "blocked_for_ai")

    def test_compute_processing_status_eligible_when_all_gates_pass(self):
        answers = [{"redaction_status": "complete"}]
        status = consent.compute_processing_status(BASE_PARTICIPANT, {}, answers, "2026-01-01T00:00:00Z")
        self.assertEqual(status, "eligible_for_ai_processing")

    def test_compute_processing_status_received_when_permission_missing(self):
        p = {**BASE_PARTICIPANT, "ai_processing_permission": False}
        answers = [{"redaction_status": "complete"}]
        status = consent.compute_processing_status(p, {}, answers, "2026-01-01T00:00:00Z")
        self.assertEqual(status, "received")


if __name__ == "__main__":
    unittest.main(verbosity=2)
