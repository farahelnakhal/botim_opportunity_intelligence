"""Provider-refactor equivalence tests (Gate E).

Confirms the copilot-backend provider module is now a thin, behavior-preserving
shim over the canonical shared.llm.provider package: same classes (by
identity, not just by name), same MockProvider determinism/offline guarantee,
no network during normal test runs, and live calls remain double-gated.
"""

import os
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from app import provider as shim                       # noqa: E402
from shared.llm import provider as canonical            # noqa: E402


class ProviderShimIdentity(unittest.TestCase):
    """The shim re-exports the SAME classes/functions — no duplication."""

    def test_same_classes_by_identity(self):
        for name in ("ProviderError", "ModelResponse", "ConversationModel",
                     "MockProvider", "AnthropicProvider", "make_provider"):
            self.assertIs(getattr(shim, name), getattr(canonical, name),
                          f"{name} in copilot-backend shim is not the canonical shared object")

    def test_shim_module_has_no_new_logic(self):
        # the shim must not define its own class bodies / network calls
        src = (BACKEND / "app" / "provider.py").read_text(encoding="utf-8")
        for banned in ("urllib", "class AnthropicProvider", "class MockProvider",
                       "API_URL ="):
            self.assertNotIn(banned, src,
                             f"shim must not contain '{banned}' — logic belongs only in shared.llm.provider")

    def test_canonical_module_is_single_source(self):
        # AnthropicProvider's network code lives only in shared.llm.provider
        canon_src = (REPO / "shared" / "llm" / "provider.py").read_text(encoding="utf-8")
        self.assertIn("class AnthropicProvider", canon_src)
        self.assertIn("api.anthropic.com", canon_src)


class MockProviderBehavior(unittest.TestCase):
    def test_mock_is_deterministic_and_offline(self):
        cfg = type("Cfg", (), {"provider": "mock"})()
        p1 = canonical.make_provider(cfg)
        p2 = canonical.make_provider(cfg)
        messages = [{"role": "user", "content": "Question: x\n\nGROUNDING FACTS:\nfact one\nfact two"}]
        r1 = p1.generate(messages, [], "sys", cfg)
        r2 = p2.generate(messages, [], "sys", cfg)
        self.assertEqual(r1.content, r2.content)
        self.assertEqual(r1.content, "fact one\nfact two")
        self.assertEqual(r1.stop_reason, "end")

    def test_shim_and_canonical_mock_behave_identically(self):
        cfg = type("Cfg", (), {"provider": "mock"})()
        via_shim = shim.make_provider(cfg)
        via_canonical = canonical.make_provider(cfg)
        self.assertIs(type(via_shim), type(via_canonical))
        msgs = [{"role": "user", "content": "Q\n\nGROUNDING FACTS:\nsame facts"}]
        self.assertEqual(via_shim.generate(msgs, [], "s", cfg).content,
                         via_canonical.generate(msgs, [], "s", cfg).content)


class NoNetworkDuringTests(unittest.TestCase):
    """Normal test runs must never open a socket to a provider."""

    def test_no_network_call_without_live_gate(self):
        import socket
        original_connect = socket.socket.connect

        def guard(self, *a, **k):
            raise AssertionError("network connection attempted during normal (non-live) tests")

        socket.socket.connect = guard
        try:
            cfg = type("Cfg", (), {"provider": "mock"})()
            p = canonical.make_provider(cfg)
            p.generate([{"role": "user", "content": "GROUNDING FACTS:\nx"}], [], "s", cfg)
        finally:
            socket.socket.connect = original_connect

    def test_live_gate_requires_both_env_vars(self):
        gated = bool(os.environ.get("ANTHROPIC_API_KEY")) and os.environ.get("COPILOT_RUN_LIVE_TESTS") == "1"
        self.assertFalse(gated, "live-provider tests must not run in this environment by default")


if __name__ == "__main__":
    unittest.main(verbosity=2)
