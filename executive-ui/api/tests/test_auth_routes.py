"""Phase R8a — accounts, sessions, opt-in enforcement, and per-user scoping
of user opportunities. Offline; enforcement is toggled via BOTIM_AUTH_MODE
per test (read per request by design)."""

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
os.environ.setdefault("WORKSPACE_DB_PATH", os.path.join(tempfile.mkdtemp(), "workspace.db"))
os.environ["AUTH_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "auth.db")

UI = Path(__file__).resolve().parents[2]
REPO = UI.parents[0]
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import server  # noqa: E402
from api.auth_store import AuthStore, AuthError, verify_password, hash_password  # noqa: E402


class AuthStoreUnit(unittest.TestCase):
    def setUp(self):
        self.store = AuthStore(Path(tempfile.mkdtemp()) / "auth.db")

    def test_password_hashing_roundtrip_and_format(self):
        stored = hash_password("a strong password")
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password("a strong password", stored))
        self.assertFalse(verify_password("wrong password!", stored))
        self.assertNotIn("a strong password", stored)

    def test_register_login_session_logout(self):
        user = self.store.register("A.Person@Example.com", "long-enough-pass")
        self.assertEqual(user["email"], "a.person@example.com")   # normalized
        self.assertNotIn("password_hash", user)                   # never exposed
        got, token = self.store.login("a.person@example.com", "long-enough-pass")
        self.assertEqual(got["id"], user["id"])
        self.assertEqual(self.store.session_user(token)["id"], user["id"])
        self.assertTrue(self.store.logout(token))
        self.assertIsNone(self.store.session_user(token))

    def test_duplicate_email_conflicts_and_weak_password_rejected(self):
        self.store.register("x@example.com", "long-enough-pass")
        with self.assertRaises(AuthError) as cm:
            self.store.register("X@example.com", "another-long-pass")
        self.assertEqual(cm.exception.status, 409)
        with self.assertRaises(AuthError):
            self.store.register("y@example.com", "short")

    def test_login_failure_is_generic_and_rate_limited(self):
        self.store.register("z@example.com", "long-enough-pass")
        for _ in range(8):
            with self.assertRaises(AuthError) as cm:
                self.store.login("z@example.com", "wrong-password-1")
            self.assertEqual(str(cm.exception), "invalid email or password")
        with self.assertRaises(AuthError) as cm:     # 9th attempt: locked out
            self.store.login("z@example.com", "long-enough-pass")
        self.assertEqual(cm.exception.status, 429)

    def test_session_tokens_are_stored_hashed(self):
        import sqlite3
        self.store.register("h@example.com", "long-enough-pass")
        _, token = self.store.login("h@example.com", "long-enough-pass")
        with sqlite3.connect(self.store.db_path) as conn:
            rows = conn.execute("SELECT token_hash FROM sessions").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0][0], token)   # only the hash is persisted
        self.assertNotIn(token, rows[0][0])


