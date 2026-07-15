"""Phase 4 — API tests: monitoring overview/summary endpoint (incl. traversal
safety), the web-brief endpoint, and evidence provenance over HTTP. Read-only
against the live repo."""

import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from urllib.request import urlopen

# Phase 5 — this suite verifies the committed demo corpus over HTTP; pin demo
# mode explicitly (normal mode hides the demo portfolio — see test_modes.py).
os.environ.setdefault("BOTIM_APP_MODE", "demo")
# and isolate the runtime user store in a temp path (never the repo tree)
import tempfile
os.environ.setdefault("USER_OPPORTUNITIES_DB_PATH",
                      os.path.join(tempfile.mkdtemp(), "user-opportunities.db"))

UI = Path(__file__).resolve().parents[2]
REPO = UI.parents[0]
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import serialize, server  # noqa: E402


class TestMonitoringPayload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mon = serialize.monitoring_payload(str(REPO))

    def test_summary_state_present_with_honest_fields(self):
        s = self.mon["summary_state"]
        self.assertEqual(s["status"], "active")
        self.assertEqual(s["event_count"], len(self.mon["events"]))
        self.assertIsNone(s["last_checked"])  # no run timestamp is committed — honestly null
        self.assertTrue(s["latest_event_at"])
        self.assertIsInstance(s["open_alert_count"], int)
        self.assertIsInstance(s["unresolved_warning_count"], int)
        self.assertIsInstance(s["monitored_entity_count"], int)

    def test_internal_only_detected_from_adapters(self):
        s = self.mon["summary_state"]
        adapters = {e.get("adapter") for e in self.mon["events"]}
        self.assertEqual(s["internal_only"], adapters <= {"kb-watcher"})
        if s["internal_only"]:
            self.assertIn("internal knowledge base", s["status_note"])

    def test_events_retain_facts_scores_details_status(self):
        self.assertTrue(self.mon["events"])
        for e in self.mon["events"]:
            for key in ("id", "entity", "detected_at", "adapter", "signal_type",
                        "scores", "tier", "status", "title"):
                self.assertIn(key, e, e.get("id"))
            self.assertIn("details", e)  # optional in schema but present in committed data

    def test_summaries_expose_no_filesystem_path(self):
        blob = json.dumps(self.mon["summaries"])
        self.assertNotIn("/home/", blob)
        self.assertNotIn("knowledge-base/", blob)
        for s in self.mon["summaries"]:
            self.assertNotIn("path", s)
            self.assertNotIn("text", s)
            self.assertTrue(s["available"])


