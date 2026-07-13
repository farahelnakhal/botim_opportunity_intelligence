"""API-level tests: structured errors, auth wiring, health, CORS (real HTTP),
no-secret-logging, no runtime data committed."""

import http.client
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from app.api import Api  # noqa: E402
from app.config import Config  # noqa: E402
from app.db import connect_mv  # noqa: E402

TOKENS = "admin:tok-admin:admin,researcher:tok-res:researcher,reviewer:tok-rev:reviewer,viewer:tok-view:viewer"


def make_api(tmp_dir):
    config = Config(env={"MV_TOKENS": TOKENS})
    conn = connect_mv(Path(tmp_dir) / "mv.db")
    counter = {"n": 0}

    def now():
        counter["n"] += 1
        return f"2026-01-01T00:00:{counter['n']:02d}Z"

    return Api(config, conn, now), config


class ApiUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.api, self.config = make_api(self.tmp.name)

    def _post(self, path, token, body):
        return self.api.handle("POST", path, {"Authorization": f"Bearer {token}"},
                               json.dumps(body).encode())

    def test_health_requires_no_auth(self):
        status, body = self.api.handle("GET", "/health", {}, b"")
        self.assertEqual(status, 200)
        self.assertTrue(body["synthetic_only"])
        self.assertIn("prototype", body["warning"].lower())

    def test_missing_auth_rejected(self):
        status, body = self.api.handle("GET", "/api/merchant-voice/campaigns", {}, b"")
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "unauthorized")

    def test_malformed_json_structured_error(self):
        status, body = self.api.handle("POST", "/api/merchant-voice/campaigns",
                                       {"Authorization": "Bearer tok-res"}, b"not json")
        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "invalid_request")
        self.assertNotIn("Traceback", json.dumps(body))

    def test_unknown_endpoint_404(self):
        status, body = self.api.handle("GET", "/api/merchant-voice/unknown",
                                       {"Authorization": "Bearer tok-view"}, b"")
        self.assertEqual(status, 404)

    def test_full_campaign_and_guide_flow_via_api(self):
        status, camp = self._post("/api/merchant-voice/campaigns", "tok-res", {
            "title": "MVC-TEST-API", "objective": "API flow test", "method": "survey",
            "data_classification": "synthetic"})
        self.assertEqual(status, 201)
        cid = camp["campaign_id"]

        status, guide = self._post(f"/api/merchant-voice/campaigns/{cid}/guides", "tok-res", {
            "questions": [{"text": "Q1?", "purpose": "problem"}]})
        self.assertEqual(status, 201)
        gid = guide["guide_id"]

        status, approved = self._post(f"/api/merchant-voice/guides/{gid}/approve", "tok-rev", {})
        self.assertEqual(status, 200)
        self.assertEqual(approved["workflow_status"], "approved")

        status, transitioned = self._post(f"/api/merchant-voice/campaigns/{cid}/transition",
                                          "tok-rev", {"workflow_status": "approved"})
        self.assertEqual(status, 200)
        self.assertEqual(transitioned["workflow_status"], "approved")

    def test_forbidden_role_structured_error(self):
        status, body = self._post("/api/merchant-voice/campaigns", "tok-view", {
            "title": "x", "objective": "y", "method": "survey", "data_classification": "synthetic"})
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "forbidden")


class HttpServerTests(unittest.TestCase):
    """Spins up the real server on an OS-assigned port to verify CORS/health
    over actual HTTP, then shuts it down cleanly."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        import server as mv_server
        self.mv_server = mv_server
        config = Config(env={"MV_TOKENS": TOKENS, "MV_HOST": "127.0.0.1", "MV_PORT": "0",
                             "MV_DB_PATH": str(Path(self.tmp.name) / "mv.db"),
                             "MV_IDENTITY_DB_PATH": str(Path(self.tmp.name) / "identity.db")})
        conn = connect_mv(config.db_path)
        from app.db import connect_identity
        connect_identity(config.identity_db_path)
        import time
        api = Api(config, conn, lambda: "2026-01-01T00:00:00Z")
        import threading as th
        self.server = mv_server.ThreadingHTTPServer(
            (config.host, config.port), mv_server.build_handler(api, config, th.BoundedSemaphore(4)))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._shutdown)

    def _shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_cors_preflight_headers(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("OPTIONS", "/api/merchant-voice/campaigns", headers={"Origin": "http://localhost:8000"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 204)
        self.assertEqual(resp.getheader("Access-Control-Allow-Origin"), "http://localhost:8000")
        conn.close()

    def test_health_over_real_http(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        body = json.loads(resp.read())
        self.assertEqual(resp.status, 200)
        self.assertTrue(body["synthetic_only"])
        conn.close()


class RepoHygieneTests(unittest.TestCase):
    def test_no_runtime_data_tracked_by_git(self):
        try:
            out = subprocess.run(["git", "ls-files", "merchant-voice/data"],
                                cwd=REPO, capture_output=True, text=True, timeout=10)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self.skipTest("git not available")
        if out.returncode != 0:
            self.skipTest("not a git repository")
        self.assertEqual(out.stdout.strip(), "", "no files under merchant-voice/data may be committed")

    def test_gitignore_covers_data_and_env(self):
        gi = (BACKEND / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("data/", gi)
        self.assertIn(".env", gi)

    def test_env_example_has_placeholders_only(self):
        content = (BACKEND / ".env.example").read_text(encoding="utf-8")
        self.assertIn("REPLACE_ME", content)
        self.assertNotIn("sk-ant-api", content)  # no realistic-looking live key prefix


if __name__ == "__main__":
    unittest.main(verbosity=2)
