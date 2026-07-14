"""API-layer tests for Phase 5 routes: proposal generate->submit->approve->
approve-export->export round trip, published-query surface, role matrix,
structured errors, and regression checks that Phase 1-4 routes and
Copilot/shared behavior are unaffected."""

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


class Phase5ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.export_root = tempfile.TemporaryDirectory()
        self.addCleanup(self.export_root.cleanup)
        self.config = Config(env={"MV_TOKENS": TOKENS,
                                  "MV_TRANSCRIPT_DIR": str(Path(self.tmp.name) / "transcripts"),
                                  "MV_EXPORT_ROOT": self.export_root.name})
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

    def _bootstrap_published_finding(self):
        _, camp = self._call("POST", "/api/merchant-voice/campaigns", "tok-res", {
            "title": "MVC-TEST-P5API", "objective": "phase 5 api test", "method": "interview",
            "data_classification": "synthetic"})
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
        rid, answer_id = resp["response_id"], resp["answers"][0]["answer_id"]
        self._patch_provider(StubProvider(answer_id))
        status, result = self._call("POST", f"/api/merchant-voice/responses/{rid}/extract", "tok-res", {})
        obs_id = result["observations"][0]["observation_id"]
        self._call("POST", f"/api/merchant-voice/observations/{obs_id}/approve", "tok-rev")
        status, candidate = self._call("POST", "/api/merchant-voice/evidence-candidates", "tok-res", {
            "campaign_id": cid, "finding_type": "pain", "statement": "Suppliers cancel late payments.",
            "proposed_evidence_role": "supporting",
            "observations": [{"observation_id": obs_id, "role": "supporting"}]})
        candidate_id = candidate["candidate_id"]
        self._call("POST", f"/api/merchant-voice/evidence-candidates/{candidate_id}/submit", "tok-res")
        status, result = self._call("POST", f"/api/merchant-voice/evidence-candidates/{candidate_id}/approve",
                                    "tok-rev")
        finding_id = result["finding"]["finding_id"]
        self._call("POST", f"/api/merchant-voice/findings/{finding_id}/publish", "tok-rev")
        return cid, finding_id, pid

    def _bootstrap_full_proposal(self):
        cid, finding_id, pid = self._bootstrap_published_finding()
        status, proposal = self._call("POST", f"/api/merchant-voice/findings/{finding_id}/part-a-proposals",
                                       "tok-res", {})
        self.assertEqual(status, 201)
        proposal_id = proposal["proposal_id"]
        self._call("POST", f"/api/merchant-voice/part-a-proposals/{proposal_id}/submit", "tok-res")
        self._call("POST", f"/api/merchant-voice/part-a-proposals/{proposal_id}/approve", "tok-rev")
        return cid, finding_id, proposal_id, pid

    def test_full_proposal_round_trip_to_export(self):
        cid, finding_id, proposal_id, pid = self._bootstrap_full_proposal()
        status, _ = self._call("POST", f"/api/merchant-voice/part-a-proposals/{proposal_id}/approve-export",
                               "tok-rev")
        self.assertEqual(status, 200)
        status, exported = self._call("POST", f"/api/merchant-voice/part-a-proposals/{proposal_id}/export",
                                      "tok-rev")
        self.assertEqual(status, 200)
        self.assertEqual(exported["export_status"], "exported")
        full_path = Path(self.export_root.name) / exported["export_path"]
        self.assertTrue(full_path.exists())
        self.assertIn("SYNTHETIC DATA", full_path.read_text(encoding="utf-8"))

    def test_reject_requires_reason(self):
        cid, finding_id, pid = self._bootstrap_published_finding()
        _, proposal = self._call("POST", f"/api/merchant-voice/findings/{finding_id}/part-a-proposals",
                                 "tok-res", {})
        proposal_id = proposal["proposal_id"]
        self._call("POST", f"/api/merchant-voice/part-a-proposals/{proposal_id}/submit", "tok-res")
        status, body = self._call("POST", f"/api/merchant-voice/part-a-proposals/{proposal_id}/reject",
                                  "tok-rev", {})
        self.assertEqual(status, 400)

    def test_self_approval_returns_403(self):
        cid, finding_id, pid = self._bootstrap_published_finding()
        status, proposal = self._call("POST", f"/api/merchant-voice/findings/{finding_id}/part-a-proposals",
                                       "tok-rev", {})
        proposal_id = proposal["proposal_id"]
        self._call("POST", f"/api/merchant-voice/part-a-proposals/{proposal_id}/submit", "tok-rev")
        status, body = self._call("POST", f"/api/merchant-voice/part-a-proposals/{proposal_id}/approve",
                                  "tok-rev")
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "self_approval_forbidden")

    def test_not_found_returns_404(self):
        status, body = self._call("GET", "/api/merchant-voice/part-a-proposals/MEP-nope", "tok-res")
        self.assertEqual(status, 404)

    def test_export_without_export_approval_returns_409(self):
        cid, finding_id, proposal_id, pid = self._bootstrap_full_proposal()
        status, body = self._call("POST", f"/api/merchant-voice/part-a-proposals/{proposal_id}/export",
                                  "tok-rev")
        self.assertEqual(status, 409)
        self.assertEqual(body["error"]["code"], "proposal_not_exportable")

    def test_viewer_forbidden_from_proposal_routes(self):
        cid, finding_id, proposal_id, pid = self._bootstrap_full_proposal()
        for method, path, body in (
            ("POST", f"/api/merchant-voice/findings/{finding_id}/part-a-proposals", {}),
            ("GET", "/api/merchant-voice/part-a-proposals", None),
            ("GET", f"/api/merchant-voice/part-a-proposals/{proposal_id}", None),
            ("PATCH", f"/api/merchant-voice/part-a-proposals/{proposal_id}", {"proposed_title": "x"}),
            ("POST", f"/api/merchant-voice/part-a-proposals/{proposal_id}/approve-export", {}),
            ("POST", f"/api/merchant-voice/part-a-proposals/{proposal_id}/export", {}),
        ):
            status, _ = self._call(method, path, "tok-view", body)
            self.assertEqual(status, 403, f"{method} {path} should be forbidden for viewer")

    def test_viewer_may_read_published_surface(self):
        cid, finding_id, pid = self._bootstrap_published_finding()
        status, result = self._call("GET", "/api/merchant-voice/published/findings", "tok-view")
        self.assertEqual(status, 200)
        self.assertEqual(len(result["findings"]), 1)
        status, summary = self._call("GET", f"/api/merchant-voice/published/campaigns/{cid}", "tok-view")
        self.assertEqual(status, 200)
        self.assertEqual(summary["published_finding_count"], 1)

    def test_published_surface_has_no_identity_fields(self):
        cid, finding_id, pid = self._bootstrap_published_finding()
        status, result = self._call("GET", "/api/merchant-voice/published/findings", "tok-view")
        self.assertNotIn(pid, json.dumps(result))

    def test_no_stack_trace_leaked_on_error(self):
        status, body = self._call("PATCH", "/api/merchant-voice/part-a-proposals/MEP-nope", "tok-res", {})
        self.assertNotIn("Traceback", json.dumps(body))

    def test_phase1_4_routes_unaffected(self):
        cid, finding_id, pid = self._bootstrap_published_finding()
        status, campaigns_list = self._call("GET", "/api/merchant-voice/campaigns", "tok-res")
        self.assertEqual(status, 200)
        status, finding = self._call("GET", f"/api/merchant-voice/findings/{finding_id}", "tok-res")
        self.assertEqual(status, 200)
        self.assertEqual(finding["publication_status"], "published")


if __name__ == "__main__":
    unittest.main(verbosity=2)