class TestMonitoringSummaryFunction(unittest.TestCase):
    def test_success(self):
        out = serialize.monitoring_summary_payload("EVT-2026-W28-013", str(REPO))
        self.assertEqual(out["event_id"], "EVT-2026-W28-013")
        self.assertIn("What changed", out["markdown"])
        self.assertFalse(out["truncated"])

    def test_missing_summary_is_none(self):
        self.assertIsNone(serialize.monitoring_summary_payload("EVT-2026-W28-001", str(REPO)))

    def test_invalid_ids_raise(self):
        for bad in ("../../etc/passwd", "EVT-2026-W28-013/../x", "EVT-9999", "", None,
                    "EVT-2026-W28-013.md", "evt-2026-w28-013"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                serialize.monitoring_summary_payload(bad, str(REPO))


class TestBriefFunction(unittest.TestCase):
    def test_valid_opportunity(self):
        b = serialize.brief_payload("OPP-013", str(REPO))
        self.assertEqual(b["opportunity_id"], "OPP-013")
        self.assertTrue(b["title"])
        self.assertTrue(b["generated_at"])
        self.assertIn("raw_score", b["score_summary"])
        self.assertTrue(b["evidence"])
        self.assertTrue(b["assumptions"])
        self.assertIn("state", b["monitoring"])
        self.assertEqual(b["decision_banner"], "No product or build decision has been made.")

    def test_unknown_opportunity_is_none(self):
        self.assertIsNone(serialize.brief_payload("OPP-999", str(REPO)))

    def test_invalid_id_raises(self):
        for bad in ("OPP-13", "opp-013", "OPP-013; rm -rf", "../x", "", None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                serialize.brief_payload(bad, str(REPO))

    def test_partial_brief_no_recommendation_doc(self):
        b = serialize.brief_payload("OPP-013", str(REPO))
        self.assertIsNone(b["brief_markdown"])  # honest: no committed recommendation doc

    def test_full_brief_with_recommendation_doc(self):
        b = serialize.brief_payload("OPP-001", str(REPO))
        self.assertTrue(b["brief_markdown"])
        self.assertTrue(b["predictions"])

    def test_no_private_fields_or_paths(self):
        for oid in ("OPP-001", "OPP-010", "OPP-013"):
            blob = json.dumps(serialize.brief_payload(oid, str(REPO))).lower()
            for banned in ("/home/", "file://", "participant_id", "transcript",
                           "identity.db", "anthropic_api_key", "system prompt"):
                self.assertNotIn(banned, blob, f"{oid}: {banned}")

    def test_merchant_voice_approved_only_and_honest_when_absent(self):
        b = serialize.brief_payload("OPP-013", str(REPO))
        mv = b["merchant_voice"]
        self.assertIn("available", mv)
        self.assertIsInstance(mv["findings"], list)
        if not mv["available"]:
            self.assertEqual(mv["findings"], [])
            self.assertTrue(mv["note"])
        for f in mv["findings"]:
            self.assertLessEqual(set(f), {
                "finding_id", "approved_statement", "finding_type", "campaign_id", "method",
                "segment_id", "strength_band", "support_count", "contradiction_count",
                "numerator", "denominator", "denominator_definition", "limitations"})

    def test_prediction_links_are_real(self):
        b = serialize.brief_payload("OPP-001", str(REPO))
        ids = {p["id"] for p in b["predictions"]}
        self.assertIn("PRED-001", ids)  # linked via VE-001, which tests OPP-001
        self.assertIn("PRED-002", ids)  # direct OPP-001 link


class TestHttpEndpoints(unittest.TestCase):
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
        try:
            with urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")

    def test_monitoring_summary_success(self):
        status, data = self._get("/executive-api/monitoring/summary/EVT-2026-W28-013")
        self.assertEqual(status, 200)
        self.assertIn("Executive summary", data["markdown"])

    def test_monitoring_summary_missing_404(self):
        status, _ = self._get("/executive-api/monitoring/summary/EVT-2026-W28-002")
        self.assertEqual(status, 404)

    def test_monitoring_summary_invalid_400(self):
        status, _ = self._get("/executive-api/monitoring/summary/EVT-BOGUS")
        self.assertEqual(status, 400)

    def test_monitoring_summary_traversal_never_serves_a_file(self):
        for attempt in ("/executive-api/monitoring/summary/..%2F..%2Fsource-log",
                        "/executive-api/monitoring/summary/../../../etc/passwd",
                        "/executive-api/monitoring/summary/EVT-2026-W28-013%2F..%2Fx",
                        "/executive-api/monitoring/summary/.."):
            status, data = self._get(attempt)
            self.assertIn(status, (400, 404), attempt)
            self.assertNotIn("markdown", data, attempt)

    def test_brief_endpoint_valid(self):
        status, data = self._get("/executive-api/brief/OPP-013")
        self.assertEqual(status, 200)
        self.assertEqual(data["opportunity_id"], "OPP-013")

    def test_brief_endpoint_unknown_404_invalid_400(self):
        self.assertEqual(self._get("/executive-api/brief/OPP-999")[0], 404)
        self.assertEqual(self._get("/executive-api/brief/notanid")[0], 400)

    def test_overview_evidence_carries_provenance(self):
        status, data = self._get("/executive-api/overview")
        self.assertEqual(status, 200)
        e = next(x for x in data["evidence"] if x["ev_id"] == "EV-2026-W28-001")
        self.assertEqual(e["publisher"], "Trustpilot")
        self.assertTrue(e["source_url"].startswith("https://"))
        self.assertIn(e["freshness_status"], ("fresh", "aging", "stale"))


if __name__ == "__main__":
    unittest.main()
