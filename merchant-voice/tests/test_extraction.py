"""Extraction orchestration tests: persistence as pending_review,
idempotency/rerun/supersession, audit safety, provider-payload/prompt
non-persistence, and provider-error handling. Uses a locally-defined stub
ConversationModel (not MockProvider's fixed echo behavior) so the exact
JSON returned to the extraction pipeline is fully controlled — this tests
OUR validation/persistence pipeline, not a model's reasoning quality."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (ADMIN, RESEARCHER, REVIEWER, VIEWER, make_active_campaign_with_approved_guide,
                      make_dbs, make_participant, make_response)

from app import extraction
from app.auth import AuthError
from app.db import DbError
from app.eligibility import ExtractionError
from shared.llm.provider import ConversationModel, ModelResponse, ProviderError


class StubProvider(ConversationModel):
    def __init__(self, observations=None, raise_error=None, tool_calls=None):
        self.observations = observations if observations is not None else []
        self.raise_error = raise_error
        self.tool_calls = tool_calls
        self.calls = []

    def generate(self, messages, tools, system_prompt, configuration):
        self.calls.append({"messages": messages, "tools": tools, "system_prompt": system_prompt})
        if self.raise_error:
            raise self.raise_error
        if self.tool_calls is not None:
            return ModelResponse(content="", tool_calls=self.tool_calls, stop_reason="tool_use")
        return ModelResponse(content=json.dumps({"observations": self.observations}))


class ExtractionOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn, self.identity_conn, self.config = make_dbs(self.tmp.name)
        self.clock_n = 0
        self.camp, self.guide = make_active_campaign_with_approved_guide(
            self.conn, self.config, self._clock, campaign_overrides={"linked_opportunities": ["OPP-013"]})
        self.participant = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                            self.camp["campaign_id"])
        self.q1 = self.guide["questions"][0]["question_id"]
        self.response = make_response(self.conn, self.config, self._clock, self.camp, self.guide,
                                      self.participant, [
                                          {"question_id": self.q1,
                                           "answer": "Suppliers cancel late payments every week and it costs us money."}])
        self.answer_id = self.response["answers"][0]["answer_id"]

    def _clock(self):
        self.clock_n += 1
        return f"2026-01-01T00:00:{self.clock_n:02d}Z"

    def _patch_provider(self, provider):
        original = extraction.make_provider
        extraction.make_provider = lambda cfg: provider
        self.addCleanup(lambda: setattr(extraction, "make_provider", original))

    def _valid_observation(self, **overrides):
        obs = {
            "observation_type": "pain", "source_answer_id": self.answer_id,
            "source_excerpt": "Suppliers cancel late payments every week",
            "normalized_statement": "Supplier payments are cancelled weekly, costing the merchant money.",
            "is_direct_quote": False, "extraction_confidence": "high", "frequency": "weekly",
        }
        obs.update(overrides)
        return obs

    def test_structured_output_accepted_end_to_end(self):
        self._patch_provider(StubProvider(observations=[self._valid_observation()]))
        run, observations = extraction.run_extraction(self.conn, self.config, RESEARCHER,
                                                       self.response["response_id"], self._clock())
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["accepted_count"], 1)
        self.assertEqual(len(observations), 1)

    def test_every_observation_persisted_pending_review(self):
        self._patch_provider(StubProvider(observations=[self._valid_observation()]))
        run, observations = extraction.run_extraction(self.conn, self.config, RESEARCHER,
                                                       self.response["response_id"], self._clock())
        for o in observations:
            self.assertEqual(o["workflow_status"], "pending_review")
            self.assertEqual(o["suppression_status"], "active")

    def test_model_cannot_set_approved_status(self):
        self._patch_provider(StubProvider(observations=[
            self._valid_observation(workflow_status="approved")]))  # model tries to smuggle a status
        run, observations = extraction.run_extraction(self.conn, self.config, RESEARCHER,
                                                       self.response["response_id"], self._clock())
        self.assertEqual(observations[0]["workflow_status"], "pending_review")

    def test_tool_call_response_parsed(self):
        self._patch_provider(StubProvider(tool_calls=[
            {"name": "propose_observations", "arguments": {"observations": [self._valid_observation()]}}]))
        run, observations = extraction.run_extraction(self.conn, self.config, RESEARCHER,
                                                       self.response["response_id"], self._clock())
        self.assertEqual(run["accepted_count"], 1)

    def test_rejected_observations_counted_not_persisted(self):
        self._patch_provider(StubProvider(observations=[
            self._valid_observation(),
            {"observation_type": "pain", "source_answer_id": "MVA-fake", "source_excerpt": "x",
             "normalized_statement": "x", "is_direct_quote": False, "extraction_confidence": "high"}]))
        run, observations = extraction.run_extraction(self.conn, self.config, RESEARCHER,
                                                       self.response["response_id"], self._clock())
        self.assertEqual(run["proposed_count"], 2)
        self.assertEqual(run["accepted_count"], 1)
        self.assertEqual(run["rejected_count"], 1)

    def test_same_source_hash_returns_existing_run(self):
        provider = StubProvider(observations=[self._valid_observation()])
        self._patch_provider(provider)
        run1, _ = extraction.run_extraction(self.conn, self.config, RESEARCHER,
                                            self.response["response_id"], self._clock())
        run2, _ = extraction.run_extraction(self.conn, self.config, RESEARCHER,
                                            self.response["response_id"], self._clock())
        self.assertEqual(run1["extraction_run_id"], run2["extraction_run_id"])
        self.assertEqual(len(provider.calls), 1)  # no second provider call

    def test_explicit_rerun_creates_new_run(self):
        provider = StubProvider(observations=[self._valid_observation()])
        self._patch_provider(provider)
        run1, _ = extraction.run_extraction(self.conn, self.config, RESEARCHER,
                                            self.response["response_id"], self._clock())
        run2, _ = extraction.run_extraction(self.conn, self.config, RESEARCHER,
                                            self.response["response_id"], self._clock(), rerun=True)
        self.assertNotEqual(run1["extraction_run_id"], run2["extraction_run_id"])
        self.assertEqual(len(provider.calls), 2)

    def test_prior_pending_observations_superseded_on_rerun(self):
        self._patch_provider(StubProvider(observations=[self._valid_observation()]))
        run1, obs1 = extraction.run_extraction(self.conn, self.config, RESEARCHER,
                                               self.response["response_id"], self._clock())
        run2, obs2 = extraction.run_extraction(self.conn, self.config, RESEARCHER,
                                               self.response["response_id"], self._clock(), rerun=True)
        all_obs = extraction.list_observations_for_response(self.conn, self.response["response_id"],
                                                            include_superseded=True)
        old = extraction.get_observation(self.conn, obs1[0]["observation_id"])
        self.assertEqual(old["workflow_status"], "superseded")
        self.assertEqual(old["superseded_by_run_id"], run2["extraction_run_id"])
        new = extraction.get_observation(self.conn, obs2[0]["observation_id"])
        self.assertEqual(new["workflow_status"], "pending_review")

    def test_list_observations_excludes_superseded_by_default(self):
        self._patch_provider(StubProvider(observations=[self._valid_observation()]))
        extraction.run_extraction(self.conn, self.config, RESEARCHER, self.response["response_id"], self._clock())
        extraction.run_extraction(self.conn, self.config, RESEARCHER, self.response["response_id"],
                                  self._clock(), rerun=True)
        visible = extraction.list_observations_for_response(self.conn, self.response["response_id"])
        self.assertEqual(len(visible), 1)
        self.assertTrue(all(o["workflow_status"] == "pending_review" for o in visible))

    def test_duplicate_extraction_blocked_while_in_progress(self):
        with self.conn:
            self.conn.execute(
                "INSERT INTO extraction_runs (extraction_run_id, response_id, provider, model, started_at, "
                "completed_at, status, input_source_hash, proposed_count, accepted_count, rejected_count, "
                "safe_error_code, actor_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("MER-fake000001", self.response["response_id"], "mock", "mock", self._clock(), None,
                 "in_progress", "sha256:x", None, None, None, None, "someone"))
        with self.assertRaises(ExtractionError) as ctx:
            extraction.run_extraction(self.conn, self.config, RESEARCHER, self.response["response_id"], self._clock())
        self.assertEqual(ctx.exception.code, "duplicate_extraction")

    def test_provider_timeout_mapped_and_run_marked_failed(self):
        self._patch_provider(StubProvider(raise_error=ProviderError("timed out", timeout=True)))
        with self.assertRaises(ExtractionError) as ctx:
            extraction.run_extraction(self.conn, self.config, RESEARCHER, self.response["response_id"], self._clock())
        self.assertEqual(ctx.exception.code, "provider_timeout")
        runs = extraction.list_runs_for_response(self.conn, self.response["response_id"])
        self.assertEqual(runs[-1]["status"], "failed")
        self.assertEqual(runs[-1]["safe_error_code"], "provider_timeout")

    def test_provider_error_mapped(self):
        self._patch_provider(StubProvider(raise_error=ProviderError("boom", timeout=False)))
        with self.assertRaises(ExtractionError) as ctx:
            extraction.run_extraction(self.conn, self.config, RESEARCHER, self.response["response_id"], self._clock())
        self.assertEqual(ctx.exception.code, "provider_error")

    def test_invalid_provider_output_handled_safely(self):
        class GarbageProvider(ConversationModel):
            def generate(self, messages, tools, system_prompt, configuration):
                return ModelResponse(content="not json at all { garbage")
        self._patch_provider(GarbageProvider())
        with self.assertRaises(ExtractionError) as ctx:
            extraction.run_extraction(self.conn, self.config, RESEARCHER, self.response["response_id"], self._clock())
        self.assertEqual(ctx.exception.code, "invalid_provider_output")

    def test_viewer_forbidden(self):
        with self.assertRaises(AuthError):
            extraction.run_extraction(self.conn, self.config, VIEWER, self.response["response_id"], self._clock())

    def test_researcher_permitted(self):
        self._patch_provider(StubProvider(observations=[self._valid_observation()]))
        run, _ = extraction.run_extraction(self.conn, self.config, RESEARCHER,
                                           self.response["response_id"], self._clock())
        self.assertEqual(run["status"], "completed")

    def test_reviewer_and_admin_permitted(self):
        for principal in (REVIEWER, ADMIN):
            self._patch_provider(StubProvider(observations=[self._valid_observation()]))
            run, _ = extraction.run_extraction(self.conn, self.config, principal,
                                               self.response["response_id"], self._clock(), rerun=True)
            self.assertEqual(run["status"], "completed")

    def test_eligibility_denied_audited_and_no_provider_call(self):
        from app import suppression
        suppression.suppress_participant(self.conn, RESEARCHER, self.participant["participant_id"],
                                         "withdrawn", self._clock(), transcript_dir=self.config.transcript_dir)
        provider = StubProvider(observations=[])
        self._patch_provider(provider)
        with self.assertRaises(ExtractionError):
            extraction.run_extraction(self.conn, self.config, RESEARCHER, self.response["response_id"], self._clock())
        self.assertEqual(provider.calls, [])
        from app import audit
        events = audit.list_for_object(self.conn, "response", self.response["response_id"])
        self.assertTrue(any(e["action"] == "extraction_denied" for e in events))

    def test_audit_contains_no_source_text(self):
        self._patch_provider(StubProvider(observations=[self._valid_observation()]))
        extraction.run_extraction(self.conn, self.config, RESEARCHER, self.response["response_id"], self._clock())
        from app import audit
        events = audit.list_for_object(self.conn, "response", self.response["response_id"])
        blob = str(events)
        self.assertNotIn("Suppliers cancel late payments", blob)

    def test_provider_payload_and_prompt_not_stored_anywhere(self):
        self._patch_provider(StubProvider(observations=[self._valid_observation()]))
        run, observations = extraction.run_extraction(self.conn, self.config, RESEARCHER,
                                                       self.response["response_id"], self._clock())
        # extraction_runs row has no column for a payload/prompt at all
        self.assertNotIn("prompt", run)
        self.assertNotIn("payload", run)
        row = self.conn.execute("SELECT * FROM extraction_runs WHERE extraction_run_id=?",
                                (run["extraction_run_id"],)).fetchone()
        columns = [d[0] for d in self.conn.execute(
            "PRAGMA table_info(extraction_runs)").fetchall()]
        self.assertNotIn("prompt", columns)
        self.assertNotIn("payload", columns)
        self.assertNotIn("system_prompt", columns)

    def test_get_run_not_found(self):
        with self.assertRaises(DbError):
            extraction.get_run(self.conn, "MER-DOES-NOT-EXIST")

    def test_get_observation_not_found(self):
        with self.assertRaises(DbError):
            extraction.get_observation(self.conn, "MVO-DOES-NOT-EXIST")

    def test_no_side_effects_on_other_response_data(self):
        self._patch_provider(StubProvider(observations=[self._valid_observation()]))
        before = dict(self.response)
        extraction.run_extraction(self.conn, self.config, RESEARCHER, self.response["response_id"], self._clock())
        from app import responses as responses_mod
        after = responses_mod.get(self.conn, self.response["response_id"])
        self.assertEqual(before["consent_snapshot"], after["consent_snapshot"])
        self.assertEqual(before["answers"][0]["original_answer"], after["answers"][0]["original_answer"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
