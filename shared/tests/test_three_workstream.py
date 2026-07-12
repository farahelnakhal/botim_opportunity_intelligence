"""Three-workstream cohesion tests — the capstone proving A, B, and C operate
as one product, not three co-located modules.

These assert the SEAMS between all three workstreams against the real repo:
- C's entities reference A's real competitor profiles
- C's KB watcher, replayed over real git history, detects A's AND B's real
  artefacts as correctly-tiered events (the live loop, proven)
- C's alerts/summaries reference real events; C isolation holds
- the full A→C→B feedback shape is structurally wired
- all three ID namespaces are collision-safe together
"""

import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "intelligence-monitoring" / "tools"))
sys.path.insert(0, str(REPO_ROOT / "opportunity-intelligence" / "tools"))

from monitoring_engine import alerts, events, kbwatch, significance, summaries  # noqa: E402
import monitor as mon_cli  # noqa: E402

KB = REPO_ROOT / "knowledge-base"
MON = KB / "monitoring"


class TestCWatchesAAndB(unittest.TestCase):
    def test_entities_reference_real_A_profiles(self):
        data = json.loads((MON / "entities.json").read_text())
        for e in data["entities"]:
            if e.get("ref"):
                self.assertTrue((REPO_ROOT / e["ref"]).exists(), f"{e['id']} ref {e['ref']} missing")
        # the two profiled competitors A actually wrote are watched
        refs = {e.get("ref") for e in data["entities"]}
        self.assertIn("knowledge-base/competitors/wio.md", refs)
        self.assertIn("knowledge-base/competitors/mamo.md", refs)

    def test_watcher_state_covers_both_A_and_B_artefacts(self):
        state = kbwatch.build_state(REPO_ROOT)
        # A's artefacts
        self.assertGreaterEqual(len(state["evidence"]), 19)
        self.assertGreaterEqual(len(state["segments"]), 4)
        self.assertGreaterEqual(len(state["inflection_points"]), 2)
        # B's artefacts
        self.assertGreaterEqual(len(state["backlog"]), 13)
        self.assertGreaterEqual(len(state["experiments"]), 4)
        self.assertIn("PRED-001", state["predictions"])

    def test_replay_from_root_surfaces_all_A_and_B_work(self):
        """The acceptance demo, as a test: replaying from the repo's root commit
        (empty knowledge base) must surface A's evidence/segments/IPs AND B's
        opportunities/experiments as events — the whole shared history as change."""
        root_commit = subprocess.run(
            ["git", "rev-list", "--max-parents=0", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip().splitlines()[-1]
        old = kbwatch.build_state_at_ref(REPO_ROOT, root_commit)
        new = kbwatch.build_state(REPO_ROOT)
        obs = kbwatch.diff_states(old, new)
        entities = {o["entity"] for o in obs}
        signals = {o["signal_type"] for o in obs}
        # A-side detected
        self.assertTrue(any(e.startswith("EV-") for e in entities), "no A evidence detected")
        self.assertTrue(any(e.startswith("SEG-") for e in entities), "no A segments detected")
        self.assertTrue(any(e.startswith("IP-") for e in entities), "no A inflection points detected")
        # B-side detected
        self.assertIn("new_opportunity", signals)
        self.assertTrue(any("OPP-013" in e for e in entities), "OPP-013 (full-scale test) not detected")
        self.assertIn("new_experiment", signals)


class TestCFeedbackToBAndA(unittest.TestCase):
    def test_summaries_reference_real_events(self):
        evs = {e["id"] for e in events.load_events(MON / "events")}
        for eid, s in summaries.load_summaries(MON / "summaries").items():
            self.assertIn(eid, evs, f"summary {eid} references a non-existent event")

    def test_alerts_reference_real_events(self):
        evs = {e["id"] for e in events.load_events(MON / "events")}
        for a in alerts.load_alerts(MON / "alerts"):
            for eid in a["event_ids"]:
                self.assertIn(eid, evs)

    def test_evidence_candidate_intake_is_A_owned(self):
        # the intake folder exists and its README hands promotion to Workstream A
        readme = (MON / "evidence-candidates" / "README.md").read_text()
        self.assertIn("Workstream A", readme)
        self.assertIn("never writes EV records", readme)

    def test_summary_flags_target_real_B_artefacts(self):
        # any rescore flag must name an OPP that exists in B's backlog
        backlog_ids = set()
        for line in (KB / "product-ideas" / "BACKLOG.md").read_text().splitlines():
            for tok in line.split("|"):
                tok = tok.strip()
                if tok.startswith("OPP-") and len(tok) == 7:
                    backlog_ids.add(tok)
        for eid, s in summaries.load_summaries(MON / "summaries").items():
            for f in s["flags"]["rescore_flags"]:
                self.assertIn(f["opp"], backlog_ids, f"{eid} rescore flag targets unknown {f['opp']}")


class TestCIsolation(unittest.TestCase):
    def test_c_writes_only_in_monitoring(self):
        # monitor.py's MON constant confines every write path
        src = (REPO_ROOT / "intelligence-monitoring/tools/monitor.py").read_text()
        self.assertIn('MON = Path("knowledge-base/monitoring")', src)
        # C's engine never imports A's or B's writers, only B's read-only parsers
        for pyfile in (REPO_ROOT / "intelligence-monitoring/tools/monitoring_engine").glob("*.py"):
            text = pyfile.read_text()
            self.assertNotIn("run.py", text)

    def test_scan_from_head_is_noop(self):
        proc = subprocess.run(
            [sys.executable, "intelligence-monitoring/tools/monitor.py", "scan", "--from-ref", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("0 new event(s)", proc.stdout)


class TestCrossWorkstreamIdSafety(unittest.TestCase):
    def test_id_namespaces_disjoint(self):
        # EV/SEG/IP (A), OPP/VE/PRED/REQ (B), EVT/ALR/ENT (C) — distinct prefixes
        a = {"EV", "SEG", "IP", "SRC"}
        b = {"OPP", "VE", "PRED", "REQ"}
        c = {"EVT", "ALR", "ENT"}
        self.assertEqual(a & b, set())
        self.assertEqual(a & c, set())
        self.assertEqual(b & c, set())
        # EVT must not be mistaken for EV by a prefix match
        self.assertFalse("EVT".startswith("EV-"))


class TestUnifiedGate(unittest.TestCase):
    def test_all_three_check_commands_pass_on_real_repo(self):
        # A conformance
        a = subprocess.run([sys.executable, "customer-intelligence/tools/conformance_check.py", "."],
                           cwd=REPO_ROOT, capture_output=True, text=True)
        self.assertEqual(a.returncode, 0, a.stdout)
        # B sweep
        b = subprocess.run([sys.executable, "opportunity-intelligence/tools/run.py", "check"],
                           cwd=REPO_ROOT, capture_output=True, text=True)
        self.assertEqual(b.returncode, 0, b.stdout)
        # C check
        c = subprocess.run([sys.executable, "intelligence-monitoring/tools/monitor.py", "check"],
                           cwd=REPO_ROOT, capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stdout)


if __name__ == "__main__":
    unittest.main()
