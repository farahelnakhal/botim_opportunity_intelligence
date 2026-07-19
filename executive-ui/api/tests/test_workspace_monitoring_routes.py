"""Phase R6 (PR6a) — scheduled-monitoring subscription routes over HTTP.

Opt-in is gated on an authenticated account (recipients must be verified
accounts — never a free-text address), owner-scoped like the rest of the
user-opportunity API, and the tokened unsubscribe link works without a
session. Offline; BOTIM_AUTH_MODE toggled per test."""

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
os.environ.setdefault("RESEARCH_DB_PATH", os.path.join(tempfile.mkdtemp(), "research.db"))
os.environ["WORKSPACE_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "workspace.db")
os.environ["AUTH_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "auth.db")

UI = Path(__file__).resolve().parents[2]
REPO = UI.parents[0]
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import server  # noqa: E402


class WorkspaceMonitoringRoutes(unittest.TestCase):
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

    def _make_opp(self, cookie, title="Monitoring opportunity"):
        _, opp, _ = self._req("POST", "/api/user-opportunities",
                             {"title": title, "status": "saved"}, cookie=cookie)
        return opp

    def test_opt_in_requires_a_signed_in_account(self):
        os.environ["BOTIM_AUTH_MODE"] = "off"
        # with auth off there is no session/identity — opt-in must refuse,
        # because a recipient MUST be a verified account (no unverified email)
        _, opp, _ = self._req("POST", "/api/user-opportunities",
                             {"title": "No-auth opp", "status": "saved"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._req("POST",
                      f"/api/user-opportunities/{opp['id']}/workspace/monitoring",
                      {"cadence_hours": 6})
        self.assertEqual(cm.exception.code, 401)

    def test_owner_opts_in_reads_back_and_opts_out(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        alice_user, alice = self._register("r6-alice@example.com")
        opp = self._make_opp(alice)
        base = f"/api/user-opportunities/{opp['id']}/workspace/monitoring"
        # opt in — the recipient email is the account's own address
        status, data, _ = self._req("POST", base, {"cadence_hours": 8}, cookie=alice)
        self.assertEqual(status, 201)
        self.assertTrue(data["unsubscribe_token"])
        sub = data["subscription"]
        self.assertTrue(sub["enabled"])
        self.assertEqual(sub["cadence_hours"], 8)
        self.assertEqual([r["recipient_email"] for r in sub["recipients"]],
                         ["r6-alice@example.com"])
        # the token hash is never exposed
        self.assertNotIn("unsubscribe_token_hash", json.dumps(sub))
        # GET reads it back
        _, got, _ = self._req("GET", base, cookie=alice)
        self.assertEqual(got["subscription"]["owner_user_id"], alice_user["id"])
        # DELETE opts the owner out; the subscription has no recipients left
        _, out, _ = self._req("DELETE", base, cookie=alice)
        self.assertTrue(out["unsubscribed"])
        _, after, _ = self._req("GET", base, cookie=alice)
        self.assertFalse(after["subscription"]["enabled"])

    def test_subscription_is_owner_scoped(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        _, owner = self._register("r6-owner@example.com")
        _, other = self._register("r6-other@example.com")
        opp = self._make_opp(owner, "Owned monitoring opp")
        base = f"/api/user-opportunities/{opp['id']}/workspace/monitoring"
        self._req("POST", base, {"cadence_hours": 6}, cookie=owner)
        # a different user gets the indistinguishable 404 the rest of the
        # user-opportunity API returns for foreign records
        for method in ("GET", "POST", "DELETE"):
            with self.assertRaises(urllib.error.HTTPError, msg=method) as cm:
                self._req(method, base,
                          {} if method == "POST" else None, cookie=other)
            self.assertEqual(cm.exception.code, 404, method)

    def test_tokened_unsubscribe_works_without_a_session(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        _, alice = self._register("r6-unsub@example.com")
        opp = self._make_opp(alice)
        base = f"/api/user-opportunities/{opp['id']}/workspace/monitoring"
        _, data, _ = self._req("POST", base, {"cadence_hours": 6}, cookie=alice)
        token = data["unsubscribe_token"]
        # the link is opened from an email client with NO session cookie,
        # even though auth enforcement is on -> a friendly HTML confirmation
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/monitoring/unsubscribe?token={token}",
            method="GET")
        with urllib.request.urlopen(req) as r:
            self.assertEqual(r.status, 200)
            self.assertIn("text/html", r.headers.get("Content-Type"))
            self.assertIn("Unsubscribed", r.read().decode())
        # the recipient is now disabled
        _, after, _ = self._req("GET", base, cookie=alice)
        self.assertFalse(after["subscription"]["enabled"])

    def test_unknown_unsubscribe_token_is_a_404(self):
        os.environ["BOTIM_AUTH_MODE"] = "off"
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/api/monitoring/unsubscribe?token=bogus")
        self.assertEqual(cm.exception.code, 404)

    def test_cadence_out_of_bounds_is_rejected(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        _, alice = self._register("r6-cadence@example.com")
        opp = self._make_opp(alice)
        base = f"/api/user-opportunities/{opp['id']}/workspace/monitoring"
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._req("POST", base, {"cadence_hours": 1}, cookie=alice)
        self.assertEqual(cm.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
