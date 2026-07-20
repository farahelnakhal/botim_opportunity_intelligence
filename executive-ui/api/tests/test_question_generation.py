"""Phase R10 / PR10b — question generation: gap profile -> LLM draft ->
deterministic taxonomy validation -> draft question-set store. Fully offline
(injected provider); no MV write, no auto-send, nothing to knowledge-base/."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("USER_OPPORTUNITIES_DB_PATH",
                      os.path.join(tempfile.mkdtemp(), "user-opportunities.db"))
os.environ["QUESTION_SETS_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "question-sets.db")

UI = Path(__file__).resolve().parents[2]
REPO = UI.parents[0]
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import question_generator  # noqa: E402
from shared.questions import QuestionSetStore  # noqa: E402
from shared.llm.provider import ConversationModel, ModelResponse  # noqa: E402
from impact import gap_profile  # noqa: E402

NOW = "2026-07-20T00:00:00Z"


def _an_opp_and_weak_link():
    cards = sorted((REPO / "knowledge-base" / "opportunity-scores").glob("*-scorecard.json"))
    opp = json.loads(cards[0].read_text(encoding="utf-8"))["opportunity_id"]
    prof = gap_profile.build_gap_profile(opp, NOW)
    return opp, prof["weak_links"][0]["assumption_id"]


class _Cfg:
    model = "stub-model"
    provider = "anthropic"


class StubModel(ConversationModel):
    """Returns a canned JSON payload — the offline stand-in for a live model."""
    def __init__(self, payload):
        self._payload = payload

    def generate(self, messages, tools, system_prompt, configuration):
        return ModelResponse(content=self._payload)


def store():
    return QuestionSetStore(Path(tempfile.mkdtemp()) / "qs.db")


class GenerationTests(unittest.TestCase):
    def test_valid_questions_persist_and_tag_assumption(self):
        opp, asm = _an_opp_and_weak_link()
        payload = json.dumps({"questions": [
            {"targets_assumption_id": asm, "text": "What do you do today when this happens?",
             "purpose": "behaviour", "question_type": "open_text",
             "follow_up_prompts": ["How often?"]}]})
        st = question_generator.generate_question_set(
            store(), opp, StubModel(payload), _Cfg(), now=NOW)
        self.assertEqual(st["status"], "draft")
        self.assertEqual(len(st["questions"]), 1)
        self.assertEqual(st["questions"][0]["linked_assumption"], asm)
        self.assertEqual(st["questions"][0]["purpose"], "behaviour")
        self.assertTrue(st["questions"][0]["question_id"].endswith("-Q1"))

    def test_invalid_purpose_rejected(self):
        opp, asm = _an_opp_and_weak_link()
        payload = json.dumps({"questions": [
            {"targets_assumption_id": asm, "text": "leading?", "purpose": "not_a_purpose",
             "question_type": "open_text"}]})
        st = question_generator.generate_question_set(store(), opp, StubModel(payload), _Cfg(), now=NOW)
        self.assertEqual(st["questions"], [])
        self.assertEqual(st["rejected_count"], 1)

    def test_invented_assumption_id_rejected(self):
        opp, _ = _an_opp_and_weak_link()
        payload = json.dumps({"questions": [
            {"targets_assumption_id": "ASM-OPP-999-made_up", "text": "q?",
             "purpose": "behaviour", "question_type": "open_text"}]})
        st = question_generator.generate_question_set(store(), opp, StubModel(payload), _Cfg(), now=NOW)
        self.assertEqual(st["questions"], [])
        self.assertGreaterEqual(st["rejected_count"], 1)

    def test_per_link_cap_enforced(self):
        opp, asm = _an_opp_and_weak_link()
        qs = [{"targets_assumption_id": asm, "text": f"question number {i}?",
               "purpose": "behaviour", "question_type": "open_text"} for i in range(5)]
        st = question_generator.generate_question_set(
            store(), opp, StubModel(json.dumps({"questions": qs})), _Cfg(),
            now=NOW, max_per_link=2)
        self.assertLessEqual(len(st["questions"]), 2)

    def test_no_provider_is_honest_gap(self):
        opp, _ = _an_opp_and_weak_link()
        st = question_generator.generate_question_set(store(), opp, None, _Cfg(), now=NOW)
        self.assertEqual(st["questions"], [])
        self.assertIn("no model configured", st["note"])

    def test_malformed_model_output_yields_empty_set_not_error(self):
        opp, _ = _an_opp_and_weak_link()
        st = question_generator.generate_question_set(
            store(), opp, StubModel("not json at all"), _Cfg(), now=NOW)
        self.assertEqual(st["questions"], [])

    def test_missing_opportunity_raises(self):
        with self.assertRaises(FileNotFoundError):
            question_generator.generate_question_set(store(), "OPP-404", None, _Cfg(), now=NOW)


if __name__ == "__main__":
    unittest.main()
