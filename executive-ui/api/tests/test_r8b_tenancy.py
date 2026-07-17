"""Phase R8b — research-run ownership over HTTP and per-user daily quotas.
Offline; BOTIM_AUTH_MODE toggled per test (read per request by design)."""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault("BOTIM_APP_MODE", "test")
os.environ.setdefault("USER_OPPORTUNITIES_DB_PATH",
                      os.path.join(tempfile.mkdtemp(), "user-opportunities.db"))
os.environ["RESEARCH_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "research.db")
os.environ.setdefault("WORKSPACE_DB_PATH", os.path.join(tempfile.mkdtemp(), "workspace.db"))
os.environ["AUTH_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "auth.db")

UI = Path(__file__).resolve().parents[2]
REPO = UI.parents[0]
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import server  # noqa: E402


class R8bTenancy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server(port=0, root=str(REPO))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def tearDown(self):
        os.environ["BOTIM_AUTH_MODE"] = "off"
        os.environ.pop("QUOTA_WORKSPACE_REFRESH_PER_DAY", None)

    def _req(self, method, path, payload=None, cookie=None):
        headers = {"content-type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode() if payload is not None else None,
            method=method, headers=headers)
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read()), r.headers

    def _register(self, email):
        _, data, headers = self._req("POST", "/api/auth/register",
                                     {"email": email, "password": "long-enough-pass"})
        token = headers.get("Set-Cookie").split("botim_session=")[1].split(";")[0]
        return data["user"], f"botim_session={token}"

    def test_research_runs_are_owner_scoped(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        _, alice = self._register("r8b-alice@example.com")
        _, bob = self._register("r8b-bob@example.com")
        _, run, _ = self._req("POST", "/api/research/runs",
                              {"title": "Alice's run", "queries": ["q"]}, cookie=alice)
        self.assertTrue(run["owner_user_id"].startswith("USER-"))
        # listing: visible to Alice, absent for Bob
        _, mine, _ = self._req("GET", "/api/research/runs", cookie=alice)
        self.assertIn(run["id"], [r["id"] for r in mine["runs"]])
        _, theirs, _ = self._req("GET", "/api/research/runs", cookie=bob)
        self.assertNotIn(run["id"], [r["id"] for r in theirs["runs"]])
        # detail + actions: indistinguishable 404 for Bob
        for method, suffix in (("GET", ""), ("POST", "/execute"),
                               ("POST", "/revalidate"), ("POST", "/extract"),
                               ("POST", "/candidates")):
            with self.assertRaises(urllib.error.HTTPError, msg=suffix) as cm:
                self._req(method, f"/api/research/runs/{run['id']}{suffix}",
                          {} if method == "POST" else None, cookie=bob)
            self.assertEqual(cm.exception.code, 404, suffix)
        # Alice still reaches her run detail
        status, detail, _ = self._req("GET", f"/api/research/runs/{run['id']}",
                                      cookie=alice)
        self.assertEqual(status, 200)
        self.assertEqual(detail["title"], "Alice's run")

    def test_candidate_review_follows_the_runs_owner(self):
        os.environ["BOTIM_AUTH_MODE"] = "off"
        # a legacy shared run with a candidate (created without auth)
        from shared.research import ResearchStore
        store = server.get_research_store()
        run = store.create_run({"title": "legacy run"})
        run = store.start_run(run["id"])
        src = store.add_source(run["id"], {"canonical_url": "https://example.com/a"})
        cand = store.add_candidate(run["id"], {"claim": "c", "source_ids": [src["id"]]})
        store.finish_run(run["id"], "complete")
        os.environ["BOTIM_AUTH_MODE"] = "required"
        _, carol = self._register("r8b-carol@example.com")
        # legacy run is shared -> Carol may review its candidate
        status, reviewed, _ = self._req(
            "POST", f"/api/research/candidates/{cand['id']}/review",
            {"action": "approve"}, cookie=carol)
        self.assertEqual(reviewed["status"], "approved")

    def test_owned_run_candidate_review_denied_to_others(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        _, dana = self._register("r8b-dana@example.com")
        _, eve = self._register("r8b-eve@example.com")
        _, run, _ = self._req("POST", "/api/research/runs",
                              {"title": "Dana's run", "queries": ["q"]}, cookie=dana)
        # seed a source + candidate directly (execution needs no provider here)
        store = server.get_research_store()
        started = store.start_run(run["id"])
        src = store.add_source(run["id"], {"canonical_url": "https://example.com/d"})
        cand = store.add_candidate(run["id"], {"claim": "c", "source_ids": [src["id"]]})
        store.finish_run(run["id"], "complete")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._req("POST", f"/api/research/candidates/{cand['id']}/review",
                      {"action": "approve"}, cookie=eve)
        self.assertEqual(cm.exception.code, 404)
        # and the candidate listing hides it from Eve
        _, listing, _ = self._req("GET", "/api/research/candidates", cookie=eve)
        self.assertNotIn(cand["id"], [c["id"] for c in listing["candidates"]])

    def test_daily_quota_yields_429_with_an_honest_message(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        os.environ["QUOTA_WORKSPACE_REFRESH_PER_DAY"] = "2"
        _, frank = self._register("r8b-frank@example.com")
        _, opp, _ = self._req("POST", "/api/user-opportunities",
                              {"title": "Quota test", "status": "saved"}, cookie=frank)
        path = f"/api/user-opportunities/{opp['id']}/workspace/refresh"
        for _ in range(2):
            status, _, _ = self._req("POST", path, {}, cookie=frank)
            self.assertEqual(status, 201)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._req("POST", path, {}, cookie=frank)
        self.assertEqual(cm.exception.code, 429)
        body = cm.exception.read().decode()
        self.assertIn("daily limit reached", body)
        self.assertIn("2 per day", body)

    def test_no_quota_when_auth_is_off(self):
        os.environ["BOTIM_AUTH_MODE"] = "off"
        os.environ["QUOTA_WORKSPACE_REFRESH_PER_DAY"] = "1"
        _, opp, _ = self._req("POST", "/api/user-opportunities",
                              {"title": "No-auth quota test", "status": "saved"})
        path = f"/api/user-opportunities/{opp['id']}/workspace/refresh"
        for _ in range(3):   # no identity -> no quota (single-tenant behavior)
            status, _, _ = self._req("POST", path, {})
            self.assertEqual(status, 201)


if __name__ == "__main__":
    unittest.main()
