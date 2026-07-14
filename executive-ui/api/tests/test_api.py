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
        self.assertEqual(set(m), {"events", "alerts", "summaries"})


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
        cls.httpd = server.make_server(port=0, root=str(REPO))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

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
        # never writes to the knowledge base. No PUT/DELETE at all.
        self.assertFalse(hasattr(server.Handler, "do_PUT"))
        self.assertFalse(hasattr(server.Handler, "do_DELETE"))

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


if __name__ == "__main__":
    unittest.main()
