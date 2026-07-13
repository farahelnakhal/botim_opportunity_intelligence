"""Tests for the Assumption/Evidence-Gap Tracker and Executive Decision Brief.

Live read-only tests run against the real repo (OPP-013) and never write.
Synthetic tests use throwaway temp repos. No source evidence/scorecard is
modified; no email is sent (no send capability exists).
"""

import contextlib
import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from impact import (apply as apply_mod, brief, cli, gaps, genmeta, paths,  # noqa: E402
                    proposal, tracker)
from impact.tests.test_impact import make_scorecard, make_descriptor, build_repo, write_proposal  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
NOW = "2026-07-13T00:00:00Z"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class LiveReadOnly(unittest.TestCase):
    """OPP-013 against the real repository — read-only."""

    def setUp(self):
        paths.set_repo_root(REPO)

    def _view(self):
        return brief.build_view("OPP-013", NOW)

    def test_scores_match_engine(self):
        sys.path.insert(0, str(REPO / "opportunity-intelligence" / "tools"))
        from opportunity_engine import scoring
        card = json.loads((paths.KB / "opportunity-scores" / "opp-013-scorecard.json").read_text())
        ev = scoring.evaluate(card)
        raw = sum(e["score"] for e in ev["scores"].values())
        v = self._view()["score"]
        self.assertEqual(v["raw"], raw)
        self.assertEqual(v["raw_score"], f"{raw}/85")
        self.assertEqual(v["composite_score"], ev["composite_indicative"])
        self.assertEqual(v["assumption_count"], ev["assumption_count"])
        self.assertEqual(v["capped"], ev["assumption_capped"])
        self.assertEqual((raw, v["composite_score"], v["assumption_count"]), (55, 3.2, 8))

    def test_unresolved_matches_scorecard(self):
        v = self._view()
        self.assertEqual(v["assumptions"]["unresolved"], v["score"]["assumption_count"])

    def test_card_only_not_recommended(self):
        v = self._view()
        rec = v["recommended_action"]["text"].lower()
        self.assertIn("before any product build decision", rec)
        self.assertNotIn("build the", rec)
        self.assertIn("validation", v["decision_requested"]["text"].lower())
        self.assertEqual(v["decision_requested"]["no_build_decision"],
                         "No product or build decision has been made.")

    def test_demand_pricing_switching_unproven(self):
        v = self._view()
        self.assertTrue(v["promising_unvalidated"])
        md = brief.render_markdown(v)
        for bad in ("product validated", "opportunity validated", "product selected"):
            self.assertNotIn(bad, md.lower())
        self.assertIn("No product or build decision has been made.", md)

    def test_ev016_ev018_not_primary(self):
        v = self._view()
        self.assertNotIn("EV-2026-W28-018", v["supporting_primary"])
        self.assertNotIn("EV-2026-W28-016", v["supporting_primary"])
        # EV-018 is cited but weak -> appears only as a lead
        self.assertIn("EV-2026-W28-018", v["supporting_leads"])

    def test_weak_evidence_no_status_change(self):
        # botim_distribution_advantage is an assumption citing EV-018 (low) -> still untested
        model = tracker.build("OPP-013", NOW)
        item = next(a for a in model["assumptions"] if a["factor"] == "botim_distribution_advantage")
        self.assertEqual(item["status"], "untested")
        self.assertIn("EV-2026-W28-018", item["supporting_ev"])
        self.assertEqual(item["evidence_confidence"]["derived"], "low")

    def test_json_md_parity(self):
        v = self._view()
        j = brief.render_json(v)
        md = brief.render_markdown(v)
        self.assertEqual(j["score"]["raw_score"], "55/85")
        self.assertIn("55/85", md)
        self.assertEqual(j["assumptions"]["unresolved"], 8)
        self.assertIn("Unresolved assumptions: **8**", md)
        self.assertEqual(j["recommended_action"]["ve"], "VE-004")
        self.assertIn("VE-004", md)
        self.assertIn(j["decision_requested"]["text"], md)
        for ev in j["evidence"]["supporting_leads"]:
            self.assertIn(ev, md)

    def test_regenerate_identical(self):
        a = tracker.build("OPP-013", NOW)
        b = tracker.build("OPP-013", NOW)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_gaps_portfolio_runs_and_top5(self):
        rep = gaps.build_portfolio(NOW)
        self.assertTrue(rep["gaps"])
        self.assertGreaterEqual(len(rep["high_priority_questions"]), 5)
        self.assertEqual(rep["ranking_method"]["type"], "heuristic (not statistically objective)")
        for g in rep["gaps"]:
            self.assertIn("reasons", g)
            self.assertIn("inputs_used", g)
            self.assertIn("missing_inputs", g)

    def test_preview_writes_no_files(self):
        before = {p.name for p in paths.BRIEFS_DIR.iterdir()}
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["brief", "--opportunity", "OPP-013", "--format", "json"])
            cli.main(["gaps", "--portfolio", "--format", "json"])
            cli.main(["assumptions", "--opportunity", "OPP-013", "--format", "json"])
        after = {p.name for p in paths.BRIEFS_DIR.iterdir()}
        self.assertEqual(before, after)  # no new files

    def test_explicit_output_writes_only_that_file(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "opp-013.json"
            with contextlib.redirect_stdout(io.StringIO()):
                cli.main(["brief", "--opportunity", "OPP-013", "--format", "json", "--output", str(out)])
            self.assertTrue(out.exists())
            self.assertEqual(list(Path(td).iterdir()), [out])

    def test_source_scorecard_unmodified(self):
        scp = paths.KB / "opportunity-scores" / "opp-013-scorecard.json"
        before = sha(scp)
        self._view()
        gaps.build_portfolio(NOW)
        self.assertEqual(sha(scp), before)


class Synthetic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        build_repo(self.tmp.name)  # writes opp-test scorecard + SEG-TEST + impact dirs
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(lambda: paths.set_repo_root(REPO))

    def test_approved_impact_updates_register(self):
        write_proposal(proposal.generate(make_scorecard(), make_descriptor(),
                                         make_descriptor()["segment"],
                                         proposal_id="PROP-T", today="2026-07-13"))
        apply_mod.apply_impact("PROP-T", approver="tester", confirm_segment_upgrade=True)
        model = tracker.build("OPP-TEST", NOW)
        wtp = next(a for a in model["assumptions"] if a["factor"] == "willingness_to_pay")
        self.assertEqual(wtp["status"], "partially_supported")
        self.assertIn("EV-TEST-001", wtp["supporting_ev"])

    def test_contradiction_preserves_supporting(self):
        # authoritative register with both supporting and contradicting evidence
        reg = {"opportunity_id": "OPP-TEST", "assumptions": [
            {"factor": "credit_need", "text": "t", "status": "contradicted",
             "supporting_ev": ["EV-2026-W28-015"], "contradicting_ev": ["EV-2026-W28-018"],
             "sensitivity": "", "next_validation": ""}]}
        (paths.ASSUMPTIONS_DIR / "opp-test.json").write_text(json.dumps(reg))
        model = tracker.build("OPP-TEST", NOW)
        item = next(a for a in model["assumptions"] if a["factor"] == "credit_need")
        self.assertEqual(item["status"], "contradicted")
        self.assertIn("EV-2026-W28-015", item["supporting_ev"])   # supporting preserved
        self.assertIn("EV-2026-W28-018", item["contradicting_ev"])

    def test_malformed_ev_reported(self):
        card = make_scorecard()
        card["scores"]["credit_need"]["basis"] = "cites EV-2099-W99-999 which does not exist"
        (paths.KB / "opportunity-scores" / "opp-test-scorecard.json").write_text(json.dumps(card))
        model = tracker.build("OPP-TEST", NOW)
        self.assertTrue(any(p["ev_id"] == "EV-2099-W99-999" for p in model["evidence_problems"]))

    def test_missing_optional_metadata_ok(self):
        # no register, no sidecar, no history -> still builds
        model = tracker.build("OPP-TEST", NOW)
        self.assertTrue(model["assumptions"])
        self.assertEqual(model["counts"]["unresolved"], model["counts"]["total_assumptions"])

    def test_stale_source_hash_detectable(self):
        model = tracker.build("OPP-TEST", NOW)
        self.assertEqual(genmeta.stale(model["meta"]), [])  # fresh
        scp = paths.KB / "opportunity-scores" / "opp-test-scorecard.json"
        scp.write_text(scp.read_text() + "\n")  # touch a source
        changed = genmeta.stale(model["meta"])
        self.assertTrue(any("opp-test-scorecard.json" in c for c in changed))

    def test_portfolio_with_opp_lacking_register(self):
        # OPP-TEST has no authoritative register; portfolio still works
        rep = gaps.build_portfolio(NOW)
        self.assertTrue(any(g["opportunity_id"] == "OPP-TEST" for g in rep["gaps"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
