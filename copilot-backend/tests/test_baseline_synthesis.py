"""PR2 (baseline synthesis) — the answer must be synthesis, not a record
dump: no raw id-list appendix, structured strategic-analysis directives in
the system identity, citations still fully structured. Offline."""

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from app.config import Config                 # noqa: E402
from app.orchestrator import Orchestrator     # noqa: E402
from app.store import ConversationStore       # noqa: E402
from app.system_prompt import SYSTEM_PROMPT   # noqa: E402


def make_orchestrator():
    cfg = Config(env={"COPILOT_PROVIDER": "mock"})
    cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
    return Orchestrator(cfg, ConversationStore(cfg.db_path))


class NoRecordDumpAppendix(unittest.TestCase):
    def test_answer_markdown_has_no_evidence_used_appendix(self):
        o = make_orchestrator()
        r = o.chat("Tell me about OPP-013", conversation_id=None)
        self.assertNotIn("## Evidence used", r["answer_markdown"])
        # the citations themselves are NOT lost — they travel structured
        self.assertTrue(r["citations"], "citations must still be present")
        self.assertTrue(all(c.get("id") and c.get("type") for c in r["citations"]))

    def test_no_decision_banner_still_appended_where_required(self):
        o = make_orchestrator()
        r = o.chat("Tell me about OPP-013", conversation_id=None)
        self.assertIn("No product or build decision has been made.", r["answer_markdown"])


class SynthesisDirectives(unittest.TestCase):
    """The system identity must carry the synthesis rules the live model
    follows. (MockProvider echoes facts by design — production quality comes
    from the live provider consuming these directives.)"""

    def test_private_context_rule_present(self):
        self.assertIn("PRIVATE working context", SYSTEM_PROMPT)
        self.assertIn("Never reproduce it verbatim", SYSTEM_PROMPT)
        self.assertIn("Related records found", SYSTEM_PROMPT)  # named as forbidden

    def test_strategic_analysis_structure_present(self):
        flat = " ".join(SYSTEM_PROMPT.split())  # collapse line wrapping
        for section in ("Executive summary", "Customer problem", "Target segment",
                        "Value proposition", "Supporting evidence", "Differentiation",
                        "Risks and weaknesses", "Assumptions and unknowns",
                        "Recommendation", "Next validation steps"):
            self.assertIn(section, flat, section)

    def test_fact_vs_inference_and_reconciliation_rules_present(self):
        flat = " ".join(SYSTEM_PROMPT.split())
        self.assertIn("reconcile", flat)
        self.assertIn("inferences you are drawing", flat)
        self.assertIn("never assert or imply a product/build decision", flat)


class LiveShapedSynthesisPath(unittest.TestCase):
    """With a (stubbed) live provider, the model's prose IS the answer —
    no appendix is bolted on, wordguard still protects it."""

    def test_stub_live_prose_passes_through_clean(self):
        from shared.llm.provider import ConversationModel, ModelResponse

        class StubLive(ConversationModel):
            def generate(self, messages, tools, system_prompt, configuration):
                return ModelResponse(content=(
                    "## Executive summary\nThe evidence base for OPP-013 remains "
                    "assumption-heavy; the strongest grounded signal is supplier-payment "
                    "friction (EV-2026-W28-014)."))

        cfg = Config(env={"COPILOT_PROVIDER": "mock"})
        cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
        o = Orchestrator(cfg, ConversationStore(cfg.db_path), provider=StubLive())
        r = o.chat("Analyse the value proposition of OPP-013", conversation_id=None)
        self.assertIn("## Executive summary", r["answer_markdown"])
        self.assertNotIn("## Evidence used", r["answer_markdown"])
        self.assertNotIn("Related records found", r["answer_markdown"])

    def test_overclaiming_live_prose_still_rejected_by_wordguard(self):
        from shared.llm.provider import ConversationModel, ModelResponse

        class Overclaimer(ConversationModel):
            def generate(self, messages, tools, system_prompt, configuration):
                return ModelResponse(content=(
                    "The market is validated and merchants will pay — ready to build."))

        cfg = Config(env={"COPILOT_PROVIDER": "mock"})
        cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
        o = Orchestrator(cfg, ConversationStore(cfg.db_path), provider=Overclaimer())
        r = o.chat("Analyse OPP-013", conversation_id=None)
        self.assertTrue(any("wording rejected" in w for w in r["warnings"]), r["warnings"])
        self.assertNotIn("ready to build", r["answer_markdown"])


if __name__ == "__main__":
    unittest.main()
