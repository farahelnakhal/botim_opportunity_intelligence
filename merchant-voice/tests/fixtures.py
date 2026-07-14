"""Shared synthetic-only test fixtures for Phase 2/3/4 tests. Not itself a
test module (no Test* classes) — imported by test files to avoid
duplicating campaign/guide/participant/observation bootstrap boilerplate."""

import json
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from app import campaigns, extraction, guides, identity, observation_review, participants, responses  # noqa: E402
from app.config import Config  # noqa: E402
from app.db import connect_identity, connect_mv  # noqa: E402
from shared.llm.provider import ConversationModel, ModelResponse  # noqa: E402

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


def make_active_campaign_with_approved_guide(conn, config, clock, questions=None, method="interview",
                                             campaign_overrides=None):
    questions = questions or [{"text": "What is your biggest pain?", "purpose": "problem"},
                              {"text": "How often does it happen?", "purpose": "frequency"}]
    data = {
        "title": "MVC-TEST-FIXTURE", "objective": "synthetic fixture campaign",
        "method": method, "data_classification": "synthetic",
    }
    data.update(campaign_overrides or {})
    camp = campaigns.create(conn, config, RESEARCHER, data, clock())
    guide = guides.create(conn, RESEARCHER, camp["campaign_id"], questions, clock())
    guides.approve(conn, config, REVIEWER, guide["guide_id"], clock())
    campaigns.transition(conn, REVIEWER, camp["campaign_id"], "approved", clock())
    campaigns.transition(conn, RESEARCHER, camp["campaign_id"], "active", clock())
    return camp, guide


def make_response(conn, config, clock, campaign, guide, participant, answers):
    """`answers`: list of {"question_id", "answer", ...} dicts (as accepted by
    responses.create's "answers" field)."""
    return responses.create(conn, config, RESEARCHER, {
        "campaign_id": campaign["campaign_id"], "participant_id": participant["participant_id"],
        "guide_id": guide["guide_id"], "method": campaign["method"], "answers": answers}, clock())


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


class _FixtureStubProvider(ConversationModel):
    def __init__(self, proposals):
        self.proposals = proposals

    def generate(self, messages, tools, system_prompt, configuration):
        return ModelResponse(content=json.dumps({"observations": self.proposals}))


def make_observation(conn, config, clock, response, answer_index, text, observation_type="pain",
                     principal=None, rerun=False, **overrides):
    """Runs a single-observation extraction against `response`'s answer at
    `answer_index`, using a fixture-local stub provider (not the real
    MockProvider echo) so the proposed observation content is fully
    controlled. Returns the created observation dict. Pass `rerun=True` to
    force a fresh extraction run against a response already extracted once
    (idempotency would otherwise just return the earlier observations)."""
    answer_id = response["answers"][answer_index]["answer_id"]
    proposal = {
        "observation_type": observation_type, "source_answer_id": answer_id, "source_excerpt": text,
        "normalized_statement": text, "is_direct_quote": False, "extraction_confidence": "high",
    }
    proposal.update(overrides)
    original = extraction.make_provider
    extraction.make_provider = lambda cfg: _FixtureStubProvider([proposal])
    try:
        run, observations = extraction.run_extraction(conn, config, principal or RESEARCHER,
                                                       response["response_id"], clock(), rerun=rerun)
    finally:
        extraction.make_provider = original
    return observations[0]


def make_approved_observation(conn, identity_conn, config, clock, campaign, guide, text,
                              question_index=0, observation_type="pain", participant=None,
                              approver=None, **overrides):
    """Creates a participant (unless given) + response + extracted
    observation, then approves it. Returns (observation, participant,
    response)."""
    if participant is None:
        participant = make_participant(conn, identity_conn, config, clock, campaign["campaign_id"])
    question_id = guide["questions"][question_index]["question_id"]
    response = make_response(conn, config, clock, campaign, guide, participant,
                             [{"question_id": question_id, "answer": text}])
    obs = make_observation(conn, config, clock, response, 0, text, observation_type=observation_type, **overrides)
    approved = observation_review.approve(conn, config, approver or REVIEWER, obs["observation_id"], clock())
    return approved, participant, response
