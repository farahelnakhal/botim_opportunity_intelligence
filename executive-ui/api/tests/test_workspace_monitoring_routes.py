"""Phase R6 — scheduled-monitoring subscription routes over HTTP.

Opt-in is gated on a signed-in account (recipients are the account's own
registered email — never a free-text address), owner-scoped like the rest of
the user-opportunity API, and triggers a DOUBLE-OPT-IN confirmation email; no
mail (including the scheduled tick's) goes out until the tokened link is
clicked. The confirm/unsubscribe links work without a session. When auth is
off, opt-in is an honest 403. A MockEmailSender captures the confirmation
email so the flow is observable. Offline; BOTIM_AUTH_MODE toggled per test."""

import json
import os
import re
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
from shared.email import MockEmailSender  # noqa: E402


class WorkspaceMonitoringRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server(port=0, root=str(REPO))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()
        # inject a mock email sender so confirmation mail is captured, not sent
        cls.mail = MockEmailSender()
        cls._orig_sender = server.get_email_sender
        server.get_email_sender = lambda: cls.mail

    @classmethod
    def tearDownClass(cls):
        server.get_email_sender = cls._orig_sender
        cls.httpd.shutdown()

    def setUp(self):
        self.mail.sent.clear()

    def tearDown(self):
        os.environ["BOTIM_AUTH_MODE"] = "off"
        for var in ("MONITORING_TICK_TOKEN", "MONITORING_TICK_MAX_CHATS",
                    "MONITORING_UNSUBSCRIBE_SIGNING_KEY", "MONITORING_PUBLIC_BASE_URL"):
            os.environ.pop(var, None)

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

    def _get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
            return r.status, r.read().decode(), r.headers

    def _register(self, email):
        _, data, headers = self._req("POST", "/api/auth/register",
                                     {"email": email, "password": "long-enough-pass"})
        token = headers.get("Set-Cookie").split("botim_session=")[1].split(";")[0]
        return data["user"], f"botim_session={token}"

    def _make_opp(self, cookie, title="Monitoring opportunity"):
        _, opp, _ = self._req("POST", "/api/user-opportunities",
                             {"title": title, "status": "saved"}, cookie=cookie)
        return opp

    def _confirm_token_from_last_email(self):
        body = self.mail.sent[-1]["text_body"]
        m = re.search(r"/api/monitoring/confirm\?token=(\S+)", body)
        self.assertIsNotNone(m, "confirmation link missing from the email body")
        return m.group(1)

    def _opt_in_confirmed(self, email, cadence_hours=6):
        """Register, create an opportunity, opt in, and click the confirm link
        — the common 'active subscription' setup for the tick tests."""
        _, cookie = self._register(email)
        opp = self._make_opp(cookie)
        base = f"/api/user-opportunities/{opp['id']}/workspace/monitoring"
        self._req("POST", base, {"cadence_hours": cadence_hours}, cookie=cookie)
        self._get(f"/api/monitoring/confirm?token={self._confirm_token_from_last_email()}")
        return opp, cookie

    # -- opt-in gating ------------------------------------------------------- #

    def test_opt_in_when_auth_off_is_an_honest_unavailable(self):
        os.environ["BOTIM_AUTH_MODE"] = "off"
        _, opp, _ = self._req("POST", "/api/user-opportunities",
                             {"title": "No-auth opp", "status": "saved"})
        base = f"/api/user-opportunities/{opp['id']}/workspace/monitoring"
        for method in ("GET", "POST", "DELETE"):
            with self.assertRaises(urllib.error.HTTPError, msg=method) as cm:
                self._req(method, base,
                          {"cadence_hours": 6} if method == "POST" else None)
            self.assertEqual(cm.exception.code, 403, method)
            self.assertIn("requires sign-in to be", cm.exception.read().decode())

    def test_opt_in_without_a_session_under_required_auth_is_401(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        _, alice = self._register("r6-nosession@example.com")
        opp = self._make_opp(alice)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._req("POST",
                      f"/api/user-opportunities/{opp['id']}/workspace/monitoring",
                      {"cadence_hours": 6})
        self.assertEqual(cm.exception.code, 401)

    # -- double opt-in ------------------------------------------------------- #

    def test_opt_in_sends_confirmation_and_confirm_activates(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        alice_user, alice = self._register("r6-alice@example.com")
        opp = self._make_opp(alice)
        base = f"/api/user-opportunities/{opp['id']}/workspace/monitoring"
        status, data, _ = self._req("POST", base, {"cadence_hours": 8}, cookie=alice)
        self.assertEqual(status, 201)
        # confirmation required + emailed to the account's own address; NOT
        # active yet, and NO token is exposed in the API response
        self.assertTrue(data["confirmation"]["required"])
        self.assertTrue(data["confirmation"]["email_sent"])
        self.assertEqual(data["confirmation"]["sent_to"], "r6-alice@example.com")
        self.assertNotIn("token", json.dumps(data))
        self.assertFalse(data["subscription"]["enabled"])
        self.assertTrue(data["subscription"]["recipients"][0]["pending_confirmation"])
        self.assertEqual(self.mail.sent[-1]["to"], "r6-alice@example.com")
        # click the confirm link -> friendly HTML page, subscription active
        token = self._confirm_token_from_last_email()
        s2, html, headers = self._get(f"/api/monitoring/confirm?token={token}")
        self.assertEqual(s2, 200)
        self.assertIn("text/html", headers.get("Content-Type"))
        self.assertIn("Monitoring confirmed", html)
        _, got, _ = self._req("GET", base, cookie=alice)
        self.assertTrue(got["subscription"]["enabled"])
        self.assertTrue(got["subscription"]["recipients"][0]["confirmed"])
        self.assertEqual(got["subscription"]["owner_user_id"], alice_user["id"])

    def test_reopt_in_while_pending_resends_confirmation(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        _, alice = self._register("r6-resend@example.com")
        opp = self._make_opp(alice)
        base = f"/api/user-opportunities/{opp['id']}/workspace/monitoring"
        self._req("POST", base, {"cadence_hours": 6}, cookie=alice)
        self._req("POST", base, {"cadence_hours": 6}, cookie=alice)   # resend
        self.assertEqual(len(self.mail.sent), 2)                       # two confirm emails
        self.assertTrue(self.mail.sent[-1]["subject"].startswith("Confirm monitoring"))

    def test_opt_out_disables_the_recipient(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        opp, cookie = self._opt_in_confirmed("r6-optout@example.com")
        base = f"/api/user-opportunities/{opp['id']}/workspace/monitoring"
        _, out, _ = self._req("DELETE", base, cookie=cookie)
        self.assertTrue(out["unsubscribed"])
        _, after, _ = self._req("GET", base, cookie=cookie)
        self.assertFalse(after["subscription"]["enabled"])

    def test_subscription_is_owner_scoped(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        _, owner = self._register("r6-owner@example.com")
        _, other = self._register("r6-other@example.com")
        opp = self._make_opp(owner, "Owned monitoring opp")
        base = f"/api/user-opportunities/{opp['id']}/workspace/monitoring"
        self._req("POST", base, {"cadence_hours": 6}, cookie=owner)
        for method in ("GET", "POST", "DELETE"):
            with self.assertRaises(urllib.error.HTTPError, msg=method) as cm:
                self._req(method, base,
                          {} if method == "POST" else None, cookie=other)
            self.assertEqual(cm.exception.code, 404, method)

    def test_cadence_out_of_bounds_is_rejected(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        _, alice = self._register("r6-cadence@example.com")
        opp = self._make_opp(alice)
        base = f"/api/user-opportunities/{opp['id']}/workspace/monitoring"
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._req("POST", base, {"cadence_hours": 1}, cookie=alice)
        self.assertEqual(cm.exception.code, 400)

    # -- tokened link endpoints (login-free) -------------------------------- #

    def test_unsubscribe_endpoint_works_without_a_session(self):
        # mint a signed token via the store, then open the link with no cookie
        # even under required-auth mode (the endpoint under test is the link)
        from shared.workspace import sign_unsubscribe_token
        os.environ["BOTIM_AUTH_MODE"] = "required"
        os.environ["MONITORING_UNSUBSCRIBE_SIGNING_KEY"] = "unsub-key"
        ws = server.get_workspace_store()
        r = ws.subscribe("UOPP-ccccccccccc3", "USER-00000000c001",
                         "USER-00000000c001", "unsub@example.com")
        token = sign_unsubscribe_token(r["recipient_id"], "unsub-key")
        s, html, headers = self._get(f"/api/monitoring/unsubscribe?token={token}")
        self.assertEqual(s, 200)
        self.assertIn("text/html", headers.get("Content-Type"))
        self.assertIn("Unsubscribed", html)

    def test_confirm_and_unsubscribe_unknown_tokens_are_404(self):
        for path in ("/api/monitoring/confirm?token=bogus",
                     "/api/monitoring/unsubscribe?token=bogus"):
            with self.assertRaises(urllib.error.HTTPError, msg=path) as cm:
                self._get(path)
            self.assertEqual(cm.exception.code, 404, path)

    # -- the scheduled-monitoring tick -------------------------------------- #

    def _force_due(self, opp_id):
        import sqlite3
        ws = server.get_workspace_store()
        conn = sqlite3.connect(ws.db_path)
        conn.execute("UPDATE workspace_subscriptions SET next_run_at=? "
                     "WHERE opportunity_id=?", ("2000-01-01T00:00:00Z", opp_id))
        conn.commit()
        conn.close()

    def _tick(self, token="tick-secret"):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/monitoring/tick",
            data=b"{}", method="POST",
            headers={"content-type": "application/json",
                     "X-Monitoring-Token": token})
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())

    def test_tick_is_404_when_the_feature_is_not_configured(self):
        os.environ.pop("MONITORING_TICK_TOKEN", None)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._tick()
        self.assertEqual(cm.exception.code, 404)

    def test_tick_rejects_a_wrong_or_missing_token(self):
        os.environ["MONITORING_TICK_TOKEN"] = "tick-secret"
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._tick(token="wrong")
        self.assertEqual(cm.exception.code, 401)

    def test_tick_builds_a_confirmed_due_chat_and_is_idempotent(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        os.environ["MONITORING_TICK_TOKEN"] = "tick-secret"
        opp, _ = self._opt_in_confirmed("r6-tick@example.com")
        self.mail.sent.clear()
        self._force_due(opp["id"])
        status, summary = self._tick()
        self.assertEqual(status, 200)
        self.assertEqual(summary["claimed"], 1)
        # no search provider -> no claims -> first version just establishes the
        # baseline: outcome no_change and NO email fired
        self.assertEqual(summary.get("no_change"), 1)
        self.assertEqual(self.mail.sent, [])
        ws = server.get_workspace_store()
        self.assertEqual(ws.latest(opp["id"])["trigger"], "monitoring")
        _, again = self._tick()          # refire finds nothing due
        self.assertEqual(again["claimed"], 0)

    def test_tick_never_runs_an_unconfirmed_subscription(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        os.environ["MONITORING_TICK_TOKEN"] = "tick-secret"
        _, alice = self._register("r6-tick-pending@example.com")
        opp = self._make_opp(alice)
        base = f"/api/user-opportunities/{opp['id']}/workspace/monitoring"
        self._req("POST", base, {"cadence_hours": 6}, cookie=alice)  # NOT confirmed
        self._force_due(opp["id"])
        _, summary = self._tick()
        self.assertEqual(summary["claimed"], 0)                      # ineligible
        self.assertIsNone(server.get_workspace_store().latest(opp["id"]))

    def test_tick_skips_a_chat_with_a_build_already_running(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        os.environ["MONITORING_TICK_TOKEN"] = "tick-secret"
        opp, _ = self._opt_in_confirmed("r6-tick-race@example.com")
        self._force_due(opp["id"])
        ws = server.get_workspace_store()
        ws.create_version(opp["id"], "manual_refresh")   # a manual run in flight
        _, summary = self._tick()
        self.assertEqual(summary["skipped_in_progress"], 1)
        self.assertIsNone(ws.latest(opp["id"], status="complete"))

    def test_tick_emails_only_on_a_material_change_end_to_end(self):
        # the full pipeline with injected providers: first build establishes the
        # baseline (no email); a build with a NEW claim emails; a repeat of the
        # SAME claim (fresh RCAND- id) is deduped by text and does NOT re-email
        os.environ["BOTIM_AUTH_MODE"] = "required"
        os.environ["MONITORING_TICK_TOKEN"] = "tick-secret"
        os.environ["MONITORING_UNSUBSCRIBE_SIGNING_KEY"] = "unsub-key"
        from shared.research.providers import SearchResult
        from shared.llm.provider import ConversationModel, ModelResponse

        opp, _ = self._opt_in_confirmed("r6-material@example.com")
        self.mail.sent.clear()
        rs = server.get_research_store()
        facts = ["The market grew 12% in 2024.", "A new competitor launched in 2025."]
        pick = {"n": 0}

        class Search:
            name = "mock"
            def search(self, query, max_results=8):
                return [SearchResult.build("mock", url="https://example.com/r",
                                           title="Report")]

        class Stub(ConversationModel):
            model = "stub"
            def generate(self, messages, tools, system_prompt, configuration):
                # pull the source id from THIS run's extraction prompt (robust
                # once several runs exist — never guess via list_runs()[0])
                blob = (system_prompt or "") + " " + " ".join(
                    (m.get("content", "") if isinstance(m, dict) else str(m))
                    for m in (messages or []))
                sid = re.search(r"RSRC-[0-9a-f]{12}", blob).group(0)
                fact = facts[pick["n"]]
                return ModelResponse(content=json.dumps({"claims": [{
                    "claim": fact,
                    "sources": [{"source_id": sid, "supporting_quote": fact}]}]}))

        class Cfg:
            provider = "openai_compatible"; api_key = "x"; model = "stub"
            base_url = "u"; timeout_s = 30

        page = (b"<html><title>Report</title><body>The market grew 12% in 2024. "
                b"A new competitor launched in 2025.</body></html>")
        orig = (server.research_providers.from_env, server.research_runner.execute_run,
                server._ExtractionLLMConfig, server.llm_provider.make_provider)
        server.research_providers.from_env = lambda *a, **k: Search()
        server.research_runner.execute_run = (
            lambda store, run_id, prov, **kw: orig[1](
                store, run_id, prov,
                fetch_fn=lambda url, t: (200, "text/html", page),
                sleep_fn=lambda s: None))
        server._ExtractionLLMConfig = lambda: Cfg()
        server.llm_provider.make_provider = lambda cfg: Stub()
        try:
            # build 1 -> first complete version, baseline established, NO email
            pick["n"] = 0
            self._force_due(opp["id"])
            _, s1 = self._tick()
            self.assertEqual(s1.get("no_change"), 1)
            self.assertEqual(self.mail.sent, [])
            # build 2 -> a genuinely new claim -> material -> emailed
            pick["n"] = 1
            self._force_due(opp["id"])
            _, s2 = self._tick()
            self.assertEqual(s2.get("emailed"), 1)
            self.assertEqual(len(self.mail.sent), 1)
            msg = self.mail.sent[-1]
            self.assertEqual(msg["to"], "r6-material@example.com")
            self.assertIn("A new competitor launched in 2025.", msg["text_body"])
            self.assertIn("PRELIMINARY", msg["text_body"])
            self.assertIn("[pending review — not confirmed]", msg["text_body"])
            # build 3 -> the SAME claim, new id -> deduped -> no re-email
            pick["n"] = 1
            self._force_due(opp["id"])
            _, s3 = self._tick()
            self.assertEqual(s3.get("no_change"), 1)
            self.assertEqual(len(self.mail.sent), 1)   # still exactly one email
            # the emailed unsubscribe link actually works (no session)
            m = re.search(r"/api/monitoring/unsubscribe\?token=(\S+)", msg["text_body"])
            st, html, _ = self._get(f"/api/monitoring/unsubscribe?token={m.group(1)}")
            self.assertEqual(st, 200)
            self.assertIn("Unsubscribed", html)
        finally:
            (server.research_providers.from_env, server.research_runner.execute_run,
             server._ExtractionLLMConfig, server.llm_provider.make_provider) = orig


if __name__ == "__main__":
    unittest.main()
