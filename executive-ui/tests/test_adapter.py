"""Adapter correctness — the real risk surface. Runs against the live repo
(read-only) and asserts the model reflects engine truth, not invented data."""

import sys
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
REPO = UI.parents[0]
sys.path.insert(0, str(UI))

from adapter import collect, model as M  # noqa: E402


class TestModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = collect.build_model(str(REPO))

    def test_multiple_opportunities_not_just_opp013(self):
        ids = [o.id for o in self.m.opportunities]
        self.assertIn("OPP-013", ids)
        self.assertGreater(len(ids), 1, "must not hard-code a single opportunity")
        self.assertIn("OPP-010", ids)

    def test_ranked_by_raw_score(self):
        raws = [o.raw_score for o in self.m.opportunities]
        self.assertEqual(raws, sorted(raws, reverse=True))
        self.assertEqual(self.m.opportunities[0].id, "OPP-010")  # real leader, not OPP-013

    def test_raw_matches_engine_sum(self):
        # adapter must not recompute — raw is the sum of the engine's factor scores
        for o in self.m.opportunities:
            self.assertEqual(o.raw_score, sum(f.score for f in o.factors))
            self.assertEqual(o.raw_max, 85)
            self.assertEqual(len(o.factors), 17)

    def test_opp013_real_values_not_brief_illustration(self):
        o = next(o for o in self.m.opportunities if o.id == "OPP-013")
        self.assertEqual(o.raw_score, 55)            # real, not the brief's illustrative 60
        self.assertEqual(o.assumption_count, 8)
        self.assertEqual(o.confidence, "medium")
        self.assertEqual(o.classification, "promising")

    def test_confidence_verbatim_not_reinterpreted(self):
        confs = {o.confidence for o in self.m.opportunities}
        self.assertTrue(confs <= {"low", "medium", "high"})

    def test_weak_evidence_flagged(self):
        weak = [r for r in self.m.evidence if r.weak]
        strong = [r for r in self.m.evidence if not r.weak]
        self.assertTrue(weak and strong, "both weak and strong evidence must exist")
        for r in weak:
            self.assertTrue((isinstance(r.strength, int) and r.strength < 3)
                            or r.status == "needs-more-evidence" or not r.resolved)

    def test_archived_reject_present_without_score(self):
        ids = [o.id for o in self.m.archived]
        self.assertIn("OPP-003", ids)
        opp003 = next(o for o in self.m.archived if o.id == "OPP-003")
        self.assertIsNone(opp003.raw_score)          # honest: no invented score
        self.assertEqual(opp003.classification, "reject")

    def test_brief_detected_for_opp001_only(self):
        exist = {b.opportunity_id for b in self.m.briefs if b.exists}
        self.assertEqual(exist, {"OPP-001"})         # the one real recommendation doc

    def test_assumptions_derived_with_status(self):
        self.assertTrue(self.m.assumptions)
        statuses = {a.status for a in self.m.assumptions}
        self.assertTrue(statuses <= {"untested", "partially-supported", "supported", "contradicted"})
        # every assumption row belongs to a real opportunity
        opp_ids = {o.id for o in self.m.opportunities}
        for a in self.m.assumptions:
            self.assertIn(a.opportunity_id, opp_ids)

    def test_missing_fields_are_unknown_not_invented(self):
        # sensitivity/owner are not structured anywhere -> must be the honest sentinel
        for a in self.m.assumptions:
            self.assertEqual(a.owner, M.UNKNOWN)

    def test_latest_change_is_honest_default(self):
        # no impact workflow exists -> the honest default, never a fabricated change
        for o in self.m.opportunities:
            self.assertEqual(o.latest_change, "No approved impact yet")


if __name__ == "__main__":
    unittest.main()
