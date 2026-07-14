"""API-layer tests for Phase 4 routes: full review->candidate->finding->
publish round trip through the real Api dispatcher, the viewer/researcher/
reviewer/admin role matrix, structured error codes/status mapping, and
regression/security checks (no identity fields exposed, no stack traces,
existing Phase 1-3 routes unaffected)."""

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
    def __init__(self, answer_id, observation_type="pain", extra=None):
        self.answer_id = answer_id
        self.observation_type = observation_type
        self.extra = extra or {}

    def generate(self, messages, tools, system_prompt, configuration):
        payload = {"observation_type": self.observation_type, "source_answer_id": self.answer_id,
                  "source_excerpt": "Suppliers cancel late payments every week",
                  "normalized_statement": "Supplier payments are cancelled weekly.",
                  "is_direct_quote": False, "extraction_confidence": "high", "frequency": "weekly"}
        payload.update(self.extra)
        return ModelResponse(content=json.dumps({"observations": [payload]}))


class Phase4ApiTests(unittest.TestCase):
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

    def _bootstrap_participant_and_response(self, answer_text="Suppliers cancel late payments every week.",
                                            token="tok-res"):
        # always built by the researcher; a distinct reviewer approves the
        # guide — self-approval is a separate concern tested via _extract_one's
        # own token, not via who created the surrounding campaign/guide
        _, camp = self._call("POST", "/api/merchant-voice/campaigns", token, {
            "title": "MVC-TEST-P4API", "objective": "phase 4 api test", "method": "interview",
            "data_classification": "synthetic"})
        cid = camp["campaign_id"]
        _, guide = self._call("POST", f"/api/merchant-voice/campaigns/{cid}/guides", token, {
            "questions": [{"text": "What is your biggest pain?", "purpose": "problem"}]})
        gid = guide["guide_id"]
        self._call("POST", f"/api/merchant-voice/guides/{gid}/approve", "tok-rev")
        self._call("POST", f"/api/merchant-voice/campaigns/{cid}/transition", "tok-rev",
                   {"workflow_status": "approved"})
        self._call("POST", f"/api/merchant-voice/campaigns/{cid}/transition", token,
                   {"workflow_status": "active"})
        _, part = self._call("POST", "/api/merchant-voice/participants", token, {
            "campaign_id": cid,
            "merchant_identity": {"consent_status": "granted", "permitted_use": "internal_research_only",
                                  "quote_permission": True, "ai_processing_permission": True,
                                  "data_classification": "synthetic"},
            "consent_status": "granted", "permitted_use": "internal_research_only",
            "quote_permission": True, "ai_processing_permission": True, "data_classification": "synthetic"})
        pid = part["participant_id"]
        qid = guide["questions"][0]["question_id"]
        _, resp = self._call("POST", "/api/merchant-voice/responses", token, {
            "campaign_id": cid, "participant_id": pid, "guide_id": gid, "method": "interview",
            "answers": [{"question_id": qid, "answer": answer_text}]})
        return cid, gid, pid, resp["response_id"], resp["answers"][0]["answer_id"]

    def _extract_one(self, rid, answer_id, observation_type="pain", token="tok-res"):
        self._patch_provider(StubProvider(answer_id, observation_type=observation_type))
        status, result = self._call("POST", f"/api/merchant-voice/responses/{rid}/extract", token, {})
        self.assertEqual(status, 201)
        return result["observations"][0]["observation_id"]

    def _full_round_trip_to_published_finding(self):
        cid, gid, pid, rid, answer_id = self._bootstrap_participant_and_response()
        obs_id = self._extract_one(rid, answer_id)
        status, _ = self._call("POST", f"/api/merchant-voice/observations/{obs_id}/approve", "tok-rev")
        self.assertEqual(status, 200)
        status, candidate = self._call("POST", "/api/merchant-voice/evidence-candidates", "tok-res", {
            "campaign_id": cid, "finding_type": "pain", "statement": "Suppliers cancel late payments.",
            "proposed_evidence_role": "supporting",
            "observations": [{"observation_id": obs_id, "role": "supporting"}]})
        self.assertEqual(status, 201)
        candidate_id = candidate["candidate_id"]
        status, _ = self._call("POST", f"/api/merchant-voice/evidence-candidates/{candidate_id}/submit", "tok-res")
        self.assertEqual(status, 200)
        status, result = self._call("POST", f"/api/merchant-voice/evidence-candidates/{candidate_id}/approve",
                                    "tok-rev")
        self.assertEqual(status, 200)
        finding_id = result["finding"]["finding_id"]
        status, _ = self._call("POST", f"/api/merchant-voice/findings/{finding_id}/publish", "tok-rev")
        self.assertEqual(status, 200)
        return cid, obs_id, candidate_id, finding_id, pid

    def test_full_round_trip_to_published_finding(self):
        cid, obs_id, candidate_id, finding_id, pid = self._full_round_trip_to_published_finding()
        status, finding = self._call("GET", f"/api/merchant-voice/findings/{finding_id}", "tok-res")
        self.assertEqual(status, 200)
        self.assertEqual(finding["publication_status"], "published")
        self.assertEqual(finding["strength_band"], "single_signal")

    def test_review_queue_and_editing(self):
        cid, gid, pid, rid, answer_id = self._bootstrap_participant_and_response()
        obs_id = self._extract_one(rid, answer_id)
        status, queue = self._call("GET", "/api/merchant-voice/review/observations", "tok-res")
        self.assertEqual(status, 200)
        self.assertEqual(len(queue["observations"]), 1)
        status, edited = self._call("PATCH", f"/api/merchant-voice/observations/{obs_id}", "tok-res",
                                    {"reviewer_notes": "checked against transcript"})
        self.assertEqual(status, 200)
        self.assertEqual(edited["reviewer_notes"], "checked against transcript")

    def test_source_field_edit_returns_source_immutable(self):
        cid, gid, pid, rid, answer_id = self._bootstrap_participant_and_response()
        obs_id = self._extract_one(rid, answer_id)
        status, body = self._call("PATCH", f"/api/merchant-voice/observations/{obs_id}", "tok-res",
                                  {"source_excerpt": "fabricated"})
        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "source_immutable")

    def test_rejection_without_reason_returns_validation_error(self):
        cid, gid, pid, rid, answer_id = self._bootstrap_participant_and_response()
        obs_id = self._extract_one(rid, answer_id)
        status, body = self._call("POST", f"/api/merchant-voice/observations/{obs_id}/reject", "tok-rev", {})
        self.assertEqual(status, 400)

    def test_self_approval_returns_403_self_approval_forbidden(self):
        cid, gid, pid, rid, answer_id = self._bootstrap_participant_and_response()
        obs_id = self._extract_one(rid, answer_id, token="tok-rev")
        status, body = self._call("POST", f"/api/merchant-voice/observations/{obs_id}/approve", "tok-rev")
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "self_approval_forbidden")

    def test_missing_support_returns_400(self):
        cid, gid, pid, rid, answer_id = self._bootstrap_participant_and_response()
        obs_id = self._extract_one(rid, answer_id)
        self._call("POST", f"/api/merchant-voice/observations/{obs_id}/approve", "tok-rev")
        status, body = self._call("POST", "/api/merchant-voice/evidence-candidates", "tok-res", {
            "campaign_id": cid, "finding_type": "pain", "statement": "Suppliers cancel late payments.",
            "proposed_evidence_role": "supporting",
            "observations": [{"observation_id": obs_id, "role": "contextual"}]})
        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "missing_support")

    def test_stale_source_version_returns_409(self):
        cid, gid, pid, rid, answer_id = self._bootstrap_participant_and_response()
        obs_id = self._extract_one(rid, answer_id)
        self._call("POST", f"/api/merchant-voice/observations/{obs_id}/approve", "tok-rev")
        status, candidate = self._call("POST", "/api/merchant-voice/evidence-candidates", "tok-res", {
            "campaign_id": cid, "finding_type": "pain", "statement": "Suppliers cancel late payments.",
            "proposed_evidence_role": "supporting",
            "observations": [{"observation_id": obs_id, "role": "supporting"}]})
        candidate_id = candidate["candidate_id"]
        self._call("POST", f"/api/merchant-voice/participants/{pid}/withdraw-consent", "tok-res", {})
        status, body = self._call("POST", f"/api/merchant-voice/evidence-candidates/{candidate_id}/submit",
                                  "tok-res")
        self.assertEqual(status, 409)
        self.assertEqual(body["error"]["code"], "stale_source_version")

    def test_not_found_returns_404(self):
        status, body = self._call("GET", "/api/merchant-voice/evidence-candidates/MEC-nope", "tok-res")
        self.assertEqual(status, 404)
        status, body2 = self._call("GET", "/api/merchant-voice/findings/MEF-nope", "tok-res")
        self.assertEqual(status, 404)

    def test_viewer_forbidden_from_review_and_candidate_write_routes(self):
        cid, obs_id, candidate_id, finding_id, pid = self._full_round_trip_to_published_finding()
        for method, path, body in (
            ("GET", "/api/merchant-voice/review/observations", None),
            ("PATCH", f"/api/merchant-voice/observations/{obs_id}", {"reviewer_notes": "x"}),
            ("POST", f"/api/merchant-voice/observations/{obs_id}/approve", {}),
            ("POST", f"/api/merchant-voice/observations/{obs_id}/reject", {"reason": "duplicate"}),
            ("POST", f"/api/merchant-voice/observations/{obs_id}/merge",
             {"duplicate_observation_ids": []}),
            ("POST", "/api/merchant-voice/evidence-candidates",
             {"campaign_id": cid, "finding_type": "pain", "statement": "x",
              "proposed_evidence_role": "supporting", "observations": []}),
            ("GET", f"/api/merchant-voice/evidence-candidates/{candidate_id}", None),
            ("POST", f"/api/merchant-voice/evidence-candidates/{candidate_id}/submit", {}),
            ("POST", f"/api/merchant-voice/findings/{finding_id}/publish", {}),
            ("POST", f"/api/merchant-voice/findings/{finding_id}/suppress", {}),
        ):
            status, _ = self._call(method, path, "tok-view", body)
            self.assertEqual(status, 403, f"{method} {path} should be forbidden for viewer")

    def test_viewer_may_read_published_findings_and_aggregate_analysis(self):
        cid, obs_id, candidate_id, finding_id, pid = self._full_round_trip_to_published_finding()
        status, finding = self._call("GET", f"/api/merchant-voice/findings/{finding_id}", "tok-view")
        self.assertEqual(status, 200)
        self.assertEqual(finding["publication_status"], "published")
        status, analysis_result = self._call("GET", f"/api/merchant-voice/campaigns/{cid}/analysis", "tok-view")
        self.assertEqual(status, 200)
        for categories in analysis_result["segments"].values():
            for entry in categories.values():
                self.assertNotIn("sample_statements", entry)

    def test_viewer_cannot_see_unpublished_finding_via_direct_get(self):
        cid, gid, pid, rid, answer_id = self._bootstrap_participant_and_response()
        obs_id = self._extract_one(rid, answer_id)
        self._call("POST", f"/api/merchant-voice/observations/{obs_id}/approve", "tok-rev")
        status, candidate = self._call("POST", "/api/merchant-voice/evidence-candidates", "tok-res", {
            "campaign_id": cid, "finding_type": "pain", "statement": "Suppliers cancel late payments.",
            "proposed_evidence_role": "supporting",
            "observations": [{"observation_id": obs_id, "role": "supporting"}]})
        candidate_id = candidate["candidate_id"]
        self._call("POST", f"/api/merchant-voice/evidence-candidates/{candidate_id}/submit", "tok-res")
        _status, result = self._call("POST", f"/api/merchant-voice/evidence-candidates/{candidate_id}/approve",
                                     "tok-rev")
        finding_id = result["finding"]["finding_id"]
        status, body = self._call("GET", f"/api/merchant-voice/findings/{finding_id}", "tok-view")
        self.assertEqual(status, 404)

    def test_finding_response_has_no_identity_fields(self):
        cid, obs_id, candidate_id, finding_id, pid = self._full_round_trip_to_published_finding()
        status, finding = self._call("GET", f"/api/merchant-voice/findings/{finding_id}", "tok-res")
        blob = json.dumps(finding)
        self.assertNotIn(pid, blob)

    def test_no_stack_trace_leaked_on_error(self):
        status, body = self._call("PATCH", "/api/merchant-voice/observations/MVO-nope", "tok-res", {})
        self.assertNotIn("Traceback", json.dumps(body))
        self.assertNotIn("File \"", json.dumps(body))

    def test_phase1_2_3_routes_unaffected(self):
        cid, gid, pid, rid, answer_id = self._bootstrap_participant_and_response()
        status, campaigns_list = self._call("GET", "/api/merchant-voice/campaigns", "tok-res")
        self.assertEqual(status, 200)
        self.assertTrue(any(c["campaign_id"] == cid for c in campaigns_list["campaigns"]))
        obs_id = self._extract_one(rid, answer_id)
        status, obs = self._call("GET", f"/api/merchant-voice/observations/{obs_id}", "tok-res")
        self.assertEqual(status, 200)
        self.assertEqual(obs["workflow_status"], "pending_review")


if __name__ == "__main__":
    unittest.main(verbosity=2)