class AuthRoutes(unittest.TestCase):
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
        status, data, headers = self._req("POST", "/api/auth/register",
                                          {"email": email, "password": "long-enough-pass"})
        self.assertEqual(status, 201)
        set_cookie = headers.get("Set-Cookie")
        self.assertIn("botim_session=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        token = set_cookie.split("botim_session=")[1].split(";")[0]
        return data["user"], f"botim_session={token}"

    def test_me_reports_mode_off_by_default(self):
        status, data, _ = self._req("GET", "/api/auth/me")
        self.assertEqual(status, 200)
        self.assertEqual(data["auth_mode"], "off")
        self.assertIsNone(data["user"])

    def test_register_login_me_logout_over_http(self):
        user, cookie = self._register("route@example.com")
        _, me, _ = self._req("GET", "/api/auth/me", cookie=cookie)
        self.assertEqual(me["user"]["id"], user["id"])
        _, out, headers = self._req("POST", "/api/auth/logout", {}, cookie=cookie)
        self.assertTrue(out["signed_out"])
        self.assertIn("Max-Age=0", headers.get("Set-Cookie"))
        _, me2, _ = self._req("GET", "/api/auth/me", cookie=cookie)
        self.assertIsNone(me2["user"])

    def test_required_mode_gates_api_but_not_auth_or_static(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/user-opportunities")
        self.assertEqual(cm.exception.code, 401)
        self.assertIn("auth_required", cm.exception.read().decode())
        # /auth/me still answers (the frontend needs it to show sign-in)
        status, data, _ = self._req("GET", "/api/auth/me")
        self.assertEqual(status, 200)
        self.assertEqual(data["auth_mode"], "required")
        # the copilot proxy is gated too
        with self.assertRaises(urllib.error.HTTPError) as cm:
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/copilot-api/chat",
                data=b"{}", method="POST",
                headers={"content-type": "application/json"})
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 401)

    def test_a_typo_mode_fails_closed(self):
        os.environ["BOTIM_AUTH_MODE"] = "requried"   # deliberate typo
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/user-opportunities")
        self.assertEqual(cm.exception.code, 401)

    def test_ownership_scoping_between_two_users(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        _, alice_cookie = self._register("alice@example.com")
        _, bob_cookie = self._register("bob@example.com")
        _, mine, _ = self._req("POST", "/api/user-opportunities",
                               {"title": "Alice's opportunity", "status": "saved"},
                               cookie=alice_cookie)
        self.assertTrue(mine["owner_user_id"].startswith("USER-"))
        # Alice sees it; Bob does not
        _, alice_list, _ = self._req("GET", "/api/user-opportunities", cookie=alice_cookie)
        self.assertIn(mine["id"], [o["id"] for o in alice_list["user_opportunities"]])
        _, bob_list, _ = self._req("GET", "/api/user-opportunities", cookie=bob_cookie)
        self.assertNotIn(mine["id"], [o["id"] for o in bob_list["user_opportunities"]])
        # Bob's direct access is an indistinguishable 404 (read AND write)
        for method, payload in (("GET", None), ("PATCH", {"title": "hijacked"}),
                                ("POST", None)):
            path = f"/api/user-opportunities/{mine['id']}"
            if method == "POST":
                path += "/archive"
                payload = {}
            with self.assertRaises(urllib.error.HTTPError, msg=method) as cm:
                self._req(method, path, payload, cookie=bob_cookie)
            self.assertEqual(cm.exception.code, 404, method)
        # Alice can still read and edit her record
        _, got, _ = self._req("GET", f"/api/user-opportunities/{mine['id']}",
                              cookie=alice_cookie)
        self.assertEqual(got["title"], "Alice's opportunity")

    def test_legacy_unowned_records_stay_shared(self):
        # created while auth is off (pre-R8a data) -> NULL owner
        os.environ["BOTIM_AUTH_MODE"] = "off"
        _, legacy, _ = self._req("POST", "/api/user-opportunities",
                                 {"title": "Legacy shared record"})
        self.assertIsNone(legacy["owner_user_id"])
        os.environ["BOTIM_AUTH_MODE"] = "required"
        _, carol_cookie = self._register("carol@example.com")
        _, listing, _ = self._req("GET", "/api/user-opportunities", cookie=carol_cookie)
        self.assertIn(legacy["id"], [o["id"] for o in listing["user_opportunities"]])
        _, got, _ = self._req("GET", f"/api/user-opportunities/{legacy['id']}",
                              cookie=carol_cookie)
        self.assertEqual(got["title"], "Legacy shared record")

    def test_registration_can_be_closed(self):
        os.environ["AUTH_ALLOW_REGISTRATION"] = "0"
        try:
            with self.assertRaises(urllib.error.HTTPError) as cm:
                self._req("POST", "/api/auth/register",
                          {"email": "late@example.com", "password": "long-enough-pass"})
            self.assertEqual(cm.exception.code, 403)
        finally:
            os.environ.pop("AUTH_ALLOW_REGISTRATION", None)

    def test_error_bodies_never_leak_hashes_or_sql(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._req("POST", "/api/auth/login",
                      {"email": "nobody@example.com", "password": "wrong-pass-123"})
        body = cm.exception.read().decode()
        self.assertEqual(cm.exception.code, 401)
        for leak in ("pbkdf2", "sqlite", "SELECT", "runtime/", "Traceback"):
            self.assertNotIn(leak, body)


if __name__ == "__main__":
    unittest.main()
