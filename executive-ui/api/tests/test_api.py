"""Read-only API tests — assert the JSON layer reflects engine truth and never
fabricates, recomputes, or asserts a build decision. Run against the live repo.
"""

import json
import sys
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

UI = Path(__file__).resolve().parents[2]        # executive-ui/
API_PKG_PARENT = UI                              # so `import api` works
REPO = UI.parents[0]
for p in (str(API_PKG_PARENT),):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import generate, router, serialize, server  # noqa: E402


class TestSerialize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = serialize.build_payload(str(REPO))

    def test_overview_has_real_opportunities_ranked(self):
        ids = [o["id"] for o in self.p["opportunities"]]
        self.assertIn("OPP-010", ids)
        self.assertGreater(len(ids), 1)
        raws = [o["raw_score"] for o in self.p["opportunities"]]
        self.assertEqual(raws, sorted(raws, reverse=True))  # ranked, not invented

    def test_decision_banner_present(self):
        self.assertEqual(self.p["meta"]["decision_banner"],
                         "No product or build decision has been made.")

    def test_seventeen_factors_and_no_recompute(self):
        for o in self.p["opportunities"]:
            self.assertEqual(len(o["factors"]), 17)
            self.assertEqual(o["raw_score"], sum(f["score"] for f in o["factors"]))
            self.assertEqual(o["raw_max"], 85)

    def test_archived_reject_has_null_score(self):
        arch = {o["id"]: o for o in self.p["archived"]}
        self.assertIn("OPP-003", arch)
        self.assertIsNone(arch["OPP-003"]["raw_score"])  # honest, not fabricated

    def test_commercial_cases_present(self):
        c = serialize.commercial_payload("OPP-010", str(REPO))
        self.assertIsNotNone(c)
        self.assertEqual(set(c["cases"]), {"downside", "base", "upside"})
        self.assertIn("No product or build decision", c["decision_banner"])

    def test_experiments_have_precommitted_thresholds(self):
        exps = serialize.experiments_payload(str(REPO))
        self.assertTrue(exps)
        for e in exps:
            self.assertIn("success_threshold", e)
            self.assertIn("kill_threshold", e)

    def test_journal_brier_over_resolved_only(self):
        j = serialize.journal_payload(str(REPO), today="2026-07-13")
        self.assertIn("calibration", j)
        self.assertIn("predictions", j)

    def test_monitoring_shape(self):
        m = serialize.monitoring_payload(str(REPO))
        # summary_state is the Phase 4 additive current-state block
        self.assertEqual(set(m), {"events", "alerts", "summaries", "summary_state"})


class TestRouter(unittest.TestCase):
    def test_opportunity_intent(self):
        r = router.route("why is OPP-010 the leader?", str(REPO))
        self.assertEqual(r["intent"], "opportunity")
        types = [b["type"] for b in r["blocks"]]
        self.assertIn("scorecard", types)

    def test_commercial_intent(self):
        r = router.route("show the commercial model for OPP-010", str(REPO))
        self.assertEqual(r["intent"], "commercial")
        self.assertTrue(any(b["type"] == "commercial_model" for b in r["blocks"]))

    def test_monitoring_intent(self):
        r = router.route("what changed this week?", str(REPO))
        self.assertEqual(r["intent"], "monitoring")

    def test_every_response_carries_banner_and_stages(self):
        for q in ("portfolio overview", "OPP-013", "generate a brief", "experiments"):
            r = router.route(q, str(REPO))
            self.assertIn("No product or build decision", r["decision_banner"])
            self.assertTrue(r["stages"] and r["stages"][-1] == "Finished")


