"""Phase P1 (PR-P1b) — GET /brief/{id}/pdf. Verifies the download endpoint
serves a real PDF with the SAME visibility/gating as the JSON /brief route:
committed OPP briefs are demo-gated, UOPP drafts are served in every mode."""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from urllib.request import urlopen, Request

os.environ["USER_OPPORTUNITIES_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "user-opps-pdf.db")

UI = Path(__file__).resolve().parents[2]   # executive-ui/
REPO = UI.parents[0]                        # repo root
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import server, user_store  # noqa: E402

try:
    import reportlab  # noqa: F401
    _HAS_REPORTLAB = True
except ImportError:
    _HAS_REPORTLAB = False

_NEEDS_RL = unittest.skipUnless(
    _HAS_REPORTLAB, "reportlab not installed — PDF download tests need the feature dep")


def _an_opportunity():
    cards = sorted((REPO / "knowledge-base" / "opportunity-scores").glob("*-scorecard.json"))
    return json.loads(cards[0].read_text(encoding="utf-8"))["opportunity_id"]


def _a_user_opportunity():
    store = user_store.UserStore(os.environ["USER_OPPORTUNITIES_DB_PATH"])
    return store.create({"title": "Draft for PDF export test"})["id"]


def _get(port, path):
    req = Request(f"http://127.0.0.1:{port}{path}", method="GET")
    try:
        with urlopen(req) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


class _ServerCase(unittest.TestCase):
    MODE = "demo"

    @classmethod
    def setUpClass(cls):
        cls._prev = os.environ.get("BOTIM_APP_MODE")
        os.environ["BOTIM_APP_MODE"] = cls.MODE
        cls.httpd = server.make_server(port=0, root=str(REPO))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()
        cls.opp = _an_opportunity()
        cls.uopp = _a_user_opportunity()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        if cls._prev is None:
            os.environ.pop("BOTIM_APP_MODE", None)
        else:
            os.environ["BOTIM_APP_MODE"] = cls._prev


@_NEEDS_RL
class PdfRouteDemoMode(_ServerCase):
    MODE = "demo"

    def test_committed_brief_pdf_downloads(self):
        status, headers, body = _get(self.port, f"/executive-api/brief/{self.opp}/pdf")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "application/pdf")
        self.assertIn("attachment", headers.get("Content-Disposition", ""))
        self.assertIn(f"{self.opp}-brief.pdf", headers.get("Content-Disposition", ""))
        self.assertTrue(body.startswith(b"%PDF-"))
        self.assertIn(b"%%EOF", body)

    def test_user_brief_pdf_downloads(self):
        status, headers, body = _get(self.port, f"/executive-api/brief/{self.uopp}/pdf")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "application/pdf")
        self.assertTrue(body.startswith(b"%PDF-"))

    def test_unknown_opportunity_is_404(self):
        status, _h, _b = _get(self.port, "/executive-api/brief/OPP-999/pdf")
        self.assertEqual(status, 404)

    def test_both_aliases_work(self):
        s1, _h, b1 = _get(self.port, f"/api/brief/{self.opp}/pdf")
        self.assertEqual(s1, 200)
        self.assertTrue(b1.startswith(b"%PDF-"))

    def test_guard_failure_is_typed_500_and_logged_loudly(self):
        # If the honesty guard trips on committed (reviewed) brief content, the
        # route must return a machine-distinguishable typed 500 (not a generic
        # crash) AND surface a loud server-side log a human can notice.
        import contextlib
        import io
        from api import report_pdf
        orig = report_pdf.render_brief_pdf

        def boom(*a, **k):
            raise report_pdf.ReportPdfError("brief PDF overclaim rejected: 'ready to launch'")

        report_pdf.render_brief_pdf = boom
        buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(buf):
                status, _h, body = _get(self.port, f"/executive-api/brief/{self.opp}/pdf")
        finally:
            report_pdf.render_brief_pdf = orig
        self.assertEqual(status, 500)
        payload = json.loads(body)
        self.assertEqual(payload["type"], "content_integrity_guard")
        self.assertIn("could not be generated", payload["error"])
        # a loud, human-noticeable log line naming the opportunity + the guard
        logged = buf.getvalue()
        self.assertIn("content_integrity_guard", logged)
        self.assertIn(self.opp, logged)


@_NEEDS_RL
class PdfRouteNormalMode(_ServerCase):
    MODE = "normal"

    def test_committed_brief_pdf_gated_out(self):
        # committed OPP briefs are demo corpus — hidden in normal mode, exactly
        # like the JSON /brief route
        status, _h, _b = _get(self.port, f"/executive-api/brief/{self.opp}/pdf")
        self.assertEqual(status, 404)

    def test_user_brief_pdf_still_served(self):
        # UOPP drafts are real product data, served in every mode
        status, _h, body = _get(self.port, f"/executive-api/brief/{self.uopp}/pdf")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
