"""Phase 3 — first-message intent classification must require POSITIVE
evidence of a new product idea, never fire on a greeting/vague/monitoring/
methodology/portfolio message, and must always defer to explicit ids or
already-selected context. MockProvider only, zero network.
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


def classify_new_chat(text, has_selected_context=False):
    ids = intents.extract_ids(text)
    return intents.classify(text, ids, is_new_conversation=True, has_selected_context=has_selected_context)


def make_orchestrator():
    cfg = Config(env={"COPILOT_PROVIDER": "mock", "COPILOT_DEBUG_TRACE": "0"})
    cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
    return Orchestrator(cfg, ConversationStore(cfg.db_path))


class Greeting(unittest.TestCase):
    def test_hello_hi_help_get_clarification_not_new_product(self):
        for msg in ("Hello", "Hi", "Help", "hello there", "Hey!"):
            self.assertEqual(classify_new_chat(msg), "clarification_needed", msg)

    def test_clarification_response_is_exact_and_deterministic(self):
        r = make_orchestrator().chat("Hello", conversation_id=None)
        self.assertEqual(r["answer_type"], "clarification")
        self.assertEqual(r["answer_markdown"], intents.CLARIFICATION)
        self.assertEqual(r["citations"], [])

    def test_greeting_embedded_in_a_real_request_is_not_swallowed(self):
        # "Hi" as a mere pleasantry inside a real product idea must not be
        # treated as a bare greeting (the anchor requires the WHOLE message).
        got = classify_new_chat("Hi, I have an idea for supplier-payment credit")
        self.assertEqual(got, "new_opportunity_analysis")


class Vague(unittest.TestCase):
    def test_can_you_explain_this_is_not_new_product(self):
        self.assertNotEqual(classify_new_chat("Can you explain this?"), "new_opportunity_analysis")


class Monitoring(unittest.TestCase):
    def test_monitoring_and_change_phrasings_route_to_change_summary(self):
        for msg in ("Show recent monitoring updates.", "What changed this week?",
                   "What's new?", "Any recent developments?"):
            self.assertEqual(classify_new_chat(msg), "change_summary", msg)


class ScoringMethodology(unittest.TestCase):
    def test_how_does_scoring_work_routes_to_general_explanation(self):
        for msg in ("How does scoring work?", "Explain the scoring methodology.",
                   "How is the composite score calculated?"):
            self.assertEqual(classify_new_chat(msg), "general_explanation", msg)

    def test_general_explanation_is_grounded_in_fixed_methodology_fact_not_invented(self):
        r = make_orchestrator().chat("How does scoring work?", conversation_id=None)
        self.assertEqual(r["answer_type"], "analysis")
        self.assertIn("17", r["answer_markdown"])
        self.assertIn("capped", r["answer_markdown"].lower())


class MerchantFeedback(unittest.TestCase):
    def test_merchant_statements_route_to_merchant_feedback(self):
        self.assertEqual(classify_new_chat("What are merchants saying?"), "merchant_feedback")


class PortfolioComparison(unittest.TestCase):
    def test_strongest_and_compare_and_portfolio(self):
        self.assertEqual(classify_new_chat("What is our strongest opportunity?"), "opportunity_comparison")
        self.assertEqual(classify_new_chat("Compare our opportunities."), "opportunity_comparison")
        self.assertEqual(classify_new_chat("Show the portfolio."), "portfolio_summary")


class ExplicitIds(unittest.TestCase):
    def test_explicit_opp_id_wins_over_new_product_heuristic(self):
        self.assertEqual(classify_new_chat("Tell me about OPP-013."), "opportunity_explanation")

    def test_explicit_id_wins_even_with_product_idea_wording(self):
        self.assertEqual(classify_new_chat("New product idea for OPP-010"), "opportunity_explanation")

    def test_evidence_and_assumption_phrasing(self):
        self.assertEqual(classify_new_chat("What supports EV-001?"), "evidence_support")
        self.assertEqual(classify_new_chat("Which assumptions are weakest?"), "assumption_analysis")


class SelectedContext(unittest.TestCase):
    def test_selected_opportunity_context_prevents_new_product_analysis(self):
        got = classify_new_chat("What are the biggest risks here?", has_selected_context=True)
        self.assertNotEqual(got, "new_opportunity_analysis")

    def test_selected_context_prevents_new_product_even_with_idea_wording(self):
        got = classify_new_chat("I have an idea for supplier credit", has_selected_context=True)
        self.assertNotEqual(got, "new_opportunity_analysis")


class GenuineProductIdea(unittest.TestCase):
    def test_all_genuine_new_product_examples_select_new_opportunity_analysis(self):
        examples = [
            "I have an idea for supplier-payment credit.",
            "We should build a card for small merchants.",
            "Analyze a product that lets merchants delay supplier payments.",
            "Could we create a working-capital feature for restaurants?",
            "Evaluate a marketplace for SME supplier financing.",
            "I want to test a product that helps freelancers manage late invoices.",
        ]
        for msg in examples:
            self.assertEqual(classify_new_chat(msg), "new_opportunity_analysis", msg)

    def test_not_a_new_conversation_does_not_trigger_new_product(self):
        # a follow-up (not the first message) never spontaneously starts a
        # new product analysis, even with matching wording
        ids = intents.extract_ids("I have an idea for supplier credit")
        got = intents.classify("I have an idea for supplier credit", ids,
                               is_new_conversation=False, has_selected_context=False)
        self.assertNotEqual(got, "new_opportunity_analysis")


if __name__ == "__main__":
    unittest.main()