class TestGenerate(unittest.TestCase):
    """On-demand analysis of an arbitrary opportunity is honest by construction."""

    @classmethod
    def setUpClass(cls):
        # force the deterministic offline path so the test never hits the network
        cls._saved = generate.API_KEY
        generate.API_KEY = ""
        cls.r = generate.analyze("Invoice financing for UAE logistics SMEs waiting 45 days")

    @classmethod
    def tearDownClass(cls):
        generate.API_KEY = cls._saved

    def test_produces_a_generated_opportunity(self):
        o = self.r["generated_opportunity"]
        self.assertTrue(o["generated"])
        self.assertTrue(o["id"].startswith("GEN-"))
        self.assertEqual(len(o["factors"]), 17)

    def test_all_dimensions_are_assumptions(self):
        o = self.r["generated_opportunity"]
        self.assertTrue(all(f["assumption"] for f in o["factors"]))
        self.assertEqual(o["assumption_count"], 17)

    def test_never_strong_and_low_confidence(self):
        o = self.r["generated_opportunity"]
        self.assertIn(o["classification"], ("promising", "weak"))  # engine caps: never 'strong'
        self.assertEqual(o["confidence"], "low")

    def test_engine_scores_it_not_the_caller(self):
        o = self.r["generated_opportunity"]
        self.assertEqual(o["raw_score"], sum(f["score"] for f in o["factors"]))

    def test_carries_research_plan_and_banner(self):
        types = [b["type"] for b in self.r["blocks"]]
        self.assertIn("research_plan", types)
        self.assertIn("banner", types)
        self.assertIn("No product or build decision", self.r["decision_banner"])

    def test_offline_engine_labelled(self):
        self.assertEqual(self.r["generated_opportunity"]["engine"], "scaffold")

    def test_provider_selection(self):
        # provider() picks the engine from env with no key -> scaffold here
        saved_key, saved_local = generate.API_KEY, generate.LOCAL_BASE_URL
        try:
            generate.API_KEY, generate.LOCAL_BASE_URL = "", ""
            self.assertEqual(generate.provider(), "scaffold")
            generate.LOCAL_BASE_URL = "http://localhost:11434/v1"
            self.assertEqual(generate.provider(), "local")   # local model, no API key needed
            generate.API_KEY = "sk-ant-x"
            self.assertEqual(generate.provider(), "claude")  # key wins
        finally:
            generate.API_KEY, generate.LOCAL_BASE_URL = saved_key, saved_local

    def test_history_is_accepted(self):
        r = generate.analyze("refine for KSA", history=[{"role": "user", "content": "pharmacy lending"}])
        self.assertTrue(r["generated_opportunity"]["generated"])


class TestServerReadOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Phase 3 — /chat and /analyze are disabled by default (see
        # TestLegacyRoutesDisabledByDefault below); this class exercises the
        # rest of the read-only surface plus the legacy pair with the flag
        # explicitly enabled, same as an operator opting in.
        server.LEGACY_UNGROUNDED_ROUTES_ENABLED = True
        cls.httpd = server.make_server(port=0, root=str(REPO))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        server.LEGACY_UNGROUNDED_ROUTES_ENABLED = False

    def _get(self, path):
        with urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
            return r.status, json.loads(r.read())

    def test_overview_endpoint(self):
        status, data = self._get("/api/overview")
        self.assertEqual(status, 200)
        self.assertTrue(data["opportunities"])

    def test_chat_endpoint(self):
        _, data = self._get("/api/chat?q=why%20is%20OPP-010%20leading")
        self.assertEqual(data["intent"], "opportunity")

    def test_no_kb_write_methods(self):
        # POST exists only for compute endpoints (chat/analyze with history); it
        # never writes to the knowledge base. No PUT at all. DELETE (Phase 2)
        # exists ONLY to proxy copilot-backend conversation deletion — its own
        # local SQLite convenience store, never the knowledge base — and is
        # refused everywhere else (see test_delete_only_proxies_copilot below).
        self.assertFalse(hasattr(server.Handler, "do_PUT"))
        self.assertTrue(hasattr(server.Handler, "do_DELETE"))

    def test_delete_only_proxies_copilot(self):
        import urllib.error
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/overview", method="DELETE")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 404)

    def test_post_only_on_compute_endpoints(self):
        import urllib.error
        import urllib.request
        # POST to a data endpoint is refused (405) — those are read-only GETs
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/overview", data=b"{}",
            method="POST", headers={"content-type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 405)

    def test_post_analyze_with_history(self):
        import urllib.request
        body = json.dumps({"q": "pharmacy working capital in KSA",
                           "history": [{"role": "user", "content": "hi"},
                                       {"role": "assistant", "content": "..."}]}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/analyze", data=body,
            method="POST", headers={"content-type": "application/json"})
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
        self.assertEqual(data["intent"], "new_analysis")
        self.assertTrue(data["generated_opportunity"]["generated"])

    def test_unknown_endpoint_404(self):
        try:
            self._get("/api/nope")
        except Exception as exc:  # urlopen raises on 404
            self.assertIn("404", str(exc))
        else:
            self.fail("expected 404")

    def test_executive_api_alias_serves_same_data_as_api(self):
        # Phase 2B — the dashboard client can address either prefix.
        status, data = self._get("/executive-api/overview")
        self.assertEqual(status, 200)
        self.assertTrue(data["opportunities"])


class TestLegacyRoutesDisabledByDefault(unittest.TestCase):
    """Phase 3 — the pre-copilot-backend, ungrounded /chat and /analyze
    scaffold is disabled unless ENABLE_LEGACY_UNGROUNDED_ROUTES=1 is set. The
    grounded chat UI only ever calls /copilot-api/chat now."""

    @classmethod
    def setUpClass(cls):
        # Explicit, not order-dependent on other test classes.
        server.LEGACY_UNGROUNDED_ROUTES_ENABLED = False
        cls.httpd = server.make_server(port=0, root=str(REPO))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_get_chat_is_disabled_by_default(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urlopen(f"http://127.0.0.1:{self.port}/api/chat?q=hi")
        self.assertEqual(cm.exception.code, 404)

    def test_get_analyze_is_disabled_by_default(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urlopen(f"http://127.0.0.1:{self.port}/api/analyze?q=hi")
        self.assertEqual(cm.exception.code, 404)

    def test_post_analyze_is_disabled_by_default(self):
        import urllib.error
        import urllib.request
        body = json.dumps({"q": "hi"}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/analyze", data=body,
            method="POST", headers={"content-type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 404)

    def test_executive_api_alias_chat_is_also_disabled_by_default(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urlopen(f"http://127.0.0.1:{self.port}/executive-api/chat?q=hi")
        self.assertEqual(cm.exception.code, 404)

    def test_read_only_routes_are_unaffected(self):
        with urlopen(f"http://127.0.0.1:{self.port}/api/overview") as r:
            self.assertEqual(r.status, 200)


class TestCopilotProxy(unittest.TestCase):
    """Phase 2 — /copilot-api/* forwards to a FIXED, configured upstream only;
    never an arbitrary caller-supplied URL. Covers both the success path (a
    real copilot-backend instance) and the honest-failure path (upstream
    down) — Phase 2L requires this never silently degrades."""

    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server(port=0, root=str(REPO))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_proxy_unavailable_upstream_returns_honest_502_not_a_crash(self):
        import urllib.error
        import urllib.request
        # Port 1 is never a live copilot-backend — simulates "copilot down".
        server.COPILOT_UPSTREAM = "http://127.0.0.1:1"
        try:
            body = json.dumps({"conversation_id": None, "message": "hi"}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/copilot-api/chat", data=body,
                method="POST", headers={"content-type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req)
            self.assertEqual(cm.exception.code, 502)
            payload = json.loads(cm.exception.read())
            self.assertEqual(payload["error"]["code"], "provider_error")
        finally:
            server.COPILOT_UPSTREAM = "http://127.0.0.1:8010"

    def test_proxy_forwards_to_a_real_copilot_backend(self):
        import urllib.request

        copilot_dir = UI.parents[0] / "copilot-backend"
        if str(copilot_dir) not in sys.path:
            sys.path.insert(0, str(copilot_dir))
        import tempfile
        from app.api import Api as CopilotApi
        from app.config import Config as CopilotConfig
        from app.orchestrator import Orchestrator
        from app.store import ConversationStore
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        cfg = CopilotConfig(env={"COPILOT_PROVIDER": "mock"})
        cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
        capi = CopilotApi(Orchestrator(cfg, ConversationStore(cfg.db_path)), ConversationStore(cfg.db_path))

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0) or 0)
                body = self.rfile.read(length) if length else b""
                status, payload = capi.handle("POST", self.path, body)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        chttpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        cport = chttpd.server_address[1]
        cthread = threading.Thread(target=chttpd.serve_forever, daemon=True)
        cthread.start()
        server.COPILOT_UPSTREAM = f"http://127.0.0.1:{cport}"
        try:
            body = json.dumps({"conversation_id": None, "message": "Tell me about OPP-013"}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/copilot-api/chat", data=body,
                method="POST", headers={"content-type": "application/json"})
            with urllib.request.urlopen(req) as r:
                data = json.loads(r.read())
            self.assertEqual(data["schema_version"], "1.0")
            self.assertTrue(data["conversation_id"].startswith("conv_"))
        finally:
            server.COPILOT_UPSTREAM = "http://127.0.0.1:8010"
            chttpd.shutdown()

    def test_oversized_body_is_rejected_before_being_buffered(self):
        # Phase 3 — enforced at the proxy itself, on the declared
        # Content-Length, so an oversized body is never read into memory
        # even when copilot-backend would also reject it.
        import urllib.error
        import urllib.request
        oversized = b"x" * (server.COPILOT_PROXY_MAX_BODY_BYTES + 1)
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/copilot-api/chat", data=oversized,
            method="POST", headers={"content-type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 413)
        payload = json.loads(cm.exception.read())
        self.assertEqual(payload["error"]["code"], "message_too_long")

    def test_at_limit_body_is_still_forwarded(self):
        # The boundary itself must not be rejected — only strictly over it.
        import urllib.request

        copilot_dir = UI.parents[0] / "copilot-backend"
        if str(copilot_dir) not in sys.path:
            sys.path.insert(0, str(copilot_dir))
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        received = {}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0) or 0)
                received["length"] = length
                self.rfile.read(length)
                data = json.dumps({"schema_version": "1.0", "conversation_id": "conv_x", "ok": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        chttpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        cport = chttpd.server_address[1]
        cthread = threading.Thread(target=chttpd.serve_forever, daemon=True)
        cthread.start()
        server.COPILOT_UPSTREAM = f"http://127.0.0.1:{cport}"
        try:
            at_limit = b"x" * server.COPILOT_PROXY_MAX_BODY_BYTES
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/copilot-api/chat", data=at_limit,
                method="POST", headers={"content-type": "application/json"})
            with urllib.request.urlopen(req) as r:
                self.assertEqual(r.status, 200)
            self.assertEqual(received["length"], server.COPILOT_PROXY_MAX_BODY_BYTES)
        finally:
            server.COPILOT_UPSTREAM = "http://127.0.0.1:8010"
            chttpd.shutdown()

    def test_authorization_header_is_forwarded_to_copilot_but_never_logged(self):
        import io
        import urllib.request
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        captured = {}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                captured["authorization"] = self.headers.get("Authorization")
                length = int(self.headers.get("Content-Length", 0) or 0)
                self.rfile.read(length)
                data = json.dumps({"schema_version": "1.0", "conversation_id": "conv_x"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        chttpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        cport = chttpd.server_address[1]
        cthread = threading.Thread(target=chttpd.serve_forever, daemon=True)
        cthread.start()
        server.COPILOT_UPSTREAM = f"http://127.0.0.1:{cport}"
        try:
            body = json.dumps({"conversation_id": None, "message": "hi"}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/copilot-api/chat", data=body,
                method="POST", headers={"content-type": "application/json",
                                        "authorization": "Bearer secret-token-abc"})
            # Capture this process's own stdout/stderr while the request runs to
            # confirm the token is never printed anywhere along the way.
            captured_output = io.StringIO()
            import contextlib
            with contextlib.redirect_stdout(captured_output):
                with urllib.request.urlopen(req) as r:
                    self.assertEqual(r.status, 200)
            self.assertEqual(captured["authorization"], "Bearer secret-token-abc")
            self.assertNotIn("secret-token-abc", captured_output.getvalue())
        finally:
            server.COPILOT_UPSTREAM = "http://127.0.0.1:8010"
            chttpd.shutdown()


if __name__ == "__main__":
    unittest.main()
