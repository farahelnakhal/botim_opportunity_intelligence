"""Tests for the alerting completion layer: summaries, alerts, and the
manual-intake adapter. The external-adapter path is exercised entirely in
isolated tmpdirs — the monitoring system must never inject fabricated
intelligence into the real knowledge base, the same evidence discipline it
enforces on the other modules."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from monitoring_engine import adapters, alerts, events, route, significance, summaries  # noqa: E402
from monitoring_engine.significance import MonitorError  # noqa: E402


def _scores(**o):
    s = {"impact": 3, "urgency": 3, "confidence": 3, "relevance": 3, "novelty": 3}
    s.update(o)
    return s


def _event(entity="ENT-wio", signal="pricing_change", title="t", scores=None, adapter="manual-intake", pool=None):
    e, _ = events.make_event(pool or [], entity=entity, detected_at="2026-07-11",
                             adapter=adapter, signal_type=signal, title=title,
                             scores=scores or _scores(), week="2026-W28")
    return e


class TestSummaries(unittest.TestCase):
    def test_skeleton_is_incomplete_until_filled(self):
        text = summaries.skeleton(_event())
        # skeleton has all section headers but placeholder bodies; still structurally valid
        eid, flags = summaries.validate_summary_text(
            text.replace("## EVT", "## EVT-2026-W28-001 —").splitlines()[0] + "\n" + text, "sk")
        self.assertEqual(flags["rescore_flags"], [])

    def test_missing_section_rejected(self):
        text = "## EVT-2026-W28-001 — t\n1. **Executive summary:** x\n```json\n{}\n```"
        with self.assertRaises(MonitorError):
            summaries.validate_summary_text(text, "bad")

    def test_missing_flags_block_rejected(self):
        body = "## EVT-2026-W28-001 — t\n" + "".join(
            f"**{s}:** x\n" for s in summaries.SECTIONS)
        with self.assertRaises(MonitorError):
            summaries.validate_summary_text(body, "bad")

    def test_ve_flag_must_be_redesign_only(self):
        body = "## EVT-2026-W28-001 — t\n" + "".join(f"**{s}:** x\n" for s in summaries.SECTIONS)
        body += '```json\n{"rescore_flags":[],"ve_flags":[{"ve":"VE-001","action":"edit-threshold"}],"req_proposals":[],"evidence_candidates":[]}\n```'
        with self.assertRaises(MonitorError):
            summaries.validate_summary_text(body, "bad")  # thresholds are inviolable

    def test_real_exemplar_summary_validates(self):
        got = summaries.load_summaries(REPO_ROOT / "knowledge-base/monitoring/summaries")
        self.assertIn("EVT-2026-W28-013", got)
        self.assertEqual(got["EVT-2026-W28-013"]["flags"]["rescore_flags"], [])


class TestAlerts(unittest.TestCase):
    PREFS = [{"user": "u", "channels": {"email": "instant", "in_app": "instant"},
              "min_tier": {"email": "important", "in_app": "informative"},
              "fatigue_budget": 3, "subscriptions": {}}]

    def test_only_important_and_critical_alerted(self):
        pool = []
        evs = [_event(title="a", scores=_scores(impact=2, relevance=1, novelty=1), pool=pool),  # insignificant
               _event(title="b", scores=_scores(impact=3, novelty=3), pool=pool)]              # important
        for e in evs:
            pool.append(e)
        new = alerts.create_alerts(evs, self.PREFS, [], "2026-W28", "2026-07-11")
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0]["tier"], "important")

    def test_no_double_alert(self):
        e = _event(title="x", scores=_scores(impact=4, urgency=4, confidence=5))
        first = alerts.create_alerts([e], self.PREFS, [], "2026-W28", "2026-07-11")
        second = alerts.create_alerts([e], self.PREFS, first, "2026-W28", "2026-07-12")
        self.assertEqual(second, [])

    def test_critical_writes_instant_outbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = _event(title="Wio launches acquiring",
                       scores=_scores(impact=5, urgency=5, confidence=5))
            a = alerts.create_alerts([e], self.PREFS, [], "2026-W28", "2026-07-11")[0]
            self.assertEqual(a["tier"], "critical")
            out = alerts.write_outbox(tmp, e, a)
            text = out.read_text()
            self.assertIn("CRITICAL", text)
            self.assertIn("Subject:", text)

    def test_alert_ledger_roundtrip_and_dupe_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = _event(scores=_scores(impact=3, novelty=3))
            a = alerts.create_alerts([e], self.PREFS, [], "2026-W28", "2026-07-11")
            alerts.append_alerts(tmp, "2026-W28", a + a)  # duplicate id
            with self.assertRaises(MonitorError):
                alerts.load_alerts(tmp)

    def test_real_alert_ledger_loads(self):
        led = alerts.load_alerts(REPO_ROOT / "knowledge-base/monitoring/alerts")
        self.assertGreaterEqual(len(led), 7)


class TestManualIntakeAdapter(unittest.TestCase):
    """The external path, fully isolated — no writes to the real KB."""

    def _setup(self, tmp, obs):
        mon = Path(tmp) / "knowledge-base" / "monitoring"
        (mon / "intake").mkdir(parents=True)
        (mon / "intake" / "obs1.json").write_text(json.dumps(obs), encoding="utf-8")
        return mon

    GOOD_OBS = {
        "entity": "ENT-wio", "signal_type": "pricing_change",
        "title": "Wio same-day settlement fee cut to 0.5%",
        "scores": {"impact": 4, "urgency": 3, "confidence": 4, "relevance": 5, "novelty": 4},
        "facts": [{"claim": "fee cut to 0.5%", "quote": "now 0.5%",
                   "source_url": "https://example.test/wio-pricing", "access_label": "direct",
                   "fetched": "2026-07-11"}],
        "evidence_candidate": True,
    }

    def test_intake_creates_event_and_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            mon = self._setup(tmp, self.GOOD_OBS)
            created, stubs = adapters.process_intake(
                mon, [], "2026-W28", "2026-07-11", {"ENT-wio"})
            self.assertEqual(len(created), 1)
            self.assertEqual(created[0]["adapter"], "manual-intake")
            self.assertEqual(created[0]["tier"], "important")  # conf 4, impact 4, urgency 3
            self.assertEqual(len(stubs), 1)
            self.assertIn("Workstream A", stubs[0][1])
            # processed file moved out of the queue (idempotent)
            self.assertTrue((mon / "intake" / "processed" / "obs1.json").exists())
            self.assertFalse((mon / "intake" / "obs1.json").exists())

    def test_provenance_mandatory(self):
        bad = json.loads(json.dumps(self.GOOD_OBS))
        del bad["facts"][0]["source_url"]
        with tempfile.TemporaryDirectory() as tmp:
            mon = self._setup(tmp, bad)
            with self.assertRaises(MonitorError):
                adapters.process_intake(mon, [], "2026-W28", "2026-07-11", {"ENT-wio"})

    def test_unknown_entity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            mon = self._setup(tmp, self.GOOD_OBS)
            with self.assertRaises(MonitorError):
                adapters.process_intake(mon, [], "2026-W28", "2026-07-11", {"ENT-other"})

    def test_external_signal_needs_explicit_scores(self):
        bad = json.loads(json.dumps(self.GOOD_OBS))
        del bad["scores"]
        with tempfile.TemporaryDirectory() as tmp:
            mon = self._setup(tmp, bad)
            with self.assertRaises(MonitorError):
                adapters.process_intake(mon, [], "2026-W28", "2026-07-11", {"ENT-wio"})

    def test_full_external_chain_isolated(self):
        """intake -> event -> summary skeleton -> alert -> outbox, all in tmp."""
        crit = json.loads(json.dumps(self.GOOD_OBS))
        crit["scores"] = {"impact": 5, "urgency": 5, "confidence": 5, "relevance": 5, "novelty": 5}
        crit["title"] = "Wio launches SME merchant acquiring"
        with tempfile.TemporaryDirectory() as tmp:
            mon = self._setup(tmp, crit)
            created, stubs = adapters.process_intake(mon, [], "2026-W28", "2026-07-11", {"ENT-wio"})
            self.assertEqual(created[0]["tier"], "critical")
            prefs = [{"user": "u", "channels": {"email": "instant"},
                      "min_tier": {"email": "important"}, "fatigue_budget": 3, "subscriptions": {}}]
            a = alerts.create_alerts(created, prefs, [], "2026-W28", "2026-07-11")[0]
            instants = [d for d in a["deliveries"] if d["mode"] == "instant"]
            self.assertEqual(len(instants), 1)
            out = alerts.write_outbox(mon / "outbox", created[0], a)
            self.assertIn("Wio launches SME merchant acquiring", out.read_text())


if __name__ == "__main__":
    unittest.main()
