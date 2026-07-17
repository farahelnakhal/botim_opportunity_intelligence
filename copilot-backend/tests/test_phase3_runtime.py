"""Phase 3 — runtime_mode disclosure (MockProvider vs a live model must be
distinguishable to the frontend) and the conversation_not_found error
contract used for stale-conversation recovery. MockProvider / a fake stub
provider only — zero network in either case.
"""

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from app.config import Config                  # noqa: E402
from app.orchestrator import Orchestrator       # noqa: E402
from app.store import ConversationStore         # noqa: E402
from shared.llm.provider import ConversationModel, ModelResponse  # noqa: E402


def make_store():
    return ConversationStore(Path(tempfile.mkdtemp()) / "conv.db")


class FakeLiveProvider(ConversationModel):
    """A stub standing in for a real model provider in tests — deterministic,
    zero network, but NOT MockProvider, so it exercises the "live_model"
    runtime_mode branch without ever touching the internet or requiring a key."""

    def generate(self, messages, tools, system_prompt, configuration):
        for m in reversed(messages):
            if m["role"] == "user" and "GROUNDING FACTS:" in m["content"]:
                facts = m["content"].split("GROUNDING FACTS:", 1)[1].strip()
                return ModelResponse(content=f"(live) {facts}")
        return ModelResponse(content="(live) no facts")


class RuntimeMode(unittest.TestCase):
    def test_mock_provider_reports_deterministic_demo(self):
        cfg = Config(env={"COPILOT_PROVIDER": "mock"})
        cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
        o = Orchestrator(cfg, ConversationStore(cfg.db_path))
        r = o.chat("Tell me about OPP-013", conversation_id=None)
        self.assertEqual(r["runtime_mode"], "deterministic_demo")

    def test_fake_live_provider_reports_live_model(self):
        cfg = Config(env={"COPILOT_PROVIDER": "mock"})  # config value irrelevant; provider is injected
        cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
        o = Orchestrator(cfg, ConversationStore(cfg.db_path), provider=FakeLiveProvider())
        r = o.chat("Tell me about OPP-013", conversation_id=None)
        self.assertEqual(r["runtime_mode"], "live_model")

    def test_runtime_mode_present_on_clarification_and_error_shortcircuits(self):
        cfg = Config(env={"COPILOT_PROVIDER": "mock"})
        cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
        o = Orchestrator(cfg, ConversationStore(cfg.db_path))
        r = o.chat("Hello", conversation_id=None)
        self.assertEqual(r["runtime_mode"], "deterministic_demo")

    def test_runtime_mode_never_exposes_key_or_provider_class(self):
        cfg = Config(env={"COPILOT_PROVIDER": "mock"})
        cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
        o = Orchestrator(cfg, ConversationStore(cfg.db_path))
        r = o.chat("Hello", conversation_id=None)
        blob = str(r)
        for leak in ("api_key", "ANTHROPIC_API_KEY", "MockProvider", "AnthropicProvider", "sk-ant"):
            self.assertNotIn(leak, blob)


class CanonicalLlmConfig(unittest.TestCase):
    """BOTIM_LLM_* is canonical; mock is explicit-only; health reports the
    active provider/model without secrets."""

    def test_health_route_reports_active_provider_and_model(self):
        from app.api import Api
        cfg = Config(env={"COPILOT_PROVIDER": "mock"})
        cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
        store = ConversationStore(cfg.db_path)
        api = Api(Orchestrator(cfg, store), store)
        status, body = api.handle("GET", "/api/health", b"")
        self.assertEqual(status, 200)
        self.assertEqual(body["provider"], "mock")
        self.assertEqual(body["runtime_mode"], "deterministic_demo")
        self.assertTrue(body["llm_configured"])
        blob = str(body)
        for leak in ("sk-ant", "api_key", "ANTHROPIC_API_KEY=", "Bearer"):
            self.assertNotIn(leak, blob)

    def test_unconfigured_chat_fails_honestly_never_mock(self):
        cfg = Config(env={})  # no key, no explicit provider
        cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
        self.assertEqual(cfg.provider, "unconfigured")
        o = Orchestrator(cfg, ConversationStore(cfg.db_path))
        r = o.chat("Tell me about OPP-013", conversation_id=None)
        self.assertIn("error", r)
        self.assertEqual(r["error"]["code"], "provider_error")

    def test_botim_llm_vars_drive_the_copilot_config(self):
        cfg = Config(env={"BOTIM_LLM_API_KEY": "gsk_x",
                          "BOTIM_LLM_MODEL": "llama-3.3-70b",
                          "BOTIM_LLM_BASE_URL": "https://api.groq.com/openai/v1"})
        self.assertEqual(cfg.provider, "openai_compatible")
        self.assertEqual(cfg.model, "llama-3.3-70b")


class ConversationNotFound(unittest.TestCase):
    def test_unknown_conversation_id_returns_conversation_not_found(self):
        cfg = Config(env={"COPILOT_PROVIDER": "mock"})
        cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
        o = Orchestrator(cfg, ConversationStore(cfg.db_path))
        r = o.chat("hello again", conversation_id="conv_doesnotexist000")
        self.assertIn("error", r)
        self.assertEqual(r["error"]["code"], "conversation_not_found")
        self.assertFalse(r["error"]["retryable"])

    def test_conversation_not_found_maps_to_404(self):
        from app.api import ERROR_STATUS
        self.assertEqual(ERROR_STATUS["conversation_not_found"], 404)

    def test_existing_conversation_id_still_works(self):
        cfg = Config(env={"COPILOT_PROVIDER": "mock"})
        cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
        o = Orchestrator(cfg, ConversationStore(cfg.db_path))
        first = o.chat("Tell me about OPP-013", conversation_id=None)
        second = o.chat("What else?", conversation_id=first["conversation_id"])
        self.assertNotIn("error", second)
        self.assertEqual(second["conversation_id"], first["conversation_id"])


if __name__ == "__main__":
    unittest.main()
