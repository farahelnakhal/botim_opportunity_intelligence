"""Phase R10 / PR10a — GET /opportunities/{id}/gap-profile. Demo mode so the
committed OPP corpus is visible; mode-gated 404 in normal mode."""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from urllib.request import urlopen

os.environ.setdefault("USER_OPPORTUNITIES_DB_PATH",
                      os.path.join(tempfile.mkdtemp(), "user-opportunities.db"))

UI = Path(__file__).resolve().parents[2]
REPO = UI.parents[0]
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import server  # noqa: E402


def _an_opportunity():
    cards = sorted((REPO / "knowledge-base" / "opportunity-scores").glob("*-scorecard.json"))
    return json.loads(cards[0].read_text(encoding="utf-8"))["opportunity_id"]


class GapProfileRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # demo mode so the committed OPP corpus is visible; saved/restored so it
        # never leaks into sibling test modules in the same process.
        cls._prev_mode = os.environ.get("BOTIM_APP_MODE")
        os.environ["BOTIM_APP_MODE"] = "demo"
        cls.httpd = server.make_server(port=0, root=str(REPO))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()
        cls.opp = _an_opportunity()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        if cls._prev_mode is None:
            os.environ.pop("BOTIM_APP_MODE", None)
        else:
            os.environ["BOTIM_APP_MODE"] = cls._prev_mode

    def _get(self, path):
        try:
            with urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_gap_profile_returned(self):
        status, data = self._get(f"/executive-api/opportunities/{self.opp}/gap-profile")
        self.assertEqual(status, 200)
        self.assertEqual(data["opportunity_id"], self.opp)
        self.assertIn("weak_links", data)
        self.assertIn("evidence_base", data)

    def test_unknown_opportunity_404(self):
        status, _ = self._get("/executive-api/opportunities/OPP-404/gap-profile")
        self.assertEqual(status, 404)

    def test_api_alias_parity(self):
        s1, d1 = self._get(f"/api/opportunities/{self.opp}/gap-profile")
        self.assertEqual(s1, 200)
        self.assertEqual(d1["opportunity_id"], self.opp)


if __name__ == "__main__":
    unittest.main()
