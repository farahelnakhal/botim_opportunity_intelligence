"""API-layer tests for Phase 2 routes: role matrix (viewer fully blocked,
admin-only maintenance/deletion), structured errors, end-to-end wiring."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from app.api import Api  # noqa: E402
from app.config import Config  # noqa: E402
from app.db import connect_identity, connect_mv  # noqa: E402

TOKENS = "admin:tok-admin:admin,researcher:tok-res:researcher,reviewer:tok-rev:reviewer,viewer:tok-view:viewer"


class Phase2ApiTests(unittest.TestCase):
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

    def _call(self, method, path, token, body=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        b = json.dumps(body).encode() if body is not None else b""
        return self.api.handle(method, path, headers, b)

    def _bootstrap_active_campaign(self):
        _, camp = self._call("POST", "/api/merchant-voice/campaigns", "tok-res", {
            "title": "MVC-TEST-API2", "objective": "phase 2 api test", "method": "interview",
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
        return cid, gid, guide["questions"][0]["question_id"]

    def _bootstrap_participant(self, cid):
        status, part = self._call("POST", "/api/merchant-voice/participants", "tok-res", {
            "campaign_id": cid,
            "merchant_identity": {"consent_status": "granted", "permitted_use": "internal_research_only",
                                  "quote_permission": True, "ai_processing_permission": True,
                                  "data_classification": "synthetic"},
            "consent_status": "granted", "permitted_use": "internal_research_only",
            "quote_permission": True, "ai_processing_permission": True, "data_classification": "synthetic"})
        self.assertEqual(status, 201)
        return part["participant_id"]

    # --- viewer boundary ------------------------------------------------

    def test_viewer_blocked_from_participants_endpoints(self):
        cid, gid, qid = self._bootstrap_active_campaign()
        status, _ = self._call("GET", f"/api/merchant-voice/campaigns/{cid}/participants", "tok-view")
        self.assertEqual(status, 403)
        status, _ = self._call("POST", "/api/merchant-voice/participants", "tok-view", {"campaign_id": cid})
        self.assertEqual(status, 403)

    def test_viewer_blocked_from_responses_endpoints(self):
        cid, gid, qid = self._bootstrap_active_campaign()
        status, _ = self._call("GET", f"/api/merchant-voice/campaigns/{cid}/responses", "tok-view")
        self.assertEqual(status, 403)
        status, _ = self._call("POST", "/api/merchant-voice/responses", "tok-view", {"campaign_id": cid})
        self.assertEqual(status, 403)

    def test_viewer_blocked_from_csv_endpoints(self):
        status, _ = self._call("POST", "/api/merchant-voice/imports/csv/preview", "tok-view", {})
        self.assertEqual(status, 403)

    def test_viewer_blocked_from_maintenance_endpoints(self):
        status, _ = self._call("POST", "/api/merchant-voice/maintenance/expire-retention", "tok-view", {})
        self.assertEqual(status, 403)

    def test_viewer_blocked_from_transcript_metadata(self):
        cid, gid, qid = self._bootstrap_active_campaign()
        pid = self._bootstrap_participant(cid)
        status, resp = self._call("POST", "/api/merchant-voice/responses", "tok-res", {
            "campaign_id": cid, "participant_id": pid, "guide_id": gid, "method": "interview",
            "answers": [{"question_id": qid, "answer": "an answer"}]})
        rid = resp["response_id"]
        self._call("POST", f"/api/merchant-voice/responses/{rid}/transcript", "tok-res",
                   {"extension": "txt", "transcript_text": "hello"})
        status, body = self._call("GET", f"/api/merchant-voice/responses/{rid}/transcript-metadata", "tok-view")
        self.assertEqual(status, 403)

    # --- role matrix for privacy-sensitive actions -----------------------

    def test_only_admin_can_request_deletion(self):
        cid, gid, qid = self._bootstrap_active_campaign()
        pid = self._bootstrap_participant(cid)
        status, _ = self._call("POST", f"/api/merchant-voice/participants/{pid}/request-deletion", "tok-res", {})
        self.assertEqual(status, 403)
        status, _ = self._call("POST", f"/api/merchant-voice/participants/{pid}/request-deletion", "tok-admin", {})
        self.assertEqual(status, 200)

    def test_researcher_can_withdraw_consent(self):
        cid, gid, qid = self._bootstrap_active_campaign()
        pid = self._bootstrap_participant(cid)
        status, _ = self._call("POST", f"/api/merchant-voice/participants/{pid}/withdraw-consent", "tok-res", {})
        self.assertEqual(status, 200)

    def test_only_admin_can_run_maintenance(self):
        status, _ = self._call("POST", "/api/merchant-voice/maintenance/expire-retention", "tok-res", {})
        self.assertEqual(status, 403)
        status, _ = self._call("POST", "/api/merchant-voice/maintenance/expire-retention", "tok-admin", {})
        self.assertEqual(status, 200)
        status, _ = self._call("POST", "/api/merchant-voice/maintenance/retry-transcript-deletions", "tok-res", {})
        self.assertEqual(status, 403)
        status, _ = self._call("POST", "/api/merchant-voice/maintenance/retry-transcript-deletions", "tok-admin", {})
        self.assertEqual(status, 200)

    # --- structured errors ------------------------------------------------

    def test_csv_commit_invalid_token_returns_structured_conflict(self):
        cid, gid, qid = self._bootstrap_active_campaign()
        status, body = self._call("POST", "/api/merchant-voice/imports/csv/commit", "tok-res", {
            "campaign_id": cid, "guide_id": gid, "csv_text": "x", "preview_token": "MVX-nope"})
        self.assertEqual(status, 409)
        self.assertEqual(body["error"]["code"], "conflict")

    def test_transcript_ingest_invalid_extension_returns_structured_400(self):
        cid, gid, qid = self._bootstrap_active_campaign()
        pid = self._bootstrap_participant(cid)
        status, resp = self._call("POST", "/api/merchant-voice/responses", "tok-res", {
            "campaign_id": cid, "participant_id": pid, "guide_id": gid, "method": "interview",
            "answers": [{"question_id": qid, "answer": "an answer"}]})
        rid = resp["response_id"]
        status, body = self._call("POST", f"/api/merchant-voice/responses/{rid}/transcript", "tok-res", {
            "extension": "pdf", "transcript_text": "x"})
        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "invalid_request")

    def test_end_to_end_response_and_csv_flow_via_api(self):
        cid, gid, qid = self._bootstrap_active_campaign()
        pid = self._bootstrap_participant(cid)
        status, resp = self._call("POST", "/api/merchant-voice/responses", "tok-res", {
            "campaign_id": cid, "participant_id": pid, "guide_id": gid, "method": "interview",
            "answers": [{"question_id": qid, "answer": "a synthetic answer"}]})
        self.assertEqual(status, 201)
        status, listing = self._call("GET", f"/api/merchant-voice/campaigns/{cid}/responses", "tok-res")
        self.assertEqual(status, 200)
        self.assertEqual(len(listing["responses"]), 1)

        csv_text = f"participant_ref,question_id,answer\n{pid},{qid},Another synthetic answer\n"
        status, prev = self._call("POST", "/api/merchant-voice/imports/csv/preview", "tok-res", {
            "campaign_id": cid, "guide_id": gid, "csv_text": csv_text})
        self.assertEqual(status, 200)
        status, commit = self._call("POST", "/api/merchant-voice/imports/csv/commit", "tok-res", {
            "campaign_id": cid, "guide_id": gid, "csv_text": csv_text, "preview_token": prev["preview_token"]})
        self.assertEqual(status, 200)
        self.assertEqual(len(commit["created_response_ids"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
