"""Participant service tests: creation, validation, consent narrowing,
identity separation, viewer access boundary is enforced at the API layer
(see test_phase2_api.py) — these are the service-layer tests."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (ADMIN, RESEARCHER, REVIEWER, VALID_IDENTITY, VIEWER,
                      make_active_campaign_with_approved_guide, make_dbs, make_participant)

from app import identity, participants
from app.auth import AuthError
from app.db import DbError
from app.models import ValidationError


class ParticipantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn, self.identity_conn, self.config = make_dbs(self.tmp.name)
        self.clock_n = 0
        self.camp, self.guide = make_active_campaign_with_approved_guide(
            self.conn, self.config, self._clock)

    def _clock(self):
        self.clock_n += 1
        return f"2026-01-01T00:00:{self.clock_n:02d}Z"

    def test_create_participant_with_new_identity(self):
        row = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                               self.camp["campaign_id"])
        self.assertTrue(row["participant_id"].startswith("MVP-"))
        self.assertEqual(row["workflow_status"], "invited")
        self.assertEqual(row["suppression_status"], "none")

    def test_create_participant_with_existing_identity(self):
        idrow = identity.create(self.identity_conn, self.config, RESEARCHER, dict(VALID_IDENTITY), self._clock())
        row = participants.create(self.conn, self.identity_conn, self.config, RESEARCHER, {
            "campaign_id": self.camp["campaign_id"], "merchant_identity_id": idrow["merchant_identity_id"],
            "consent_status": "granted", "permitted_use": "internal_research_only",
            "quote_permission": True, "ai_processing_permission": True,
            "data_classification": "synthetic"}, self._clock())
        self.assertEqual(row["merchant_identity_id"], idrow["merchant_identity_id"])

    def test_viewer_cannot_create_participant(self):
        with self.assertRaises(AuthError):
            participants.create(self.conn, self.identity_conn, self.config, VIEWER, {
                "campaign_id": self.camp["campaign_id"], "merchant_identity_id": "MID-x"}, self._clock())

    def test_missing_campaign_id_rejected(self):
        idrow = identity.create(self.identity_conn, self.config, RESEARCHER, dict(VALID_IDENTITY), self._clock())
        with self.assertRaises(ValidationError):
            participants.create(self.conn, self.identity_conn, self.config, RESEARCHER, {
                "merchant_identity_id": idrow["merchant_identity_id"],
                "permitted_use": "internal_research_only"}, self._clock())

    def test_unknown_campaign_rejected(self):
        idrow = identity.create(self.identity_conn, self.config, RESEARCHER, dict(VALID_IDENTITY), self._clock())
        with self.assertRaises(DbError):
            participants.create(self.conn, self.identity_conn, self.config, RESEARCHER, {
                "campaign_id": "MVC-DOES-NOT-EXIST", "merchant_identity_id": idrow["merchant_identity_id"],
                "permitted_use": "internal_research_only"}, self._clock())

    def test_participant_cannot_widen_ai_processing_permission_beyond_identity(self):
        idrow = identity.create(self.identity_conn, self.config, RESEARCHER, {
            **VALID_IDENTITY, "ai_processing_permission": False}, self._clock())
        with self.assertRaises(ValidationError):
            participants.create(self.conn, self.identity_conn, self.config, RESEARCHER, {
                "campaign_id": self.camp["campaign_id"], "merchant_identity_id": idrow["merchant_identity_id"],
                "consent_status": "granted", "permitted_use": "internal_research_only",
                "ai_processing_permission": True, "data_classification": "synthetic"}, self._clock())

    def test_participant_cannot_widen_quote_permission_beyond_identity(self):
        idrow = identity.create(self.identity_conn, self.config, RESEARCHER, {
            **VALID_IDENTITY, "quote_permission": False}, self._clock())
        with self.assertRaises(ValidationError):
            participants.create(self.conn, self.identity_conn, self.config, RESEARCHER, {
                "campaign_id": self.camp["campaign_id"], "merchant_identity_id": idrow["merchant_identity_id"],
                "consent_status": "granted", "permitted_use": "internal_research_only",
                "quote_permission": True, "data_classification": "synthetic"}, self._clock())

    def test_participant_cannot_be_granted_if_identity_not_granted(self):
        idrow = identity.create(self.identity_conn, self.config, RESEARCHER, {
            **VALID_IDENTITY, "consent_status": "pending"}, self._clock())
        with self.assertRaises(ValidationError):
            participants.create(self.conn, self.identity_conn, self.config, RESEARCHER, {
                "campaign_id": self.camp["campaign_id"], "merchant_identity_id": idrow["merchant_identity_id"],
                "consent_status": "granted", "permitted_use": "internal_research_only",
                "data_classification": "synthetic"}, self._clock())

    def test_participant_may_narrow_below_identity_grant(self):
        idrow = identity.create(self.identity_conn, self.config, RESEARCHER, dict(VALID_IDENTITY), self._clock())
        row = participants.create(self.conn, self.identity_conn, self.config, RESEARCHER, {
            "campaign_id": self.camp["campaign_id"], "merchant_identity_id": idrow["merchant_identity_id"],
            "consent_status": "granted", "permitted_use": "internal_research_only",
            "quote_permission": False, "ai_processing_permission": False,
            "data_classification": "synthetic"}, self._clock())
        self.assertFalse(row["quote_permission"])
        self.assertFalse(row["ai_processing_permission"])

    def test_participant_does_not_expose_identity_fields(self):
        row = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                               self.camp["campaign_id"])
        self.assertNotIn("protected_external_reference", row)

    def test_list_for_campaign_excludes_suppressed_by_default(self):
        row = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                               self.camp["campaign_id"])
        from app import suppression
        suppression.suppress_participant(self.conn, RESEARCHER, row["participant_id"], "withdrawn", self._clock())
        visible = participants.list_for_campaign(self.conn, self.camp["campaign_id"])
        self.assertEqual(visible, [])
        all_rows = participants.list_for_campaign(self.conn, self.camp["campaign_id"], include_suppressed=True)
        self.assertEqual(len(all_rows), 1)

    def test_update_draft_fields(self):
        row = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                               self.camp["campaign_id"])
        updated = participants.update(self.conn, self.identity_conn, self.config, RESEARCHER,
                                      row["participant_id"], {"industry": "logistics"}, self._clock())
        self.assertEqual(updated["industry"], "logistics")

    def test_cannot_edit_suppressed_participant(self):
        row = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                               self.camp["campaign_id"])
        from app import suppression
        suppression.suppress_participant(self.conn, RESEARCHER, row["participant_id"], "withdrawn", self._clock())
        with self.assertRaises(ValidationError):
            participants.update(self.conn, self.identity_conn, self.config, RESEARCHER,
                                row["participant_id"], {"industry": "logistics"}, self._clock())

    def test_participant_create_is_audited(self):
        from app import audit
        row = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                               self.camp["campaign_id"])
        events = audit.list_for_object(self.conn, "participant", row["participant_id"])
        self.assertEqual([e["action"] for e in events], ["create"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
