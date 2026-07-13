"""Shared synthetic-only test fixtures for Phase 2 tests. Not itself a test
module (no Test* classes) — imported by the Phase 2 test files to avoid
duplicating campaign/guide/participant bootstrap boilerplate."""

import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from app import campaigns, guides, identity, participants  # noqa: E402
from app.config import Config  # noqa: E402
from app.db import connect_identity, connect_mv  # noqa: E402

RESEARCHER = {"role": "researcher", "label": "researcher-1"}
REVIEWER = {"role": "reviewer", "label": "reviewer-1"}
ADMIN = {"role": "admin", "label": "admin-1"}
VIEWER = {"role": "viewer", "label": "viewer-1"}

VALID_IDENTITY = {
    "consent_status": "granted", "permitted_use": "internal_research_only",
    "quote_permission": True, "ai_processing_permission": True,
    "data_classification": "synthetic",
}


class Clock:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1
        return f"2026-01-01T00:00:{self.n:02d}Z"


def make_dbs(tmp_dir):
    conn = connect_mv(Path(tmp_dir) / "mv.db")
    identity_conn = connect_identity(Path(tmp_dir) / "identity.db")
    config = Config(env={"MV_TOKENS": "a:t:admin", "MV_TRANSCRIPT_DIR": str(Path(tmp_dir) / "transcripts")})
    return conn, identity_conn, config


def make_active_campaign_with_approved_guide(conn, config, clock, questions=None):
    questions = questions or [{"text": "What is your biggest pain?", "purpose": "problem"},
                              {"text": "How often does it happen?", "purpose": "frequency"}]
    camp = campaigns.create(conn, config, RESEARCHER, {
        "title": "MVC-TEST-FIXTURE", "objective": "synthetic fixture campaign",
        "method": "interview", "data_classification": "synthetic"}, clock())
    guide = guides.create(conn, RESEARCHER, camp["campaign_id"], questions, clock())
    guides.approve(conn, config, REVIEWER, guide["guide_id"], clock())
    campaigns.transition(conn, REVIEWER, camp["campaign_id"], "approved", clock())
    campaigns.transition(conn, RESEARCHER, camp["campaign_id"], "active", clock())
    return camp, guide


def make_participant(conn, identity_conn, config, clock, campaign_id, **overrides):
    identity_data = {**VALID_IDENTITY, **overrides.pop("identity_overrides", {})}
    idrow = identity.create(identity_conn, config, RESEARCHER, identity_data, clock())
    data = {
        "campaign_id": campaign_id, "merchant_identity_id": idrow["merchant_identity_id"],
        "consent_status": "granted", "permitted_use": "internal_research_only",
        "quote_permission": True, "ai_processing_permission": True,
        "data_classification": "synthetic",
    }
    data.update(overrides)
    return participants.create(conn, identity_conn, config, RESEARCHER, data, clock())
