"""Phase 5 — application data modes over HTTP: normal hides the demo corpus,
demo serves it labelled, test stays isolated, no silent mode fallback."""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from urllib.request import urlopen

# isolated runtime store; the mode env var is manipulated per test below
os.environ["USER_OPPORTUNITIES_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "u.db")

UI = Path(__file__).resolve().parents[2]
REPO = UI.parents[0]
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import modes, server  # noqa: E402


class TestModeResolution(unittest.TestCase):
    def test_default_is_normal(self):
        self.assertEqual(modes.get_mode({}), "normal")

    def test_explicit_modes(self):
        for m in ("normal", "demo", "test"):
            self.assertEqual(modes.get_mode({"BOTIM_APP_MODE": m}), m)
        self.assertEqual(modes.get_mode({"BOTIM_APP_MODE": " DEMO "}), "demo")

    def test_invalid_value_resolves_to_normal_never_demo(self):
        self.assertEqual(modes.get_mode({"BOTIM_APP_MODE": "production"}), "normal")

    def test_demo_corpus_visibility(self):
        self.assertFalse(modes.demo_corpus_visible("normal"))
        self.assertTrue(modes.demo_corpus_visible("demo"))
        self.assertTrue(modes.demo_corpus_visible("test"))


class TestModesOverHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server(port=0, root=str(REPO))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()
        cls._saved_mode = os.environ.get("BOTIM_APP_MODE")

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        if cls._saved_mode is None:
            os.environ.pop("BOTIM_APP_MODE", None)
        else:
            os.environ["BOTIM_APP_MODE"] = cls._saved_mode

    def _get(self, path):
        try:
            with urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")

    def test_normal_mode_returns_no_demo_portfolio(self):
        os.environ["BOTIM_APP_MODE"] = "normal"
        _, ov = self._get("/executive-api/overview")
        self.assertEqual(ov["meta"]["app_mode"], "normal")
        self.assertEqual(ov["opportunities"], [])
        self.assertEqual(ov["archived"], [])
        self.assertEqual(ov["briefs"], [])
        self.assertEqual(ov["feed"], [])
        self.assertEqual(ov["assumptions"], [])
        # the reference evidence layer stays available to the copilot
        self.assertTrue(ov["evidence"])
        _, j = self._get("/executive-api/journal")
        self.assertEqual(j["predictions"], [])
        _, mon = self._get("/executive-api/monitoring")
        self.assertEqual(mon["events"], [])
        self.assertIn(mon["summary_state"]["status"], ("never-run", "no-events"))
        self.assertIn("user_monitoring", mon)
        # demo detail endpoints are not reachable in normal mode
        self.assertEqual(self._get("/executive-api/brief/OPP-013")[0], 404)
        self.assertEqual(self._get("/executive-api/opportunities/OPP-010")[0], 404)
        self.assertEqual(self._get("/executive-api/commercial/OPP-010")[0], 404)
        self.assertEqual(self._get("/executive-api/monitoring/summary/EVT-2026-W28-013")[0], 404)

    def test_demo_mode_serves_the_labelled_demo_corpus(self):
        os.environ["BOTIM_APP_MODE"] = "demo"
        _, ov = self._get("/executive-api/overview")
        self.assertEqual(ov["meta"]["app_mode"], "demo")
        self.assertTrue(ov["opportunities"])
        self.assertEqual(self._get("/executive-api/brief/OPP-013")[0], 200)

    def test_test_mode_serves_fixtures_and_stays_isolated(self):
        os.environ["BOTIM_APP_MODE"] = "test"
        _, ov = self._get("/executive-api/overview")
        self.assertEqual(ov["meta"]["app_mode"], "test")
        self.assertTrue(ov["opportunities"])
        # isolation: the user store in this process is a temp path, never the
        # default runtime location
        self.assertIn(tempfile.gettempdir(),
                      str(server.get_user_store().db_path))

    def test_invalid_mode_env_resolves_to_normal(self):
        os.environ["BOTIM_APP_MODE"] = "not-a-mode"
        _, ov = self._get("/executive-api/overview")
        self.assertEqual(ov["meta"]["app_mode"], "normal")
        self.assertEqual(ov["opportunities"], [])

    def test_user_opportunities_visible_in_every_mode(self):
        import urllib.request
        os.environ["BOTIM_APP_MODE"] = "normal"
        body = json.dumps({"title": "Mode-independent record", "status": "saved"}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/executive-api/user-opportunities",
            data=body, method="POST", headers={"content-type": "application/json"})
        with urllib.request.urlopen(req) as r:
            created = json.loads(r.read())
        for mode in ("normal", "demo"):
            os.environ["BOTIM_APP_MODE"] = mode
            _, lst = self._get("/executive-api/user-opportunities")
            self.assertIn(created["id"], [o["id"] for o in lst["user_opportunities"]], mode)
            self.assertEqual(self._get(f"/executive-api/brief/{created['id']}")[0], 200, mode)


if __name__ == "__main__":
    unittest.main()
