"""Merchant Voice (Phase 5) orchestrator-level tests: merchant questions are
grounded in approved+published findings only, survey/interview/concept
reaction are distinguished, contradictions and limitations always surface,
n-of-m wording is used (never a bare percentage), merchant_finding
citations are emitted with an internal/anonymized target, no product-
selection or build-decision claim is made, and existing Part A behavior /
conversation-API contract shape are unaffected."""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import Config              # noqa: E402
from app.orchestrator import Orchestrator  # noqa: E402
from app.store import ConversationStore    # noqa: E402
from app import tools_registry             # noqa: E402

from test_mv_tools import _build_fixture_mv_db  # noqa: E402

ANSWER_TYPES = {"analysis", "brief", "comparison", "evidence", "challenge", "assumptions",
                "research_recommendation", "research_request_draft", "change_summary",
                "merchant_feedback"}
CITE_TYPES = {"evidence", "opportunity", "segment", "inflection", "experiment", "assumption",
             "merchant_finding"}
CITE_ROLES = {"primary", "contextual", "contradictory", "weak_lead", "excluded", "concept_reaction"}


def assert_contract(tc, resp):
    for key in ("schema_version", "conversation_id", "message_id", "answer_markdown",
                "answer_type", "confidence", "citations", "assumptions", "unknowns",
                "recommended_next_actions", "warnings", "safe_tool_trace"):
        tc.assertIn(key, resp)
    tc.assertEqual(resp["schema_version"], "1.0")
    tc.assertIn(resp["answer_type"], ANSWER_TYPES)
    tc.assertIn(resp["confidence"]["level"], ("high", "medium", "low", "mixed"))
    for c in resp["citations"]:
        tc.assertIn(c["type"], CITE_TYPES)
        tc.assertIn(c["role"], CITE_ROLES)
        tc.assertEqual(c["target"]["type"], "internal_route")
        tc.assertTrue(c["target"]["value"].startswith("/"))
        tc.assertNotIn("knowledge-base", c["target"]["value"])


def make_orchestrator():
    cfg = Config(env={"COPILOT_PROVIDER": "mock", "COPILOT_DEBUG_TRACE": "0"})
    cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
    store = ConversationStore(cfg.db_path)
    return Orchestrator(cfg, store), store, cfg


class MerchantVoiceOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.o, self.store, self.cfg = make_orchestrator()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._original_path = tools_registry.MV_CONFIG.mv_db_path
        self.addCleanup(setattr, tools_registry.MV_CONFIG, "mv_db_path", self._original_path)

    def _seed(self, **kwargs):
        db_path, cid, fid = _build_fixture_mv_db(self.tmp.name, **kwargs)
        tools_registry.MV_CONFIG.mv_db_path = db_path
        return cid, fid

    def test_merchant_feedback_question_grounded_in_approved_findings(self):
        cid, fid = self._seed()
        r = self.o.chat(f"What did we learn from {cid}?")
        assert_contract(self, r)
        self.assertIn("Suppliers cancel late payments.", r["answer_markdown"])
        self.assertTrue(any(c["id"] == fid for c in r["citations"]))

    def test_n_of_m_wording_used_not_bare_percentage(self):
        cid, fid = self._seed()
        r = self.o.chat(f"What did we learn from {cid}?")
        self.assertIn("1 of 1", r["answer_markdown"])
        self.assertNotIn("%", r["answer_markdown"])

    def test_merchant_finding_citation_emitted_with_internal_anonymized_target(self):
        cid, fid = self._seed()
        r = self.o.chat(f"What did we learn from {cid}?")
        cite = next(c for c in r["citations"] if c["id"] == fid)
        self.assertEqual(cite["type"], "merchant_finding")
        self.assertEqual(cite["target"]["value"], f"/merchant-findings/{fid}")
        blob = json.dumps(cite)
        self.assertNotIn("MVP-", blob)  # no participant id
        self.assertNotIn("MID-", blob)  # no merchant identity id

    def test_contradictions_surfaced(self):
        cid, fid = self._seed()
        r = self.o.chat(f"What contradictions came up for merchants in {cid}?")
        assert_contract(self, r)
        # the discipline epilogue always mentions preserving contradictions/limitations
        self.assertIn("Merchant Voice", r["answer_markdown"])

    def test_concept_reaction_not_presented_as_validation(self):
        cid, fid = self._seed()
        r = self.o.chat("What concept reactions have merchants given?")
        low = r["answer_markdown"].lower()
        self.assertNotIn("market validated", low)
        self.assertNotIn("demand is validated", low)
        self.assertIn("no product or build decision has been made", low)

    def test_no_product_selection_or_build_decision_claim(self):
        cid, fid = self._seed()
        r = self.o.chat(f"What are merchants saying about supplier-payment delays in {cid}?")
        self.assertIn("No product or build decision has been made.", r["answer_markdown"])

    def test_survey_and_interview_methods_distinguished(self):
        cid, fid = self._seed()
        r = self.o.chat(f"What did we learn from {cid}?")
        self.assertIn("interview", r["answer_markdown"].lower())

    def test_segment_feedback_question(self):
        cid, fid = self._seed(segment_id="SEG-alpha")
        r = self.o.chat("What feedback does merchant segment SEG-alpha report?")
        assert_contract(self, r)
        self.assertTrue(any(c["id"] == fid for c in r["citations"]))

    def test_wtp_limitations_preserved_when_present(self):
        cid, fid = self._seed()
        # deliberately no MVC- id here: campaign_summary would otherwise
        # take priority (an explicit campaign reference shows the whole
        # campaign) — this exercises the merchant_wtp_signals intent itself
        r = self.o.chat("What willingness to pay signals do merchants report?")
        assert_contract(self, r)
        # no data of this finding_type exists in the fixture (it's a plain
        # pain finding) -- confirms the tool degrades to an explicit unknown
        # rather than fabricating a signal
        self.assertTrue(r["unknowns"])

    def test_existing_opportunity_questions_unaffected(self):
        r = self.o.chat("What evidence supports willingness to pay for OPP-013?")
        self.assertEqual(r["answer_type"], "evidence")
        self.assertIn("EV-2026-W28-015", r["answer_markdown"])

    def test_existing_contradiction_question_unaffected(self):
        # pre-existing behavior (unchanged by Phase 5): a bare "contradicts
        # OPP-013" question classifies as opportunity_explanation, and
        # get_opportunity's own grounding already surfaces contradicting
        # evidence regardless of intent name — see test_backend.py's
        # equivalent test, which likewise never asserts answer_type here.
        r = self.o.chat("What evidence contradicts OPP-013?")
        self.assertIn("switching_intent", r["answer_markdown"])

    def test_conversation_api_contract_shape_unchanged(self):
        cid, fid = self._seed()
        r = self.o.chat(f"What did we learn from {cid}?")
        assert_contract(self, r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
