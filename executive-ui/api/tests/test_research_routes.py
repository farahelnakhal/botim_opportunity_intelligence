"""Phase R1 — read-only research-run routes. No write routes exist yet
(the runner is Phase R2); these prove honest empty/populated/404 states."""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from urllib.request import urlopen

os.environ.setdefault("BOTIM_APP_MODE", "test")
os.environ.setdefault("USER_OPPORTUNITIES_DB_PATH",
                      os.path.join(tempfile.mkdtemp(), "user-opportunities.db"))
os.environ["RESEARCH_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "research.db")

UI = Path(__file__).resolve().parents[2]
REPO = UI.parents[0]
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import server  # noqa: E402
from shared.research import ResearchStore  # noqa: E402


class ResearchRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server(port=0, root=str(REPO))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()
        cls.store = ResearchStore(os.environ["RESEARCH_DB_PATH"])

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def _get(self, path):
        with urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
            return r.status, json.loads(r.read())

    def test_empty_store_returns_honest_empty_list(self):
        status, data = self._get("/executive-api/research/runs?status=failed")
        self.assertEqual(status, 200)
        self.assertEqual(data, {"runs": []})

    def test_run_lifecycle_visible_over_http(self):
        run = self.store.create_run({"title": "HTTP visibility run"})
        run = self.store.start_run(run["id"])
        q = self.store.add_query(run["id"], {"query_text": "test query"})
        s = self.store.add_source(run["id"], {"canonical_url": "https://example.com/a",
                                              "query_id": q["id"]})
        self.store.add_candidate(run["id"], {"claim": "a sourced claim",
                                             "source_ids": [s["id"]]})
        self.store.finish_run(run["id"], "partial", error="one provider was unavailable")

        _, listing = self._get("/executive-api/research/runs")
        ids = [r["id"] for r in listing["runs"]]
        self.assertIn(run["id"], ids)

        _, detail = self._get(f"/executive-api/research/runs/{run['id']}")
        self.assertEqual(detail["status"], "partial")
        self.assertIn("unavailable", detail["error"])          # honest partial reason
        self.assertEqual(detail["counts"], {"queries": 1, "sources": 1, "candidates": 1})
        self.assertEqual(detail["candidate_evidence"][0]["status"], "pending_review")
        self.assertEqual(detail["sources"][0]["canonical_url"], "https://example.com/a")

    def test_unknown_run_404_and_malformed_id_400(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urlopen(f"http://127.0.0.1:{self.port}/executive-api/research/runs/RRUN-000000000000")
        self.assertEqual(cm.exception.code, 404)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urlopen(f"http://127.0.0.1:{self.port}/executive-api/research/runs/not-a-run-id")
        self.assertEqual(cm.exception.code, 400)

    def test_no_destructive_methods_exist_for_research(self):
        import urllib.request
        for method in ("PUT", "DELETE"):
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/executive-api/research/runs",
                data=b"{}" if method != "DELETE" else None, method=method,
                headers={"content-type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError, msg=method) as cm:
                urllib.request.urlopen(req)
            self.assertIn(cm.exception.code, (404, 405), method)

    # -- Phase R2: create + execute ---------------------------------------- #

    def _post(self, path, payload):
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode(), method="POST",
            headers={"content-type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())

    def test_create_run_with_profile_prefills_queries(self):
        status, run = self._post("/executive-api/research/runs",
                                 {"title": "SME validation run",
                                  "profile": "sme-financial-product",
                                  "context": {"market": "UAE"}})
        self.assertEqual(status, 201)
        self.assertEqual(run["status"], "pending")
        self.assertGreater(run["counts"]["queries"], 5)
        self.assertTrue(all(q["status"] == "pending" for q in run["queries"]))

    def test_create_run_with_arabic_querying_tags_queries(self):
        # R9a multi-language querying over HTTP: queries come back tagged with
        # the language they were issued in, including localized Arabic terms.
        status, run = self._post("/executive-api/research/runs",
                                 {"title": "SME AR/EN run",
                                  "profile": "sme-financial-product",
                                  "context": {"languages": ["en", "ar"]}})
        self.assertEqual(status, 201)
        langs = {q["language"] for q in run["queries"]}
        self.assertEqual(langs, {"en", "ar"})
        self.assertTrue(any("الإمارات" in q["query_text"]
                            for q in run["queries"] if q["language"] == "ar"))

    def test_create_run_with_uncurated_language_is_a_client_error(self):
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/executive-api/research/runs",
            data=json.dumps({"title": "x", "profile": "sme-financial-product",
                             "context": {"languages": ["hi"]}}).encode(),
            method="POST", headers={"content-type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 400)
        self.assertIn("curated", cm.exception.read().decode())

    def test_create_run_with_unknown_profile_is_a_client_error(self):
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/executive-api/research/runs",
            data=json.dumps({"title": "x", "profile": "nope"}).encode(),
            method="POST", headers={"content-type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 400)
        self.assertIn("unknown research profile", cm.exception.read().decode())

    def test_execute_without_configured_provider_fails_honestly(self):
        # RESEARCH_SEARCH_PROVIDER is unset in the test environment — the run
        # must finish 'failed' with a stated reason, never fabricate sources.
        _, run = self._post("/executive-api/research/runs",
                            {"title": "no provider", "queries": ["a query"]})
        _, finished = self._post(f"/executive-api/research/runs/{run['id']}/execute", {})
        self.assertEqual(finished["status"], "failed")
        self.assertIn("no search provider configured", finished["error"])
        self.assertEqual(finished["counts"]["sources"], 0)

    def test_execute_with_injected_provider_end_to_end(self):
        # Patch the provider factory the route uses — the mock provider stays
        # unreachable via environment configuration by design.
        from shared.research import MockSearchProvider
        from shared.research import runner as research_runner
        provider = MockSearchProvider({"a query": [
            {"url": "https://example.com/hit", "title": "Hit", "snippet": "s"}]})
        original_from_env = server.research_providers.from_env
        original_execute = research_runner.execute_run
        server.research_providers.from_env = lambda *a, **k: provider
        server.research_runner.execute_run = (
            lambda store, run_id, prov, **kw: original_execute(
                store, run_id, prov,
                fetch_fn=lambda url, t: (200, "text/html",
                                         b"<html><title>Hit</title><body>page body</body>"),
                sleep_fn=lambda s: None))
        try:
            _, run = self._post("/executive-api/research/runs",
                                {"title": "live-shaped run", "queries": ["a query"]})
            _, finished = self._post(f"/executive-api/research/runs/{run['id']}/execute", {})
        finally:
            server.research_providers.from_env = original_from_env
            server.research_runner.execute_run = original_execute
        self.assertEqual(finished["status"], "complete")
        self.assertEqual(finished["counts"]["sources"], 1)
        self.assertEqual(finished["sources"][0]["canonical_url"], "https://example.com/hit")
        self.assertEqual(finished["sources"][0]["excerpt"], "page body")

    def test_revalidate_route_appends_outcomes_and_returns_summary(self):
        # Phase R4b — seeded run with one source; the live re-fetch will fail
        # in the offline test environment, which is exactly the honest
        # "unreachable" outcome we assert (no network is ever required).
        run = self.store.create_run({"title": "revalidation over http"})
        run = self.store.start_run(run["id"])
        s = self.store.add_source(run["id"], {
            "canonical_url": "http://127.0.0.1:1/never-reachable.example"})
        self.store.finish_run(run["id"], "complete")
        _, detail = self._post(f"/executive-api/research/runs/{run['id']}/revalidate", {})
        self.assertEqual(detail["revalidation_summary"]["checked"], 1)
        self.assertEqual(detail["revalidation_summary"]["unreachable"], 1)
        self.assertEqual(detail["sources"][0]["last_revalidation"]["outcome"], "unreachable")
        self.assertEqual(detail["sources"][0]["id"], s["id"])

    def test_extract_route_without_provider_is_an_honest_400(self):
        # no BOTIM_LLM_API_KEY in the test env -> unconfigured -> honest refusal
        run = self.store.create_run({"title": "extract route"})
        run = self.store.start_run(run["id"])
        self.store.add_source(run["id"], {"canonical_url": "https://example.com/a",
                                          "title": "t", "excerpt": "grounded text here"})
        self.store.finish_run(run["id"], "complete")
        import urllib.error, urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/executive-api/research/runs/{run['id']}/extract",
            data=b"{}", method="POST", headers={"content-type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 400)
        self.assertIn("BOTIM_LLM_API_KEY", cm.exception.read().decode())

    def test_extract_route_end_to_end_with_injected_provider(self):
        import json as _json
        from shared.research import extract as research_extract
        from shared.llm.provider import ConversationModel, ModelResponse

        run = self.store.create_run({"title": "extract e2e"})
        run = self.store.start_run(run["id"])
        s = self.store.add_source(run["id"], {"canonical_url": "https://example.com/x",
                                              "title": "Report", "excerpt": "The market grew 12% in 2024."})
        self.store.finish_run(run["id"], "complete")

        class Stub(ConversationModel):
            model = "stub"
            def generate(self, messages, tools, system_prompt, configuration):
                return ModelResponse(content=_json.dumps({"claims": [{
                    "claim": "The market grew 12% in 2024.",
                    "sources": [{"source_id": s["id"], "supporting_quote": "grew 12% in 2024"}]}]}))

        orig_cfg = server._ExtractionLLMConfig
        orig_make = server.llm_provider.make_provider
        class Cfg:
            provider = "openai_compatible"; api_key = "x"; model = "stub"; base_url = "u"; timeout_s = 30
        server._ExtractionLLMConfig = lambda: Cfg()
        server.llm_provider.make_provider = lambda cfg: Stub()
        try:
            _, detail = self._post(f"/executive-api/research/runs/{run['id']}/extract", {})
        finally:
            server._ExtractionLLMConfig = orig_cfg
            server.llm_provider.make_provider = orig_make
        self.assertEqual(detail["extraction_summary"]["accepted"], 1)
        cand = detail["candidate_evidence"][0]
        self.assertEqual(cand["status"], "pending_review")
        self.assertEqual(cand["origin"], "extracted")

    def test_error_bodies_never_leak_sql_or_paths(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urlopen(f"http://127.0.0.1:{self.port}/executive-api/research/runs?status=bogus")
        body = cm.exception.read().decode()
        self.assertEqual(cm.exception.code, 400)
        for leak in ("sqlite", "SELECT", "runtime/", "Traceback"):
            self.assertNotIn(leak, body)


if __name__ == "__main__":
    unittest.main()
