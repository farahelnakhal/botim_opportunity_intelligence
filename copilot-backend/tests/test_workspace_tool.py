"""Phase R5 / PR4 — copilot read-only access to the analysis workspace.
Everything the tool returns is labelled PRELIMINARY; pending claims are kept
visibly apart from approved ones; reading never builds anything."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[0]
for p in (str(BACKEND), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("COPILOT_PROVIDER", "mock")

from app import grounding, intents, tools_registry  # noqa: E402
from shared.research import ResearchStore  # noqa: E402
from shared.workspace import WorkspaceStore  # noqa: E402


def seed_workspace(tmp, *, review=None, stale=False):
    """A complete workspace version backed by a real research run with one
    extracted-style candidate claim. Returns (opp_id, version_id)."""
    os.environ["WORKSPACE_DB_PATH"] = str(tmp / "workspace.db")
    os.environ["RESEARCH_DB_PATH"] = str(tmp / "research.db")
    rs = ResearchStore(tmp / "research.db")
    run = rs.create_run({"title": "Workspace analysis: test",
                         "opportunity_ref": "UOPP-aaaaaaaaaaa1", "profile": "workspace"})
    run = rs.start_run(run["id"])
    src = rs.add_source(run["id"], {"canonical_url": "https://example.com/r",
                                    "title": "Report",
                                    "excerpt": "The market grew 12% in 2024."})
    cand = rs.add_candidate(run["id"], {
        "claim": "The market grew 12% in 2024.", "source_ids": [src["id"]],
        "origin": "extracted",
        "extraction_meta": {"model": "stub", "supporting_quotes": {src["id"]: ["grew 12%"]}}})
    rs.finish_run(run["id"], "complete")
    if review:
        rs.review_candidate(cand["id"], review)
    ws = WorkspaceStore(tmp / "workspace.db")
    v = ws.create_version("UOPP-aaaaaaaaaaa1", "first_analysis")
    v = ws.complete_version(
        v["id"], kb_evidence=[{"id": "EV-2026-W01-001", "title": "Related record"}],
        claim_ids=[cand["id"]],
        preliminary_score={"preliminary": True, "engine": "opportunity_engine.scoring",
                           "composite": 3.0, "assumption_count": 17,
                           "assumption_capped": True, "max_classification": "promising",
                           "classification": "promising (preliminary, unvalidated)",
                           "confidence": "low"},
        gaps=["no related internal evidence beyond one record"],
        provenance={"trigger": "first_analysis"}, research_run_id=run["id"])
    if stale:
        os.environ["WORKSPACE_STALE_HOURS"] = "0"
    else:
        os.environ.pop("WORKSPACE_STALE_HOURS", None)
    return "UOPP-aaaaaaaaaaa1", v["id"]


class WorkspaceTool(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("WORKSPACE_STALE_HOURS", None)

    def test_no_workspace_is_an_honest_empty_answer(self):
        tmp = Path(tempfile.mkdtemp())
        os.environ["WORKSPACE_DB_PATH"] = str(tmp / "workspace.db")
        result = tools_registry.get_analysis_workspace("UOPP-aaaaaaaaaaa1")
        self.assertIsNone(result["workspace"])
        self.assertIn("no analysis workspace exists", result["note"])

    def test_workspace_resolves_claims_to_current_review_status(self):
        tmp = Path(tempfile.mkdtemp())
        opp_id, _ = seed_workspace(tmp)
        result = tools_registry.get_analysis_workspace(opp_id)
        w = result["workspace"]
        self.assertEqual(w["claims"][0]["status"], "pending_review")
        self.assertEqual(w["claims"][0]["origin"], "extracted")
        self.assertIn("PRELIMINARY", result["note"])
        # an approval done AFTER the version was built shows through — the
        # approval lives on the claim, not on the workspace version
        from shared.research import ResearchStore
        ResearchStore(tmp / "research.db").review_candidate(
            w["claims"][0]["candidate_id"], "approve")
        again = tools_registry.get_analysis_workspace(opp_id)
        self.assertEqual(again["workspace"]["claims"][0]["status"], "approved")

    def test_invalid_ref_rejected(self):
        with self.assertRaises(tools_registry.ToolError):
            tools_registry.get_analysis_workspace("DROP TABLE")


class WorkspaceGrounding(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("WORKSPACE_STALE_HOURS", None)

    def _ids(self):
        return intents.extract_ids("")

    def test_pending_claims_are_labelled_and_never_presented_as_established(self):
        tmp = Path(tempfile.mkdtemp())
        opp_id, _ = seed_workspace(tmp)
        result = tools_registry.get_analysis_workspace(opp_id)
        pack = grounding.build("opportunity_explanation",
                               [("get_analysis_workspace", result)], self._ids())
        facts = "\n".join(pack.facts)
        self.assertIn("PRELIMINARY ANALYSIS WORKSPACE", facts)
        self.assertIn("PENDING HUMAN REVIEW", facts)
        self.assertIn("[pending review] The market grew 12% in 2024.", facts)
        self.assertNotIn("APPROVED external claim", facts)
        self.assertTrue(pack.needs_no_decision)
        self.assertEqual(pack.conf_sources["analysis workspace (preliminary)"], "low")
        # engine-capped score is stated as capped
        self.assertIn("capped at 'promising'", facts)

    def test_approved_claims_are_cited_as_research_candidates(self):
        tmp = Path(tempfile.mkdtemp())
        opp_id, _ = seed_workspace(tmp, review="approve")
        result = tools_registry.get_analysis_workspace(opp_id)
        pack = grounding.build("opportunity_explanation",
                               [("get_analysis_workspace", result)], self._ids())
        facts = "\n".join(pack.facts)
        self.assertIn("APPROVED external claim", facts)
        cand_id = result["workspace"]["claims"][0]["candidate_id"]
        self.assertIn(cand_id, pack.citations)
        self.assertEqual(pack.citations[cand_id]["type"], "research_candidate")

    def test_stale_workspace_produces_a_deterministic_warning(self):
        tmp = Path(tempfile.mkdtemp())
        opp_id, _ = seed_workspace(tmp, stale=True)
        result = tools_registry.get_analysis_workspace(opp_id)
        pack = grounding.build("opportunity_explanation",
                               [("get_analysis_workspace", result)], self._ids())
        self.assertTrue(any("stale" in w for w in pack.warnings))

    def test_empty_workspace_result_is_an_unknown(self):
        tmp = Path(tempfile.mkdtemp())
        os.environ["WORKSPACE_DB_PATH"] = str(tmp / "workspace.db")
        result = tools_registry.get_analysis_workspace("UOPP-aaaaaaaaaaa1")
        pack = grounding.build("opportunity_explanation",
                               [("get_analysis_workspace", result)], self._ids())
        self.assertTrue(any("no analysis workspace" in u for u in pack.unknowns))


class WorkspacePlanWiring(unittest.TestCase):
    def test_uopp_ids_are_extracted_and_normalized(self):
        ids = intents.extract_ids("what does the workspace say about UOPP-ABCDEF123456?")
        self.assertEqual(ids["user_opportunities"], ["UOPP-abcdef123456"])

    def test_tool_is_registered_and_read_only_shaped(self):
        specs = {s["name"]: s for s in tools_registry.tool_specs()}
        self.assertIn("get_analysis_workspace", specs)
        self.assertEqual(specs["get_analysis_workspace"]["input_schema"]["required"],
                         ["opportunity_ref"])


if __name__ == "__main__":
    unittest.main()
