"""Campaign service tests: creation, validation, lifecycle, roles, audit."""

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from app import audit, campaigns  # noqa: E402
from app.auth import AuthError  # noqa: E402
from app.config import Config  # noqa: E402
from app.db import connect_mv  # noqa: E402
from app.models import ValidationError  # noqa: E402

RESEARCHER = {"role": "researcher", "label": "researcher-1"}
REVIEWER = {"role": "reviewer", "label": "reviewer-1"}
ADMIN = {"role": "admin", "label": "admin-1"}
VIEWER = {"role": "viewer", "label": "viewer-1"}

VALID_INPUT = {
    "title": "MVC-TEST-001 supplier payment pain",
    "objective": "Understand supplier-payment financing pain in UAE importers",
    "method": "interview",
    "research_questions": ["What is your biggest supplier-payment pain?"],
    "target_segments": ["SEG-uae-importers-upfront-pay"],
    "linked_opportunities": ["OPP-013"],
    "linked_assumptions": ["ASM-OPP-013-willingness_to_pay"],
    "data_classification": "synthetic",
}


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn = connect_mv(Path(self.tmp.name) / "mv.db")
        self.config = Config(env={"MV_TOKENS": "a:t:admin", "MV_SYNTHETIC_ONLY": "1"})

    def test_create_campaign_happy_path(self):
        row = campaigns.create(self.conn, self.config, RESEARCHER, dict(VALID_INPUT), "2026-01-01T00:00:00Z")
        self.assertTrue(row["campaign_id"].startswith("MVC-"))
        self.assertEqual(row["workflow_status"], "draft")
        self.assertEqual(row["method"], "interview")
        fetched = campaigns.get(self.conn, row["campaign_id"])
        self.assertEqual(fetched["title"], VALID_INPUT["title"])

    def test_viewer_cannot_create(self):
        with self.assertRaises(AuthError):
            campaigns.create(self.conn, self.config, VIEWER, dict(VALID_INPUT), "2026-01-01T00:00:00Z")

    def test_missing_required_fields_rejected(self):
        bad = {k: v for k, v in VALID_INPUT.items() if k not in ("title", "objective")}
        with self.assertRaises(ValidationError):
            campaigns.create(self.conn, self.config, RESEARCHER, bad, "2026-01-01T00:00:00Z")

    def test_invalid_method_rejected(self):
        bad = {**VALID_INPUT, "method": "phone_call"}
        with self.assertRaises(ValidationError):
            campaigns.create(self.conn, self.config, RESEARCHER, bad, "2026-01-01T00:00:00Z")

    def test_invalid_linked_ids_rejected(self):
        bad = {**VALID_INPUT, "linked_opportunities": ["not-an-opp-id"]}
        with self.assertRaises(ValidationError):
            campaigns.create(self.conn, self.config, RESEARCHER, bad, "2026-01-01T00:00:00Z")

    def test_synthetic_only_blocks_non_synthetic_classification(self):
        bad = {**VALID_INPUT, "data_classification": "confidential"}
        with self.assertRaises(ValidationError):
            campaigns.create(self.conn, self.config, RESEARCHER, bad, "2026-01-01T00:00:00Z")

    def test_synthetic_only_disabled_allows_other_classifications(self):
        cfg = Config(env={"MV_TOKENS": "a:t:admin", "MV_SYNTHETIC_ONLY": "0"})
        row = campaigns.create(self.conn, cfg, RESEARCHER,
                               {**VALID_INPUT, "data_classification": "confidential"},
                               "2026-01-01T00:00:00Z")
        self.assertEqual(row["data_classification"], "confidential")

    def test_valid_lifecycle_transitions(self):
        row = campaigns.create(self.conn, self.config, RESEARCHER, dict(VALID_INPUT), "t0")
        cid = row["campaign_id"]
        campaigns.transition(self.conn, REVIEWER, cid, "approved", "t1")
        campaigns.transition(self.conn, RESEARCHER, cid, "active", "t2")
        campaigns.transition(self.conn, RESEARCHER, cid, "paused", "t3")
        campaigns.transition(self.conn, RESEARCHER, cid, "active", "t4")
        final = campaigns.transition(self.conn, RESEARCHER, cid, "completed", "t5")
        self.assertEqual(final["workflow_status"], "completed")

    def test_invalid_transition_rejected(self):
        row = campaigns.create(self.conn, self.config, RESEARCHER, dict(VALID_INPUT), "t0")
        with self.assertRaises(ValidationError):
            campaigns.transition(self.conn, REVIEWER, row["campaign_id"], "active", "t1")  # skip approved

    def test_only_reviewer_or_admin_can_approve(self):
        row = campaigns.create(self.conn, self.config, RESEARCHER, dict(VALID_INPUT), "t0")
        with self.assertRaises(AuthError):
            campaigns.transition(self.conn, RESEARCHER, row["campaign_id"], "approved", "t1")
        campaigns.transition(self.conn, REVIEWER, row["campaign_id"], "approved", "t1")  # ok

    def test_only_admin_can_archive(self):
        row = campaigns.create(self.conn, self.config, RESEARCHER, dict(VALID_INPUT), "t0")
        campaigns.transition(self.conn, REVIEWER, row["campaign_id"], "approved", "t1")
        with self.assertRaises(AuthError):
            campaigns.archive(self.conn, REVIEWER, row["campaign_id"], "t2")
        campaigns.archive(self.conn, ADMIN, row["campaign_id"], "t2")  # ok

    def test_archived_is_terminal(self):
        row = campaigns.create(self.conn, self.config, RESEARCHER, dict(VALID_INPUT), "t0")
        campaigns.archive(self.conn, ADMIN, row["campaign_id"], "t1")
        with self.assertRaises(ValidationError):
            campaigns.transition(self.conn, ADMIN, row["campaign_id"], "active", "t2")

    def test_only_draft_editable_directly(self):
        row = campaigns.create(self.conn, self.config, RESEARCHER, dict(VALID_INPUT), "t0")
        campaigns.transition(self.conn, REVIEWER, row["campaign_id"], "approved", "t1")
        with self.assertRaises(ValidationError):
            campaigns.update_draft(self.conn, RESEARCHER, row["campaign_id"],
                                   {"title": "changed"}, self.config, "t2")

    def test_create_and_transition_are_audited(self):
        row = campaigns.create(self.conn, self.config, RESEARCHER, dict(VALID_INPUT), "t0")
        campaigns.transition(self.conn, REVIEWER, row["campaign_id"], "approved", "t1", reason="looks good")
        events = audit.list_for_object(self.conn, "campaign", row["campaign_id"])
        actions = [e["action"] for e in events]
        self.assertEqual(actions, ["create", "transition"])
        self.assertEqual(events[1]["reason"], "looks good")
        self.assertIsNotNone(events[0]["after_hash"])

    def test_get_nonexistent_campaign_raises(self):
        from app.db import DbError
        with self.assertRaises(DbError):
            campaigns.get(self.conn, "MVC-DOES-NOT-EXIST")

    def test_list_all_returns_created_campaigns(self):
        campaigns.create(self.conn, self.config, RESEARCHER, {**VALID_INPUT, "campaign_id": "MVC-TEST-A"}, "t0")
        campaigns.create(self.conn, self.config, RESEARCHER, {**VALID_INPUT, "campaign_id": "MVC-TEST-B"}, "t0")
        ids = {c["campaign_id"] for c in campaigns.list_all(self.conn)}
        self.assertEqual(ids, {"MVC-TEST-A", "MVC-TEST-B"})

    def test_duplicate_campaign_id_rejected(self):
        campaigns.create(self.conn, self.config, RESEARCHER, {**VALID_INPUT, "campaign_id": "MVC-TEST-DUP"}, "t0")
        with self.assertRaises(ValidationError):
            campaigns.create(self.conn, self.config, RESEARCHER, {**VALID_INPUT, "campaign_id": "MVC-TEST-DUP"}, "t0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
