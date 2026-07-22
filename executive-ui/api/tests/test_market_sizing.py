"""Phase C2 / PR2 — verified-source market-sizing composition + candidate
routes. The builder is deterministic (no model at build time): it corroborates a
run's persisted figures and wires them into the C1 calculator, populating each
sourced input's source_id and its F/A label (H3: corroborated -> Fact,
low-confidence -> Assumption; analyst fractions always Assumption). A candidate
is persisted pending_review; approval never writes committed scores or the KB.

Threaded server on an ephemeral port; auth off (single-tenant); demo corpus
visible under BOTIM_APP_MODE=test."""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from urllib.request import urlopen, Request

os.environ.setdefault("BOTIM_APP_MODE", "test")
os.environ.setdefault("USER_OPPORTUNITIES_DB_PATH",
                      os.path.join(tempfile.mkdtemp(), "user-opportunities.db"))
os.environ["RESEARCH_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "research.db")
os.environ["MARKET_SIZING_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "market-sizing.db")

UI = Path(__file__).resolve().parents[2]
REPO = UI.parents[0]
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import server, market_sizing_builder  # noqa: E402
from shared.research import ResearchStore  # noqa: E402
from shared.market_sizing import MarketSizingStore  # noqa: E402


def make_research_store():
    return ResearchStore(Path(tempfile.mkdtemp()) / "research.db")


def make_sizing_store():
    return MarketSizingStore(Path(tempfile.mkdtemp()) / "m.db")


def seed_run(store):
    run = store.create_run({"title": "sizing run", "profile": "sme-financial-product"})
    return run["id"]


def add_fig(store, run_id, url, quantity, value, tier="T1"):
    src = store.add_source(run_id, {"canonical_url": url, "title": "src"})
    return store.add_figure(run_id, {
        "quantity": quantity, "value": value, "unit": "unit", "tier": tier,
        "supporting_quote": f"the figure is {value}.", "source_id": src["id"]})


# -- builder (deterministic, in-process) ---------------------------------- #
class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.rs = make_research_store()
        self.ss = make_sizing_store()
        self.run_id = seed_run(self.rs)

    def _verified_population(self):
        # two INDEPENDENT T1 registrable domains agreeing within tolerance
        add_fig(self.rs, self.run_id, "https://www.centralbank.ae/a", "population", 500000)
        add_fig(self.rs, self.run_id, "https://www.imf.org/b", "population", 520000)

    def test_corroborated_input_is_fact_with_source_id(self):
        self._verified_population()
        # annual value: also two independent T1 sources
        add_fig(self.rs, self.run_id, "https://www.worldbank.org/c", "spend", 12000)
        add_fig(self.rs, self.run_id, "https://www.centralbank.ae/d", "spend", 12500)
        result = market_sizing_builder.build_market_sizing(
            self.rs, self.ss, opportunity_id="OPP-001", run_id=self.run_id, method="top_down",
            inputs={"population": {"quantity": "population"},
                    "annual_value_per_unit": {"quantity": "spend"},
                    "serviceable_fraction": {"value": 0.4},
                    "obtainable_share": {"value": 0.1}})
        self.assertEqual(result["confidence"], "verified")
        self.assertEqual(result["status"], "pending_review")
        steps_inputs = result["sizing"]["envelope"]["normalized_inputs"]
        self.assertEqual(steps_inputs["population"]["label"], "F")     # H3 corroborated -> Fact
        self.assertTrue(steps_inputs["population"]["source_id"])        # traced to a source
        self.assertEqual(steps_inputs["serviceable_fraction"]["label"], "A")  # analyst fraction

    def test_single_source_is_low_confidence_assumption(self):
        add_fig(self.rs, self.run_id, "https://www.centralbank.ae/a", "population", 500000)  # one source only
        add_fig(self.rs, self.run_id, "https://www.imf.org/b", "spend", 12000)
        add_fig(self.rs, self.run_id, "https://www.worldbank.org/c", "spend", 12400)
        result = market_sizing_builder.build_market_sizing(
            self.rs, self.ss, opportunity_id="OPP-001", run_id=self.run_id, method="top_down",
            inputs={"population": {"quantity": "population"},
                    "annual_value_per_unit": {"quantity": "spend"},
                    "serviceable_fraction": {"value": 0.4},
                    "obtainable_share": {"value": 0.1}})
        self.assertEqual(result["confidence"], "low_confidence")       # not validated
        ni = result["sizing"]["envelope"]["normalized_inputs"]
        self.assertEqual(ni["population"]["label"], "A")               # H3 low-confidence -> Assumption
        self.assertEqual(ni["annual_value_per_unit"]["label"], "F")   # this one corroborated

    def test_low_confidence_and_verified_labels_differ(self):
        # the phase's hard constraint: a low-confidence number must never look
        # identical to a corroborated one inside the calculator's own labels.
        add_fig(self.rs, self.run_id, "https://www.centralbank.ae/a", "population", 500000)  # single
        add_fig(self.rs, self.run_id, "https://www.imf.org/b", "spend", 12000)
        add_fig(self.rs, self.run_id, "https://www.worldbank.org/c", "spend", 12400)  # corroborated
        result = market_sizing_builder.build_market_sizing(
            self.rs, self.ss, opportunity_id="OPP-001", run_id=self.run_id, method="top_down",
            inputs={"population": {"quantity": "population"},
                    "annual_value_per_unit": {"quantity": "spend"},
                    "serviceable_fraction": {"value": 0.4},
                    "obtainable_share": {"value": 0.1}})
        ni = result["sizing"]["envelope"]["normalized_inputs"]
        self.assertNotEqual(ni["population"]["label"], ni["annual_value_per_unit"]["label"])

    def test_missing_figure_refused_422_not_invented(self):
        self._verified_population()
        # no 'spend' figures at all
        with self.assertRaises(market_sizing_builder.MarketSizingBuildError) as cm:
            market_sizing_builder.build_market_sizing(
                self.rs, self.ss, opportunity_id="OPP-001", run_id=self.run_id, method="top_down",
                inputs={"population": {"quantity": "population"},
                        "annual_value_per_unit": {"quantity": "spend"},
                        "serviceable_fraction": {"value": 0.4},
                        "obtainable_share": {"value": 0.1}})
        self.assertEqual(cm.exception.status, 422)
        self.assertIn("spend", str(cm.exception))

    def test_assumption_input_required(self):
        self._verified_population()
        add_fig(self.rs, self.run_id, "https://www.imf.org/c", "spend", 12000)
        add_fig(self.rs, self.run_id, "https://www.worldbank.org/d", "spend", 12400)
        with self.assertRaises(market_sizing_builder.MarketSizingBuildError):
            market_sizing_builder.build_market_sizing(
                self.rs, self.ss, opportunity_id="OPP-001", run_id=self.run_id, method="top_down",
                inputs={"population": {"quantity": "population"},
                        "annual_value_per_unit": {"quantity": "spend"},
                        "obtainable_share": {"value": 0.1}})   # serviceable_fraction missing

    def test_bad_method_rejected(self):
        with self.assertRaises(market_sizing_builder.MarketSizingBuildError):
            market_sizing_builder.build_market_sizing(
                self.rs, self.ss, opportunity_id="OPP-001", run_id=self.run_id,
                method="sideways", inputs={})


# -- HTTP routes ----------------------------------------------------------- #
class MarketSizingRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server(port=0, root=str(REPO))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()
        # seed via the SAME singleton stores the routes use
        cls.rs = server.get_research_store()
        cls.run_id = seed_run(cls.rs)
        add_fig(cls.rs, cls.run_id, "https://www.centralbank.ae/a", "population", 500000)
        add_fig(cls.rs, cls.run_id, "https://www.imf.org/b", "population", 510000)
        add_fig(cls.rs, cls.run_id, "https://www.worldbank.org/c", "spend", 12000)
        add_fig(cls.rs, cls.run_id, "https://www.centralbank.ae/d", "spend", 12300)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def _url(self, p):
        return f"http://127.0.0.1:{self.port}{p}"

    def _get(self, p):
        try:
            with urlopen(self._url(p)) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def _send(self, method, p, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self._url(p), data=data, method=method,
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def _build(self):
        return self._send("POST", "/executive-api/opportunities/OPP-001/market-sizing",
                          {"run_id": self.run_id, "method": "top_down",
                           "inputs": {"population": {"quantity": "population"},
                                      "annual_value_per_unit": {"quantity": "spend"},
                                      "serviceable_fraction": {"value": 0.4},
                                      "obtainable_share": {"value": 0.1}}})

    def test_build_then_get_then_review_once(self):
        status, data = self._build()
        self.assertEqual(status, 201)
        msz = data["market_sizing"]
        self.assertTrue(msz["id"].startswith("MSZ-"))
        self.assertEqual(msz["status"], "pending_review")
        self.assertEqual(msz["confidence"], "verified")

        status, got = self._get(f"/executive-api/market-sizing/{msz['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(got["market_sizing"]["id"], msz["id"])

        status, listing = self._get("/executive-api/market-sizing?opportunity_id=OPP-001")
        self.assertIn(msz["id"], [m["id"] for m in listing["market_sizings"]])

        status, reviewed = self._send(
            "POST", f"/executive-api/market-sizing/{msz['id']}/review", {"action": "approve"})
        self.assertEqual(status, 200)
        self.assertEqual(reviewed["market_sizing"]["status"], "approved")

        # a second review is refused (already terminal)
        status, _ = self._send(
            "POST", f"/executive-api/market-sizing/{msz['id']}/review", {"action": "reject"})
        self.assertEqual(status, 409)

    def test_build_missing_run_400(self):
        status, _ = self._send("POST", "/executive-api/opportunities/OPP-001/market-sizing",
                               {"method": "top_down", "inputs": {}})
        self.assertEqual(status, 400)

    def test_build_missing_figure_422(self):
        run2 = seed_run(self.rs)   # empty run — no figures
        status, data = self._send(
            "POST", "/executive-api/opportunities/OPP-001/market-sizing",
            {"run_id": run2, "method": "top_down",
             "inputs": {"population": {"quantity": "population"},
                        "annual_value_per_unit": {"quantity": "spend"},
                        "serviceable_fraction": {"value": 0.4},
                        "obtainable_share": {"value": 0.1}}})
        self.assertEqual(status, 422)

    def test_review_unknown_id_404(self):
        status, _ = self._send("POST", "/executive-api/market-sizing/MSZ-ffffffffffff/review",
                               {"action": "approve"})
        self.assertEqual(status, 404)

    def test_get_unknown_id_404(self):
        status, _ = self._get("/executive-api/market-sizing/MSZ-ffffffffffff")
        self.assertEqual(status, 404)

    def test_api_and_executive_api_parity_on_list(self):
        s1, _ = self._get("/executive-api/market-sizing")
        s2, _ = self._get("/api/market-sizing")
        self.assertEqual(s1, s2)


if __name__ == "__main__":
    unittest.main()
