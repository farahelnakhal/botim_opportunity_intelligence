"""Phase R3 — external-research grounding: approved-only, clearly external,
traceable citations, honest empty state, stale flagging. Offline (MockProvider
+ mock search provider + temp research DB)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

os.environ["RESEARCH_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "research.db")

from app.config import Config                    # noqa: E402
from app.orchestrator import Orchestrator        # noqa: E402
from app.store import ConversationStore          # noqa: E402
from app import intents                          # noqa: E402
from shared.research import (MockSearchProvider, ResearchStore,  # noqa: E402
                             execute_run)


def make_orchestrator():
    cfg = Config(env={"COPILOT_PROVIDER": "mock"})
    cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
    return Orchestrator(cfg, ConversationStore(cfg.db_path))


def seed_candidate(store, approve=True, published_at="2026-06-01", opp="OPP-010"):
    run = store.create_run({"title": "seed run", "opportunity_ref": opp})
    store.add_query(run["id"], {"query_text": "q"})
    execute_run(store, run["id"], MockSearchProvider({"q": [
        {"url": f"https://example.com/{os.urandom(4).hex()}",
         "title": "SME Report", "published_at": published_at}]}),
        fetch_fn=lambda u, t: (200, "text/html", b"<html><title>SME Report</title><body>b</body>"),
        sleep_fn=lambda s: None)
    full = store.get_run(run["id"], include_children=True)
    cand = store.add_candidate(run["id"], {
        "claim": "UAE has roughly 600k SMEs according to ministry data",
        "source_ids": [full["sources"][0]["id"]]})
    if approve:
        cand = store.review_candidate(cand["id"], "approve")
    return run, cand


class IntentRouting(unittest.TestCase):
    def _classify(self, msg):
        return intents.classify(msg, intents.extract_ids(msg),
                                is_new_conversation=True, has_selected_context=False)

    def test_external_research_phrasings_route_to_the_new_intent(self):
        for msg in ("What did the external research find?",
                    "Summarize the web research for OPP-010",
                    "Show research findings from the last research run"):
            self.assertEqual(self._classify(msg), "external_research_summary", msg)

    def test_existing_research_recommendation_routing_unchanged(self):
        self.assertEqual(self._classify("What should we research next for OPP-013?"),
                         "research_recommendation")


class Grounding(unittest.TestCase):
    def setUp(self):
        # a fresh, isolated research DB per test
        os.environ["RESEARCH_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "research.db")
        self.store = ResearchStore()
        self.orch = make_orchestrator()

    def _ask(self, msg="What did the external research find about OPP-010?"):
        return self.orch.chat(msg, conversation_id=None)

    def test_empty_store_is_an_honest_unknown_not_a_fabrication(self):
        r = self._ask()
        self.assertIn("No approved external research candidates", r["answer_markdown"])
        self.assertEqual([c for c in r["citations"] if c["type"] == "research_candidate"], [])

    def test_pending_candidates_never_ground_answers(self):
        seed_candidate(self.store, approve=False)
        r = self._ask()
        self.assertNotIn("600k SMEs", r["answer_markdown"])
        self.assertIn("No approved external research candidates", r["answer_markdown"])

    def test_approved_candidate_grounds_with_external_label_and_citation(self):
        run, cand = seed_candidate(self.store)
        r = self._ask()
        self.assertIn("EXTERNAL RESEARCH", r["answer_markdown"])
        self.assertIn("NOT authoritative", r["answer_markdown"])
        self.assertIn("600k SMEs", r["answer_markdown"])
        cites = [c for c in r["citations"] if c["type"] == "research_candidate"]
        self.assertEqual(len(cites), 1)
        self.assertEqual(cites[0]["id"], cand["id"])
        self.assertEqual(cites[0]["target"]["value"], f"/research/runs/{run['id']}")
        self.assertTrue(cites[0]["metadata"]["external"])
        self.assertEqual(cites[0]["metadata"]["sources"][0]["freshness_status"], "fresh")

    def test_stale_source_produces_a_deterministic_warning(self):
        seed_candidate(self.store, published_at="2024-01-01")
        r = self._ask()
        self.assertTrue(any("stale" in w.lower() for w in r["warnings"]),
                        r["warnings"])
        self.assertIn("[STALE]", r["answer_markdown"])

    def test_never_mints_or_implies_an_ev_id(self):
        seed_candidate(self.store)
        r = self._ask()
        import re
        self.assertIsNone(re.search(r"\bEV-\d{4}-W\d{2}-\d{3}\b", r["answer_markdown"]))


if __name__ == "__main__":
    unittest.main()
