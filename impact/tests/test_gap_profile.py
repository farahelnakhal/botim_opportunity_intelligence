"""Phase R10 / PR10a — evidence-gap profiler tests. Deterministic, offline,
against a throwaway temp knowledge base (no live KB touched)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from impact import gap_profile, paths  # noqa: E402

NOW = "2026-07-20T00:00:00Z"

# 17 canonical factors; 15 assumption:true (capped, cap=6). willingness_to_pay's
# basis cites a stale EV; competitive_defensibility will be marked contradicted
# and mvp_feasibility_7wk supported via the authoritative assumptions store.
_SCORES = {
    "pain_severity": (4, True), "pain_frequency": (4, True), "financial_impact": (4, True),
    "workaround_cost": (4, True), "switching_intent": (3, True),
    "willingness_to_pay": (3, True), "digital_readiness": (3, True),
    "payment_volume": (3, True), "credit_need": (5, True),
    "botim_distribution_advantage": (4, True), "transaction_data_advantage": (3, True),
    "payment_revenue_potential": (2, True), "lending_revenue_potential": (4, True),
    "credit_risk_visibility": (3, True), "competitive_defensibility": (3, True),
    "ease_of_validation": (4, False), "mvp_feasibility_7wk": (4, False),
}


def _scorecard():
    scores = {}
    for k, (s, a) in _SCORES.items():
        basis = "fixture"
        if k == "willingness_to_pay":
            basis = "merchants pay a surcharge today (EV-2024-W01-001)"
        scores[k] = {"score": s, "assumption": a, "basis": basis}
    return {"opportunity_id": "OPP-TEST", "name": "Synthetic test opportunity",
            "is_lending_product": True, "proposed_classification": "promising",
            "evidence_confidence": "medium", "scores": scores}


STALE_RECORD = (
    "## EV-2024-W01-001 — an old supporting record\n"
    "**Status:** active · **Created:** 2024-01-01 · **Last verified:** 2024-01-01\n\n"
    "| Customer segment | SEG-TEST |\n"
    "| Evidence confidence | Medium — two accounts |\n"
)

# authoritative assumptions store: set a supported + a contradicted status
ASSUMPTIONS_STORE = {
    "opportunity_id": "OPP-TEST",
    "assumptions": [
        {"factor": "willingness_to_pay", "status": "partially supported",
         "supporting_ev": ["EV-2024-W01-001"], "contradicting_ev": []},
        {"factor": "competitive_defensibility", "status": "contradicted",
         "supporting_ev": [], "contradicting_ev": ["EV-2024-W01-001"]},
        {"factor": "mvp_feasibility_7wk", "status": "supported",
         "supporting_ev": ["EV-2024-W01-001"], "contradicting_ev": []},
    ],
}


def build_repo(root):
    kb = Path(root) / "knowledge-base"
    (kb / "opportunity-scores").mkdir(parents=True)
    (kb / "customer-evidence" / "records").mkdir(parents=True)
    (kb / "impact" / "assumptions").mkdir(parents=True)
    (kb / "opportunity-scores" / "opp-test-scorecard.json").write_text(
        json.dumps(_scorecard(), indent=2) + "\n", encoding="utf-8")
    (kb / "customer-evidence" / "records" / "2024-W01.md").write_text(STALE_RECORD, encoding="utf-8")
    (kb / "impact" / "assumptions" / "opp-test.json").write_text(
        json.dumps(ASSUMPTIONS_STORE, indent=2) + "\n", encoding="utf-8")
    paths.set_repo_root(root)
    paths.ensure_dirs()


class GapProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        build_repo(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(lambda: paths.set_repo_root(Path(__file__).resolve().parents[2]))
        self.profile = gap_profile.build_gap_profile("OPP-TEST", NOW)

    def _link(self, factor):
        return next((w for w in self.profile["weak_links"] if w["factor"] == factor), None)

    def test_structure_and_determinism(self):
        again = gap_profile.build_gap_profile("OPP-TEST", NOW)
        self.assertEqual(json.dumps(self.profile), json.dumps(again))
        self.assertEqual(self.profile["opportunity_id"], "OPP-TEST")
        self.assertTrue(self.profile["weak_links"])
        # ranking: sorted desc by priority, ranks assigned 1..n
        scores = [w["priority_score"] for w in self.profile["weak_links"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual([w["priority_rank"] for w in self.profile["weak_links"]],
                         list(range(1, len(self.profile["weak_links"]) + 1)))

    def test_evidence_base_summary(self):
        eb = self.profile["evidence_base"]
        self.assertTrue(eb["assumption_capped"])          # 15 assumptions > cap 6
        self.assertEqual(eb["assumption_cap"], 6)
        self.assertGreater(eb["assumptions_to_lift_cap"], 0)
        self.assertIn("EV-2024-W01-001", eb["stale_load_bearing_ev"])

    def test_no_supporting_evidence_signal(self):
        # pain_severity has no cited EV -> flagged
        link = self._link("pain_severity")
        self.assertIsNotNone(link)
        self.assertIn("no_supporting_evidence", link["signals"])
        self.assertIn("open_gap", link["signals"])

    def test_stale_load_bearing_signal(self):
        link = self._link("willingness_to_pay")
        self.assertIsNotNone(link)
        self.assertIn("stale_load_bearing", link["signals"])
        self.assertEqual(link["stale_ev"][0]["ev_id"], "EV-2024-W01-001")
        self.assertEqual(link["stale_ev"][0]["freshness_status"], "stale")

    def test_assumption_capped_signal(self):
        # every still-assumption factor under a capped opportunity carries it
        link = self._link("pain_severity")
        self.assertIn("assumption_capped", link["signals"])

    def test_contradicted_signal(self):
        link = self._link("competitive_defensibility")
        self.assertIsNotNone(link)
        self.assertIn("contradicted", link["signals"])
        self.assertEqual(link["status"], "contradicted")

    def test_supported_assumption_excluded(self):
        # mvp_feasibility_7wk is 'supported' in the store -> not a weak link
        self.assertIsNone(self._link("mvp_feasibility_7wk"))

    def test_each_link_traces_to_an_assumption_id(self):
        for w in self.profile["weak_links"]:
            self.assertRegex(w["assumption_id"], r"^ASM-OPP-TEST-[a-z0-9_]+$")

    def test_missing_opportunity_raises(self):
        with self.assertRaises(FileNotFoundError):
            gap_profile.build_gap_profile("OPP-404", NOW)

    def test_render_markdown_smoke(self):
        md = gap_profile.render_markdown(self.profile, top=3)
        self.assertIn("Evidence-gap profile", md)
        self.assertIn("ASM-OPP-TEST-", md)


if __name__ == "__main__":
    unittest.main()
