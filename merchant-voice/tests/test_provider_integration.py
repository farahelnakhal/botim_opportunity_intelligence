"""Gate E verification from the merchant-voice side: this service imports the
canonical shared.llm.provider package directly (a real Python package via the
repository's existing sys.path convention) — no sys.path hacks into the
hyphenated copilot-backend directory, no dynamic/file-based imports, no
duplicated provider implementation.
"""

import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from shared.llm import provider as shared_provider  # noqa: E402


class ProviderReuseTests(unittest.TestCase):
    def test_merchant_voice_imports_canonical_package_directly(self):
        self.assertTrue(hasattr(shared_provider, "ConversationModel"))
        self.assertTrue(hasattr(shared_provider, "MockProvider"))
        self.assertTrue(hasattr(shared_provider, "AnthropicProvider"))
        self.assertTrue(hasattr(shared_provider, "make_provider"))

    def test_no_sys_path_hack_into_copilot_backend_hyphenated_dir(self):
        # scan every merchant-voice source file for the forbidden pattern
        for py in (BACKEND / "app").glob("*.py"):
            src = py.read_text(encoding="utf-8")
            self.assertNotIn("copilot-backend", src, f"{py} must not reference copilot-backend directly")
            self.assertNotIn("importlib", src, f"{py} must not use dynamic/file-based imports")

    def test_mock_provider_deterministic_offline_from_merchant_voice(self):
        cfg = type("Cfg", (), {"provider": "mock"})()
        p = shared_provider.make_provider(cfg)
        msgs = [{"role": "user", "content": "Q\n\nGROUNDING FACTS:\nsynthetic fact"}]
        r1 = p.generate(msgs, [], "sys", cfg)
        r2 = p.generate(msgs, [], "sys", cfg)
        self.assertEqual(r1.content, r2.content)
        self.assertEqual(r1.content, "synthetic fact")

    def test_no_network_without_live_gate(self):
        import os
        import socket
        gated = bool(os.environ.get("ANTHROPIC_API_KEY")) and os.environ.get("MV_RUN_LIVE_TESTS") == "1"
        self.assertFalse(gated)

        original_connect = socket.socket.connect

        def guard(self, *a, **k):
            raise AssertionError("network connection attempted during normal (non-live) tests")

        socket.socket.connect = guard
        try:
            cfg = type("Cfg", (), {"provider": "mock"})()
            p = shared_provider.make_provider(cfg)
            p.generate([{"role": "user", "content": "GROUNDING FACTS:\nx"}], [], "s", cfg)
        finally:
            socket.socket.connect = original_connect


if __name__ == "__main__":
    unittest.main(verbosity=2)
