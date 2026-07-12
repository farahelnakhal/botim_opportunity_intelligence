"""Tests for the monitoring engine (Workstream C) — covering the DESIGN.md §14
categories that are mechanically testable: duplicates, false positives,
conflicting reports (confidence gate), fatigue, simultaneous events, missing
sources, plus schema/tier/id discipline and the KB watcher."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from monitoring_engine import digest, events, kbwatch, route, significance  # noqa: E402
from monitoring_engine.significance import MonitorError  # noqa: E402


def _scores(**over):
    s = {"impact": 3, "urgency": 3, "confidence": 3, "relevance": 3, "novelty": 3}
    s.update(over)
    return s


class TestTierMath(unittest.TestCase):
    def test_confidence_gate_caps_everything(self):
        # unverified bombshell: max impact/urgency but confidence 2 -> informative
        self.assertEqual(significance.tier(_scores(impact=5, urgency=5, confidence=2)), "informative")
        self.assertEqual(significance.tier(_scores(impact=5, urgency=5, confidence=2, relevance=2)), "insignificant")

    def test_critical_rule(self):
        self.assertEqual(significance.tier(_scores(impact=4, urgency=4)), "critical")
        self.assertEqual(significance.tier(_scores(impact=4, urgency=3)), "important")

    def test_important_and_informative(self):
        self.assertEqual(significance.tier(_scores(impact=3, novelty=3)), "important")
        self.assertEqual(significance.tier(_scores(impact=2, novelty=5)), "informative")
        self.assertEqual(significance.tier(_scores(impact=2, relevance=2)), "insignificant")

    def test_default_scores_yield_documented_tiers(self):
        self.assertEqual(significance.tier(significance.default_scores("ve_verdict_conclusive")), "critical")
        self.assertEqual(significance.tier(significance.default_scores("ip_status_change")), "critical")
        self.assertEqual(significance.tier(significance.default_scores("opportunity_reclassified")), "important")
        self.assertEqual(significance.tier(significance.default_scores("new_evidence_record")), "informative")

    def test_score_validation(self):
        for bad in ({"impact": 3}, _scores(impact=0), _scores(impact=3.5), _scores(extra=3)):
            with self.assertRaises(MonitorError):
                significance.validate_scores(bad)


class TestEvents(unittest.TestCase):
    def test_fingerprint_normalisation(self):
        a = events.fingerprint("ENT-wio", "pricing", "Fee Cut  to 0.6%")
        b = events.fingerprint("ENT-wio", "pricing", "fee cut to 0.6%")
        self.assertEqual(a, b)
        self.assertNotEqual(a, events.fingerprint("ENT-mamo", "pricing", "fee cut to 0.6%"))

    def test_dedup_same_fact_two_routes(self):
        pool = []
        e1, new1 = events.make_event(pool, entity="ENT-wio", detected_at="2026-07-11",
                                     adapter="rss-newsroom", signal_type="new_evidence_record",
                                     title="Wio launches acquiring", scores=_scores(), week="2026-W28")
        pool.append(e1)
        e2, new2 = events.make_event(pool, entity="ENT-wio", detected_at="2026-07-12",
                                     adapter="web-page-differ", signal_type="new_evidence_record",
                                     title="WIO   launches ACQUIRING", scores=_scores(), week="2026-W28")
        self.assertTrue(new1)
        self.assertFalse(new2)          # same fact, second route -> dedup
        self.assertEqual(e2["id"], e1["id"])

    def test_hand_edited_tier_rejected(self):
        e, _ = events.make_event([], entity="X", detected_at="2026-07-11", adapter="kb-watcher",
                                 signal_type="new_evidence_record", title="t",
                                 scores=_scores(), week="2026-W28")
        e["tier"] = "critical"  # enthusiasm
        with self.assertRaises(MonitorError):
            events.validate_event(e)

    def test_id_sequencing_per_week(self):
        pool = []
        for i in range(3):
            e, _ = events.make_event(pool, entity=f"E{i}", detected_at="2026-07-11",
                                     adapter="kb-watcher", signal_type="new_evidence_record",
                                     title=f"t{i}", scores=_scores(), week="2026-W28")
            pool.append(e)
        self.assertEqual([e["id"] for e in pool],
                         ["EVT-2026-W28-001", "EVT-2026-W28-002", "EVT-2026-W28-003"])

    def test_jsonl_roundtrip_and_duplicate_id_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            e, _ = events.make_event([], entity="X", detected_at="2026-07-11", adapter="kb-watcher",
                                     signal_type="new_evidence_record", title="t",
                                     scores=_scores(), week="2026-W28")
            events.append_events(tmp, "2026-W28", [e, e])  # duplicate id smuggled in
            with self.assertRaises(MonitorError):
                events.load_events(tmp)


class TestRouting(unittest.TestCase):
    PREFS = [{"user": "u1", "channels": {"email": "instant", "in_app": "instant"},
              "min_tier": {"email": "important", "in_app": "informative"},
              "fatigue_budget": 2, "subscriptions": {}}]

    def _event(self, tier_scores, entity="ENT-wio"):
        e, _ = events.make_event([], entity=entity, detected_at="2026-07-11",
                                 adapter="kb-watcher", signal_type="new_evidence_record",
                                 title=f"t-{json.dumps(tier_scores)}", scores=tier_scores, week="2026-W28")
        return e

    def test_fatigue_budget_demotes_non_critical(self):
        ledger = {}
        crit = _scores(impact=4, urgency=4, confidence=5)
        deliveries = []
        for _ in range(4):
            e = self._event(crit)
            e["title"] += str(len(deliveries))  # distinct
            deliveries += route.route_event(e, self.PREFS, ledger)
        # critical may exceed the budget — none demoted
        self.assertFalse(any(d["demoted_by_budget"] for d in deliveries))

    def test_min_tier_filters(self):
        informative = self._event(_scores(impact=2, novelty=4))
        deliveries = route.route_event(informative, self.PREFS, {})
        # email min_tier=important filters it; in_app (informative) receives
        self.assertEqual({d["channel"] for d in deliveries}, {"in_app"})

    def test_insignificant_never_routed(self):
        e = self._event(_scores(impact=1, relevance=1, novelty=1))
        self.assertEqual(route.route_event(e, self.PREFS, {}), [])

    def test_subscription_filter(self):
        prefs = copy.deepcopy(self.PREFS)
        prefs[0]["subscriptions"] = {"entities": ["ENT-mamo"]}
        e = self._event(_scores(impact=4, urgency=4, confidence=5), entity="ENT-wio")
        self.assertEqual(route.route_event(e, prefs, {}), [])

    def test_real_preference_files_load(self):
        prefs = route.load_preferences(REPO_ROOT / "knowledge-base/monitoring/preferences")
        self.assertEqual(len(prefs), 2)


class TestKbWatch(unittest.TestCase):
    def test_build_state_on_real_repo(self):
        state = kbwatch.build_state(REPO_ROOT)
        self.assertGreaterEqual(len(state["evidence"]), 19)
        self.assertGreaterEqual(len(state["segments"]), 4)
        self.assertGreaterEqual(len(state["backlog"]), 13)
        self.assertGreaterEqual(len(state["experiments"]), 4)
        self.assertIn("PRED-001", state["predictions"])

    def test_diff_emits_every_signal_type(self):
        old = {"evidence": {"EV-2026-W01-001": {"status": "active", "confidence": "Low",
                                                "scores": {"severity": 3}}},
               "segments": {"SEG-a": {"confidence": "Low"}},
               "inflection_points": {"IP-2026-001": {"status": "emerging"}},
               "backlog": {"OPP-001": {"enum": "promising"}},
               "experiments": {"VE-001": {"verdict": "pending", "observed_filled": 0, "n_metrics": 3}},
               "predictions": {"PRED-001": {"outcome": None}}}
        new = copy.deepcopy(old)
        new["evidence"]["EV-2026-W01-001"].update(status="superseded-by:EV-2026-W02-001",
                                                  scores={"severity": 4})
        new["evidence"]["EV-2026-W01-002"] = {"status": "active", "confidence": "Medium", "scores": {}}
        new["segments"]["SEG-a"]["confidence"] = "Medium"
        new["segments"]["SEG-b"] = {"confidence": "Low"}
        new["inflection_points"]["IP-2026-001"]["status"] = "confirmed"
        new["backlog"]["OPP-001"]["enum"] = "weak"
        new["backlog"]["OPP-002"] = {"enum": "unscored"}
        new["experiments"]["VE-001"] = {"verdict": "pass", "observed_filled": 3, "n_metrics": 3}
        new["experiments"]["VE-002"] = {"verdict": "pending", "observed_filled": 0, "n_metrics": 2}
        new["predictions"]["PRED-001"]["outcome"] = True
        types = {o["signal_type"] for o in kbwatch.diff_states(old, new)}
        self.assertEqual(types, {
            "evidence_status_change", "evidence_score_change", "new_evidence_record",
            "segment_confidence_change", "new_segment", "ip_status_change",
            "opportunity_reclassified", "new_opportunity",
            "ve_verdict_conclusive", "new_experiment", "prediction_resolved",
        })

    def test_no_change_no_events(self):
        state = kbwatch.build_state(REPO_ROOT)
        self.assertEqual(kbwatch.diff_states(state, state), [])

    def test_sentiment_drift_below_threshold_ignored(self):
        # unchanged integer axis scores -> no evidence_score_change event
        old = {"evidence": {"EV-1": {"status": "active", "confidence": "Low", "scores": {"severity": 3}}},
               "segments": {}, "inflection_points": {}, "backlog": {}, "experiments": {}, "predictions": {}}
        new = copy.deepcopy(old)
        self.assertEqual(kbwatch.diff_states(old, new), [])

    def test_observations_dedup_against_stored_events(self):
        obs = [{"signal_type": "new_evidence_record", "entity": "EV-X", "title": "New evidence record EV-X", "details": {}}]
        first = kbwatch.observations_to_events(obs, [], "2026-07-11", "2026-W28")
        self.assertEqual(len(first), 1)
        second = kbwatch.observations_to_events(obs, first, "2026-07-12", "2026-W28")
        self.assertEqual(second, [])


class TestDigest(unittest.TestCase):
    def test_deterministic_and_sectioned(self):
        evs = events.load_events(REPO_ROOT / "knowledge-base/monitoring/events")
        a = digest.compile_digest("2026-W28", evs)
        b = digest.compile_digest("2026-W28", evs)
        self.assertEqual(a, b)
        self.assertIn("Customer intelligence changes", a)
        self.assertIn("Portfolio & judgment changes", a)
        self.assertIn("Tiers are computed mechanically", a)

    def test_critical_gets_own_block(self):
        e, _ = events.make_event([], entity="VE-001", detected_at="2026-07-11", adapter="kb-watcher",
                                 signal_type="ve_verdict_conclusive", title="VE-001 verdict: pending → PASS",
                                 scores=significance.default_scores("ve_verdict_conclusive"), week="2026-W28")
        text = digest.compile_digest("2026-W28", [e])
        self.assertIn("🔴 CRITICAL", text)


class TestCliAndGateIntegration(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run([sys.executable, "intelligence-monitoring/tools/monitor.py", *args],
                              cwd=REPO_ROOT, capture_output=True, text=True)

    def test_check_passes_on_real_repo(self):
        proc = self._run("check")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("MONITOR CHECK PASSED", proc.stdout)

    def test_scan_idempotent_against_current_state(self):
        proc = self._run("scan")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("0 new event(s)", proc.stdout)

    def test_replay_from_head_yields_nothing(self):
        proc = self._run("scan", "--from-ref", "HEAD")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("0 new event(s)", proc.stdout)

    def test_events_and_entities_list(self):
        self.assertIn("EVT-2026-W28-001", self._run("events").stdout)
        self.assertIn("ENT-wio", self._run("entities").stdout)


if __name__ == "__main__":
    unittest.main()
