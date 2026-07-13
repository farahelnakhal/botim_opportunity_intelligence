"""API-layer tests for Phase 3 extraction routes: role matrix, structured
errors, end-to-end wiring through the real Api dispatcher."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from app import extraction as extraction_mod  # noqa: E402
from app.api import Api  # noqa: E402
from app.config import Config  # noqa: E402
from app.db import connect_identity, connect_mv  # noqa: E402
from shared.llm.provider import ConversationModel, ModelResponse  # noqa: E402

TOKENS = "admin:tok-admin:admin,researcher:tok-res:researcher,reviewer:tok-rev:reviewer,viewer:tok-view:viewer"


class StubProvider(ConversationModel):
    def __init__(self, answer_id):
        self.answer_id = answer_id

    def generate(self, messages, tools, system_prompt, configuration):
        return ModelResponse(content=json.dumps({"observations": [{
            "observation_type": "pain", "source_answer_id": self.answer_id,
            "source_excerpt": "Suppliers cancel late payments every week",
            "normalized_statement": "Supplier payments are cancelled weekly.",
            "is_direct_quote": False, "extraction_confidence": "high", "frequency": "weekly",
        }]}))


class Phase3ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Config(env={"MV_TOKENS": TOKENS,
                                  "MV_TRANSCRIPT_DIR": str(Path(self.tmp.name) / "transcripts")})
        conn = connect_mv(Path(self.tmp.name) / "mv.db")
        identity_conn = connect_identity(Path(self.tmp.name) / "identity.db")
        self.counter = {"n": 0}

        def now():
            self.counter["n"] += 1
            return f"2026-01-01T00:00:{self.counter['n']:02d}Z"

        self.api = Api(self.config, conn, identity_conn, now)

    def _patch_provider(self, provider):
        original = extraction_mod.make_provider
        extraction_mod.make_provider = lambda cfg: provider
        self.addCleanup(lambda: setattr(extraction_mod, "make_provider", original))

    def _call(self, method, path, token, body=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        b = json.dumps(body).encode() if body is not None else b""
        return self.api.handle(method, path, headers, b)

    def _bootstrap(self):
        _, camp = self._call("POST", "/api/merchant-voice/campaigns", "tok-res", {
            "title": "MVC-TEST-P3API", "objective": "phase 3 api test", "method": "interview",
            "linked_opportunities": ["OPP-013"], "data_classification": "synthetic"})
        cid = camp["campaign_id"]
        _, guide = self._call("POST", f"/api/merchant-voice/campaigns/{cid}/guides", "tok-res", {
            "questions": [{"text": "What is your biggest pain?", "purpose": "problem"}]})
        gid = guide["guide_id"]
        self._call("POST", f"/api/merchant-voice/guides/{gid}/approve", "tok-rev")
        self._call("POST", f"/api/merchant-voice/campaigns/{cid}/transition", "tok-rev",
                   {"workflow_status": "approved"})
        self._call("POST", f"/api/merchant-voice/campaigns/{cid}/transition", "tok-res",
                   {"workflow_status": "active"})
        _, part = self._call("POST", "/api/merchant-voice/participants", "tok-res", {
            "campaign_id": cid,
            "merchant_identity": {"consent_status": "granted", "permitted_use": "internal_research_only",
                                  "quote_permission": True, "ai_processing_permission": True,
                                  "data_classification": "synthetic"},
            "consent_status": "granted", "permitted_use": "internal_research_only",
            "quote_permission": True, "ai_processing_permission": True, "data_classification": "synthetic"})
        pid = part["participant_id"]
        qid = guide["questions"][0]["question_id"]
        _, resp = self._call("POST", "/api/merchant-voice/responses", "tok-res", {
            "campaign_id": cid, "participant_id": pid, "guide_id": gid, "method": "interview",
            "answers": [{"question_id": qid, "answer": "Suppliers cancel late payments every week."}]})
        return cid, gid, pid, resp["response_id"], resp["answers"][0]["answer_id"]

    def test_viewer_forbidden_from_all_extraction_routes(self):
        cid, gid, pid, rid, answer_id = self._bootstrap()
        for method, path, body in (
            ("POST", f"/api/merchant-voice/responses/{rid}/extract", {}),
            ("GET", f"/api/merchant-voice/responses/{rid}/extraction-runs", None),
            ("GET", f"/api/merchant-voice/responses/{rid}/observations", None),
        ):
            status, _ = self._call(method, path, "tok-view", body)
            self.assertEqual(status, 403, f"{method} {path} should be forbidden for viewer")

    def test_researcher_permitted_full_round_trip(self):
        cid, gid, pid, rid, answer_id = self._bootstrap()
        self._patch_provider(StubProvider(answer_id))
        status, result = self._call("POST", f"/api/merchant-voice/responses/{rid}/extract", "tok-res", {})
        self.assertEqual(status, 201)
        self.assertEqual(result["extraction_run"]["status"], "completed")
        run_id = result["extraction_run"]["extraction_run_id"]

        status, runs = self._call("GET", f"/api/merchant-voice/responses/{rid}/extraction-runs", "tok-res")
        self.assertEqual(status, 200)
        self.assertEqual(len(runs["extraction_runs"]), 1)

        status, run = self._call("GET", f"/api/merchant-voice/extraction-runs/{run_id}", "tok-res")
        self.assertEqual(status, 200)
        self.assertEqual(run["extraction_run_id"], run_id)

        status, obs_list = self._call("GET", f"/api/merchant-voice/responses/{rid}/observations", "tok-res")
        self.assertEqual(status, 200)
        self.assertEqual(len(obs_list["observations"]), 1)
        obs_id = obs_list["observations"][0]["observation_id"]

        status, obs = self._call("GET", f"/api/merchant-voice/observations/{obs_id}", "tok-res")
        self.assertEqual(status, 200)
        self.assertEqual(obs["review_status"], "pending_review")

    def test_ineligible_response_returns_structured_error(self):
        cid, gid, pid, rid, answer_id = self._bootstrap()
        status, part2 = self._call("POST", "/api/merchant-voice/participants", "tok-res", {
            "campaign_id": cid,
            "merchant_identity": {"consent_status": "granted", "permitted_use": "internal_research_only",
                                  "quote_permission": True, "ai_processing_permission": False,
                                  "data_classification": "synthetic"},
            "consent_status": "granted", "permitted_use": "internal_research_only",
            "quote_permission": True, "ai_processing_permission": False, "data_classification": "synthetic"})
        qid_row = self._call("GET", f"/api/merchant-voice/campaigns/{cid}/guides", "tok-res")[1]["guides"][0]
        qid = qid_row["questions"][0]["question_id"]
        status, resp2 = self._call("POST", "/api/merchant-voice/responses", "tok-res", {
            "campaign_id": cid, "participant_id": part2["participant_id"], "guide_id": gid,
            "method": "interview", "answers": [{"question_id": qid, "answer": "another synthetic answer"}]})
        status, body = self._call("POST", f"/api/merchant-voice/responses/{resp2['response_id']}/extract",
                                  "tok-res", {})
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "ai_processing_denied")
        self.assertNotIn("Traceback", json.dumps(body))

    def test_not_found_observation_structured_404(self):
        status, body = self._call("GET", "/api/merchant-voice/observations/MVO-nope", "tok-res")
        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "not_found")

    def test_rerun_body_field_honored(self):
        cid, gid, pid, rid, answer_id = self._bootstrap()
        self._patch_provider(StubProvider(answer_id))
        status, result1 = self._call("POST", f"/api/merchant-voice/responses/{rid}/extract", "tok-res", {})
        status, result2 = self._call("POST", f"/api/merchant-voice/responses/{rid}/extract", "tok-res",
                                     {"rerun": True})
        self.assertNotEqual(result1["extraction_run"]["extraction_run_id"],
                            result2["extraction_run"]["extraction_run_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
