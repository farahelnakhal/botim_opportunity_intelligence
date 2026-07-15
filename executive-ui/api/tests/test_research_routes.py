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

    def test_no_write_methods_exist_for_research(self):
        import urllib.request
        for method in ("POST", "PUT", "DELETE"):
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/executive-api/research/runs",
                data=b"{}" if method != "DELETE" else None, method=method,
                headers={"content-type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError, msg=method) as cm:
                urllib.request.urlopen(req)
            self.assertIn(cm.exception.code, (404, 405), method)

    def test_error_bodies_never_leak_sql_or_paths(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urlopen(f"http://127.0.0.1:{self.port}/executive-api/research/runs?status=bogus")
        body = cm.exception.read().decode()
        self.assertEqual(cm.exception.code, 400)
        for leak in ("sqlite", "SELECT", "runtime/", "Traceback"):
            self.assertNotIn(leak, body)


if __name__ == "__main__":
    unittest.main()
