"""Phase R5 / PR4 — analysis-workspace routes over HTTP. Offline: providers
are unset (honest gaps) or injected by patching the module seams."""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from urllib.request import urlopen

os.environ.setdefault("BOTIM_APP_MODE", "test")
os.environ.setdefault("USER_OPPORTUNITIES_DB_PATH",
                      os.path.join(tempfile.mkdtemp(), "user-opportunities.db"))
os.environ.setdefault("RESEARCH_DB_PATH", os.path.join(tempfile.mkdtemp(), "research.db"))
os.environ["WORKSPACE_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "workspace.db")

UI = Path(__file__).resolve().parents[2]
REPO = UI.parents[0]
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import server  # noqa: E402


class WorkspaceRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server(port=0, root=str(REPO))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def _req(self, method, path, payload=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode() if payload is not None else None,
            method=method, headers={"content-type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())

    def _make_opp(self, title="Workspace test opportunity"):
        _, opp = self._req("POST", "/api/user-opportunities", {
            "title": title, "status": "saved",
            "target_segment": "regional SMEs",
            "problem_statement": "slow settlement hurts cash flow"})
        return opp

    def test_get_workspace_before_any_build_is_honest_empty(self):
        opp = self._make_opp()
        status, data = self._req("GET", f"/api/user-opportunities/{opp['id']}/workspace")
        self.assertEqual(status, 200)
        self.assertIsNone(data["workspace"])
        self.assertIn("no analysis workspace exists yet", data["note"])

    def test_refresh_without_providers_builds_a_complete_version_with_gaps(self):
        # no search provider and no LLM key in the test env — the chain still
        # completes, with every skipped step recorded as an honest gap
        opp = self._make_opp()
        status, v = self._req("POST",
                              f"/api/user-opportunities/{opp['id']}/workspace/refresh",
                              {"question": "is this a real pain?"})
        self.assertEqual(status, 201)
        self.assertEqual(v["status"], "complete")
        self.assertEqual(v["trigger"], "first_analysis")
        self.assertTrue(v["is_stale"] is False)
        gaps = " | ".join(v["gaps"])
        self.assertIn("no search provider configured", gaps)
        # preliminary score computed by the REAL engine, capped
        self.assertTrue(v["preliminary_score"]["preliminary"])
        self.assertTrue(v["preliminary_score"]["assumption_capped"])
        self.assertEqual(v["preliminary_score"]["max_classification"], "promising")
        # second refresh is a manual_refresh with an incremented version
        _, v2 = self._req("POST",
                          f"/api/user-opportunities/{opp['id']}/workspace/refresh", {})
        self.assertEqual((v2["trigger"], v2["version"]), ("manual_refresh", 2))
        # GET returns the newest complete version
        _, data = self._req("GET", f"/api/user-opportunities/{opp['id']}/workspace")
        self.assertEqual(data["workspace"]["id"], v2["id"])
        # versions listing, newest first
        _, listing = self._req("GET",
                               f"/api/user-opportunities/{opp['id']}/workspace/versions")
        self.assertEqual([x["version"] for x in listing["versions"]], [2, 1])

    def test_refresh_with_injected_providers_end_to_end(self):
        from shared.research.providers import SearchResult
        from shared.llm.provider import ConversationModel, ModelResponse

        opp = self._make_opp("Injected providers opportunity")

        class Search:
            name = "mock"
            def search(self, query, max_results=8):
                return [SearchResult.build("mock", url="https://example.com/r",
                                           title="Report")]

        rs = server.get_research_store()

        class Stub(ConversationModel):
            model = "stub"
            def generate(self, messages, tools, system_prompt, configuration):
                run = rs.list_runs(opportunity_ref=opp["id"])[0]
                detail = rs.get_run(run["id"], include_children=True)
                # cite the primary (non-duplicate) source — the one carrying
                # the stored excerpt the validator checks quotes against
                sid = next(s["id"] for s in detail["sources"]
                           if not s.get("duplicate_of") and s.get("excerpt"))
                return ModelResponse(content=json.dumps({"claims": [{
                    "claim": "The market grew 12% in 2024.",
                    "sources": [{"source_id": sid,
                                 "supporting_quote": "grew 12% in 2024"}]}]}))

        class Cfg:
            provider = "openai_compatible"; api_key = "x"; model = "stub"
            base_url = "u"; timeout_s = 30

        orig_from_env = server.research_providers.from_env
        orig_execute = server.research_runner.execute_run
        orig_cfg = server._ExtractionLLMConfig
        orig_make = server.llm_provider.make_provider
        server.research_providers.from_env = lambda *a, **k: Search()
        server.research_runner.execute_run = (
            lambda store, run_id, prov, **kw: orig_execute(
                store, run_id, prov,
                fetch_fn=lambda url, t: (200, "text/html",
                                         b"<html><title>Report</title><body>"
                                         b"The market grew 12% in 2024.</body>"),
                sleep_fn=lambda s: None))
        server._ExtractionLLMConfig = lambda: Cfg()
        server.llm_provider.make_provider = lambda cfg: Stub()
        try:
            _, v = self._req("POST",
                             f"/api/user-opportunities/{opp['id']}/workspace/refresh", {})
        finally:
            server.research_providers.from_env = orig_from_env
            server.research_runner.execute_run = orig_execute
            server._ExtractionLLMConfig = orig_cfg
            server.llm_provider.make_provider = orig_make

        self.assertEqual(v["status"], "complete")
        self.assertEqual(len(v["claim_ids"]), 1)
        # the GET view resolves claims to their CURRENT review status
        self.assertEqual(v["claims"][0]["status"], "pending_review")
        self.assertEqual(v["claims"][0]["origin"], "extracted")
        self.assertTrue(v["research_run_id"].startswith("RRUN-"))
        self.assertEqual(v["provenance"]["trigger"], "first_analysis")

    def test_diff_route_compares_the_two_newest_complete_versions(self):
        opp = self._make_opp("Diff opportunity")
        # fewer than two versions -> honest note, no fabricated diff
        _, empty = self._req("GET",
                             f"/api/user-opportunities/{opp['id']}/workspace/diff")
        self.assertIsNone(empty["diff"])
        self.assertIn("fewer than two", empty["note"])
        self._req("POST", f"/api/user-opportunities/{opp['id']}/workspace/refresh", {})
        self._req("POST", f"/api/user-opportunities/{opp['id']}/workspace/refresh", {})
        _, result = self._req("GET",
                              f"/api/user-opportunities/{opp['id']}/workspace/diff")
        diff = result["diff"]
        self.assertEqual(diff["composite_delta"], 0.0)   # same all-assumption card
        self.assertEqual(diff["new_claim_ids"], [])
        self.assertTrue(diff["newer_id"].startswith("AWV-"))
        self.assertNotEqual(diff["newer_id"], diff["older_id"])

    def test_unknown_opportunity_404_and_bad_method_405(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urlopen(f"http://127.0.0.1:{self.port}"
                    "/api/user-opportunities/UOPP-000000000000/workspace")
        self.assertEqual(cm.exception.code, 404)
        opp = self._make_opp("Method check")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/user-opportunities/{opp['id']}/workspace",
            data=b"{}", method="POST", headers={"content-type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 405)


if __name__ == "__main__":
    unittest.main()
