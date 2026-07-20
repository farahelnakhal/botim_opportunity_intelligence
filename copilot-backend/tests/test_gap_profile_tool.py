"""Phase R10 / PR10a — copilot read-only access to the evidence-gap profile.
Deterministic; recomputes no score; each weak link surfaces as an unknown to
target, never a conclusion. Runs against the committed KB (read-only)."""

import json
import os
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[0]
for p in (str(BACKEND), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("COPILOT_PROVIDER", "mock")

from app import grounding, intents, tools_registry  # noqa: E402
from impact import paths as impact_paths  # noqa: E402


def _an_opportunity():
    cards = sorted((impact_paths.KB / "opportunity-scores").glob("*-scorecard.json"))
    return json.loads(cards[0].read_text(encoding="utf-8"))["opportunity_id"]


class GapProfileTool(unittest.TestCase):
    def test_tool_registered_and_shaped(self):
        specs = {s["name"]: s for s in tools_registry.tool_specs()}
        self.assertIn("get_evidence_gap_profile", specs)
        self.assertEqual(specs["get_evidence_gap_profile"]["input_schema"]["required"], ["opp_id"])

    def test_returns_ranked_weak_links(self):
        opp = _an_opportunity()
        prof = tools_registry.get_evidence_gap_profile(opp)
        self.assertEqual(prof["opportunity_id"], opp)
        self.assertIn("weak_links", prof)
        self.assertIn("evidence_base", prof)

    def test_unknown_opportunity_is_not_found(self):
        with self.assertRaises(tools_registry.ToolError) as cm:
            tools_registry.get_evidence_gap_profile("OPP-404")
        self.assertTrue(cm.exception.not_found)

    def test_invalid_id_rejected(self):
        with self.assertRaises(tools_registry.ToolError):
            tools_registry.get_evidence_gap_profile("DROP TABLE")


class GapProfilePlanAndGrounding(unittest.TestCase):
    def test_plan_includes_profile_when_opportunity_referenced(self):
        ids = intents.extract_ids("what are the evidence gaps for OPP-001?")
        plan = intents.tool_plan("evidence_gap", ids, "what are the evidence gaps for OPP-001?")
        tools = [t for t, _ in plan]
        self.assertIn("get_evidence_gap_profile", tools)

    def test_grounding_surfaces_weak_links_as_unknowns(self):
        opp = _an_opportunity()
        result = tools_registry.get_evidence_gap_profile(opp)
        pack = grounding.build("evidence_gap", [("get_evidence_gap_profile", result)],
                               intents.extract_ids(""))
        facts = "\n".join(pack.facts)
        self.assertIn("EVIDENCE-GAP PROFILE", facts)
        self.assertTrue(pack.needs_no_decision)
        # weak links become unknowns to target, not conclusions
        if result["weak_links"]:
            self.assertTrue(pack.unknowns)


if __name__ == "__main__":
    unittest.main()
