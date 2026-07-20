"""Phase C1 — deterministic calculator routes (catalog, compute, save, list,
delete). Threaded server on an ephemeral port; auth off (single-tenant)."""

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
os.environ["CALCULATORS_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "calculators.db")

UI = Path(__file__).resolve().parents[2]
REPO = UI.parents[0]
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import server  # noqa: E402


class CalculatorRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server(port=0, root=str(REPO))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def _url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def _get(self, path):
        try:
            with urlopen(self._url(path)) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def _send(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self._url(path), data=data, method=method,
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    # -- catalog ----------------------------------------------------------- #
    def test_catalog_lists_calculators_with_inputs(self):
        status, data = self._get("/executive-api/calculators")
        self.assertEqual(status, 200)
        ids = [c["id"] for c in data["calculators"]]
        self.assertIn("market_sizing", ids)
        self.assertIn("payments_take", ids)
        ms = next(c for c in data["calculators"] if c["id"] == "market_sizing")
        self.assertTrue(all("unit" in i and "kind" in i for i in ms["inputs"]))

    def test_api_and_executive_api_parity(self):
        s1, d1 = self._get("/executive-api/calculators")
        s2, d2 = self._get("/api/calculators")
        self.assertEqual((s1, d1), (s2, d2))

    # -- compute (stateless) ---------------------------------------------- #
    def test_compute_returns_full_shown_working(self):
        status, data = self._send("POST", "/executive-api/calculators/market_sizing/compute",
                                  {"inputs": {"population": 500000, "annual_value_per_unit": 12000,
                                              "serviceable_fraction": 0.4, "obtainable_share": 0.1}})
        self.assertEqual(status, 200)
        env = data["calculation"]
        self.assertEqual(env["outputs"]["tam"]["value"], 6_000_000_000)
        self.assertTrue(env["steps"])
        self.assertTrue(env["disclaimers"])

    def test_compute_missing_input_400(self):
        status, data = self._send("POST", "/executive-api/calculators/market_sizing/compute",
                                  {"inputs": {"population": 1}})
        self.assertEqual(status, 400)
        self.assertIn("error", data)

    def test_compute_unknown_calculator_404(self):
        status, _ = self._send("POST", "/executive-api/calculators/nope/compute", {"inputs": {}})
        self.assertEqual(status, 404)

    def test_compute_does_not_persist(self):
        self._send("POST", "/executive-api/calculators/breakeven/compute",
                   {"inputs": {"fixed_costs": 1000, "contribution_per_unit": 2}})
        _, data = self._get("/executive-api/calculators/results")
        # nothing saved by a compute-only call
        self.assertEqual(data["saved_calculations"], [])

    # -- save / list / get / delete --------------------------------------- #
    def test_save_then_list_get_delete(self):
        status, data = self._send("POST", "/executive-api/calculators/breakeven",
                                  {"inputs": {"fixed_costs": 100000, "contribution_per_unit": 5},
                                   "label": "SME break-even", "opportunity_ref": "UOPP-0123456789ab"})
        self.assertEqual(status, 201)
        cid = data["saved_calculation"]["id"]
        self.assertTrue(cid.startswith("CALC-"))

        _, listing = self._get("/executive-api/calculators/results")
        self.assertIn(cid, [c["id"] for c in listing["saved_calculations"]])

        _, filtered = self._get("/executive-api/calculators/results?opportunity_ref=UOPP-0123456789ab")
        self.assertEqual(len(filtered["saved_calculations"]), 1)

        status, one = self._get(f"/executive-api/calculators/results/{cid}")
        self.assertEqual(status, 200)
        self.assertEqual(one["saved_calculation"]["envelope"]["outputs"]["breakeven_units"]["value"], 20000)

        status, _ = self._send("DELETE", f"/executive-api/calculators/results/{cid}")
        self.assertEqual(status, 200)
        status, _ = self._get(f"/executive-api/calculators/results/{cid}")
        self.assertEqual(status, 404)

    def test_get_unknown_id_404(self):
        status, _ = self._get("/executive-api/calculators/results/CALC-ffffffffffff")
        self.assertEqual(status, 404)

    def test_bad_id_shape_400(self):
        status, _ = self._get("/executive-api/calculators/results/not-an-id")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
