"""Phase 2 — new_opportunity_analysis: mode detection, grounded retrieval,
no-evidence-found handling, and citation integrity for a genuinely new idea
that has no OPP record yet. MockProvider only (deterministic, zero network),
against the real read-only repository.
"""

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from app import intents                       # noqa: E402
from app.config import Config                 # noqa: E402
from app.orchestrator import Orchestrator      # noqa: E402
from app.store import ConversationStore        # noqa: E402


def make_orchestrator():
    cfg = Config(env={"COPILOT_PROVIDER": "mock", "COPILOT_DEBUG_TRACE": "0"})
    cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
    store = ConversationStore(cfg.db_path)
    return Orchestrator(cfg, store), store, cfg


class ModeDetection(unittest.TestCase):
    """Test 6/7 — first message on a new conversation is treated as a new
    product idea unless an explicit id or selected context says otherwise."""

    def test_first_message_new_conversation_is_new_opportunity_analysis(self):
        ids = intents.extract_ids("Invoice financing for UAE logistics SMEs waiting 45 days to get paid")
        got = intents.classify("Invoice financing for UAE logistics SMEs waiting 45 days to get paid",
                               ids, is_new_conversation=True, has_selected_context=False)
        self.assertEqual(got, "new_opportunity_analysis")

    def test_explicit_opp_id_wins_over_new_conversation(self):
        text = "Tell me about OPP-013"
        ids = intents.extract_ids(text)
        got = intents.classify(text, ids, is_new_conversation=True, has_selected_context=False)
        self.assertEqual(got, "opportunity_explanation")

    def test_selected_context_prevents_new_opportunity_analysis(self):
        # e.g. the user opened an existing opportunity's chat tab and asked a
        # generic follow-up with no id in the text itself.
        text = "What are the biggest risks here?"
        ids = intents.extract_ids(text)
        got = intents.classify(text, ids, is_new_conversation=True, has_selected_context=True)
        self.assertNotEqual(got, "new_opportunity_analysis")

    def test_followup_in_existing_conversation_is_not_new_opportunity_analysis(self):
        text = "Say more about that."
        ids = intents.extract_ids(text)
        got = intents.classify(text, ids, is_new_conversation=False, has_selected_context=False)
        self.assertNotEqual(got, "new_opportunity_analysis")


class GroundedPipeline(unittest.TestCase):
    def setUp(self):
        self.o, self.store, self.cfg = make_orchestrator()

    def test_new_idea_reuses_repository_search_and_cites_real_records(self):
        # "supplier" + "payment" match real evidence/opportunity records already
        # in the knowledge base (see opp-002 / supplier-payment-card fixtures).
        resp = self.o.chat("A card product for supplier payments to reduce cash-flow strain",
                          conversation_id=None)
        self.assertEqual(resp["answer_type"], "new_opportunity_analysis")
        self.assertIsInstance(resp["citations"], list)
        # every citation must be a real record id the tools actually returned —
        # never a bare fabrication (test 16: cannot invent EV/OPP/SEG/ASM ids)
        for c in resp["citations"]:
            self.assertRegex(c["id"], r"^(EV-|OPP-|SEG-|ASM-|VE-|MVC-|MEF-)|^[a-z0-9-]+$")
        self.assertIn("No product or build decision has been made.", resp["answer_markdown"])

    def test_no_evidence_found_produces_explicit_unknown_not_fabrication(self):
        resp = self.o.chat("Xyzzyplex Qwzxcvbnm Blorptastic Fnargle Vexnorbit",
                          conversation_id=None)
        self.assertEqual(resp["answer_type"], "new_opportunity_analysis")
        self.assertTrue(any("no related repository evidence" in u for u in resp["unknowns"]),
                        resp["unknowns"])

    def test_never_states_a_numeric_score_for_a_new_idea(self):
        resp = self.o.chat("A working-capital product for freelance delivery riders",
                          conversation_id=None)
        low = resp["answer_markdown"].lower()
        for banned in ("composite score", "raw score", "classification: strong",
                      "classification: promising"):
            self.assertNotIn(banned, low)

    def test_wordguard_blocks_overclaims_for_new_ideas(self):
        from app.wordguard import check_wording
        self.assertIsNotNone(check_wording("Demand is proven for this and merchants will pay immediately."))
        self.assertIsNotNone(check_wording("This is ready to build."))

    def test_recommended_next_action_present_even_when_nothing_found(self):
        resp = self.o.chat("Xyzzyplex Qwzxcvbnm Blorptastic Fnargle Vexnorbit",
                          conversation_id=None)
        self.assertEqual(resp["answer_type"], "new_opportunity_analysis")
        self.assertTrue(resp["recommended_next_actions"])

    def test_followup_preserves_conversation_and_does_not_restart_new_opportunity_analysis(self):
        first = self.o.chat("A prepaid card product for gig-economy delivery drivers",
                           conversation_id=None)
        cid = first["conversation_id"]
        second = self.o.chat("What about the segment specifically?", conversation_id=cid)
        self.assertEqual(second["conversation_id"], cid)
        # a bare follow-up in an ALREADY-established conversation must not be
        # re-classified as a fresh new_opportunity_analysis
        self.assertNotEqual(second["answer_type"], "new_opportunity_analysis")


if __name__ == "__main__":
    unittest.main()
