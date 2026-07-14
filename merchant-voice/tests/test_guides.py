"""Research guide service tests: taxonomy validation, versioning, immutability,
self-approval rejection/audit."""

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from app import audit, campaigns, guides  # noqa: E402
from app.auth import AuthError  # noqa: E402
from app.config import Config  # noqa: E402
from app.db import connect_mv  # noqa: E402
from app.models import ValidationError  # noqa: E402

RESEARCHER = {"role": "researcher", "label": "researcher-1"}
REVIEWER = {"role": "reviewer", "label": "reviewer-1"}
ADMIN = {"role": "admin", "label": "admin-1"}
VIEWER = {"role": "viewer", "label": "viewer-1"}

VALID_CAMPAIGN = {
    "title": "MVC-TEST-002 guide pilot", "objective": "Test guide flow",
    "method": "interview", "data_classification": "synthetic",
}

VALID_QUESTIONS = [
    {"text": "What is your biggest supplier-payment problem?", "purpose": "problem"},
    {"text": "How often does this happen?", "purpose": "frequency"},
    {"text": "What do you do instead today?", "purpose": "workaround"},
]


class GuideTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn = connect_mv(Path(self.tmp.name) / "mv.db")
        self.config = Config(env={"MV_TOKENS": "a:t:admin"})
        self.campaign = campaigns.create(self.conn, self.config, RESEARCHER,
                                         dict(VALID_CAMPAIGN), "t0")

    def test_create_guide_happy_path(self):
        g = guides.create(self.conn, RESEARCHER, self.campaign["campaign_id"], VALID_QUESTIONS, "t0")
        self.assertEqual(g["version"], 1)
        self.assertEqual(g["workflow_status"], "draft")
        self.assertEqual(len(g["questions"]), 3)
        self.assertEqual(g["questions"][0]["purpose"], "problem")

    def test_viewer_cannot_create_guide(self):
        with self.assertRaises(AuthError):
            guides.create(self.conn, VIEWER, self.campaign["campaign_id"], VALID_QUESTIONS, "t0")

    def test_invalid_purpose_rejected(self):
        bad = [{"text": "x?", "purpose": "not_a_real_purpose"}]
        with self.assertRaises(ValidationError):
            guides.create(self.conn, RESEARCHER, self.campaign["campaign_id"], bad, "t0")

    def test_invalid_question_type_rejected(self):
        bad = [{"text": "x?", "purpose": "problem", "question_type": "video_response"}]
        with self.assertRaises(ValidationError):
            guides.create(self.conn, RESEARCHER, self.campaign["campaign_id"], bad, "t0")

    def test_empty_questions_rejected(self):
        with self.assertRaises(ValidationError):
            guides.create(self.conn, RESEARCHER, self.campaign["campaign_id"], [], "t0")

    def test_guide_versioning_increments(self):
        g1 = guides.create(self.conn, RESEARCHER, self.campaign["campaign_id"], VALID_QUESTIONS, "t0")
        guides.approve(self.conn, self.config, REVIEWER, g1["guide_id"], "t1")
        g2 = guides.new_version_from_approved(self.conn, RESEARCHER, g1["guide_id"], "t2")
        self.assertEqual(g2["version"], 2)
        self.assertNotEqual(g1["guide_id"], g2["guide_id"])
        versions = guides.list_versions(self.conn, self.campaign["campaign_id"])
        self.assertEqual([v["version"] for v in versions], [1, 2])

    def test_approved_guide_is_immutable(self):
        g = guides.create(self.conn, RESEARCHER, self.campaign["campaign_id"], VALID_QUESTIONS, "t0")
        guides.approve(self.conn, self.config, REVIEWER, g["guide_id"], "t1")
        with self.assertRaises(ValidationError):
            guides.update_draft(self.conn, RESEARCHER, g["guide_id"], VALID_QUESTIONS, "t2")

    def test_draft_guide_editable(self):
        g = guides.create(self.conn, RESEARCHER, self.campaign["campaign_id"], VALID_QUESTIONS, "t0")
        edited = [{"text": "Updated question?", "purpose": "trust"}]
        updated = guides.update_draft(self.conn, RESEARCHER, g["guide_id"], edited, "t1")
        self.assertEqual(len(updated["questions"]), 1)
        self.assertEqual(updated["questions"][0]["purpose"], "trust")

    def test_new_version_only_from_approved(self):
        g = guides.create(self.conn, RESEARCHER, self.campaign["campaign_id"], VALID_QUESTIONS, "t0")
        with self.assertRaises(ValidationError):
            guides.new_version_from_approved(self.conn, RESEARCHER, g["guide_id"], "t1")

    def test_self_approval_rejected_by_default(self):
        g = guides.create(self.conn, REVIEWER, self.campaign["campaign_id"], VALID_QUESTIONS, "t0")
        with self.assertRaises(AuthError):
            guides.approve(self.conn, self.config, REVIEWER, g["guide_id"], "t1")

    def test_self_approval_allowed_and_audited_when_enabled(self):
        cfg = Config(env={"MV_TOKENS": "a:t:admin", "MV_ALLOW_SELF_APPROVAL": "1"})
        g = guides.create(self.conn, REVIEWER, self.campaign["campaign_id"], VALID_QUESTIONS, "t0")
        approved = guides.approve(self.conn, cfg, REVIEWER, g["guide_id"], "t1")
        self.assertEqual(approved["workflow_status"], "approved")
        events = audit.list_for_object(self.conn, "guide", g["guide_id"])
        approve_event = next(e for e in events if e["action"] == "approve")
        self.assertTrue(approve_event["self_approval"])

    def test_non_self_approval_not_flagged(self):
        g = guides.create(self.conn, RESEARCHER, self.campaign["campaign_id"], VALID_QUESTIONS, "t0")
        guides.approve(self.conn, self.config, REVIEWER, g["guide_id"], "t1")
        events = audit.list_for_object(self.conn, "guide", g["guide_id"])
        approve_event = next(e for e in events if e["action"] == "approve")
        self.assertFalse(approve_event["self_approval"])

    def test_researcher_cannot_approve(self):
        g = guides.create(self.conn, RESEARCHER, self.campaign["campaign_id"], VALID_QUESTIONS, "t0")
        with self.assertRaises(AuthError):
            guides.approve(self.conn, self.config, RESEARCHER, g["guide_id"], "t1")

    def test_guide_create_is_audited(self):
        g = guides.create(self.conn, RESEARCHER, self.campaign["campaign_id"], VALID_QUESTIONS, "t0")
        events = audit.list_for_object(self.conn, "guide", g["guide_id"])
        self.assertEqual([e["action"] for e in events], ["create"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
