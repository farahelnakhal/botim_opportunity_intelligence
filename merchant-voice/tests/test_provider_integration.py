"""Gate E verification from the merchant-voice side: this service imports the
canonical shared.llm.provider package directly (a real Python package via the
repository's existing sys.path convention) — no sys.path hacks into the
hyphenated copilot-backend directory, no dynamic/file-based imports, no
duplicated provider implementation.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import RESEARCHER, make_active_campaign_with_approved_guide, make_dbs, make_participant, make_response  # noqa: E402

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

    def test_phase2_modules_never_call_the_provider(self):
        # Phase 2 (participants/consent/responses/csv/transcripts/redaction/
        # suppression) implements the AI-processing consent GATE only —
        # Phase 3 extraction, which would actually call a provider, is not
        # built yet. None of these modules may reference the provider layer.
        phase2_modules = ("participants.py", "consent.py", "responses.py", "csv_import.py",
                          "transcripts.py", "redaction.py", "suppression.py", "identity.py", "counting.py")
        for name in phase2_modules:
            src = (BACKEND / "app" / name).read_text(encoding="utf-8")
            self.assertNotIn("make_provider", src, f"{name} must not call the provider layer")
            self.assertNotIn("shared.llm", src, f"{name} must not import the provider layer")
            self.assertNotIn("ANTHROPIC_API_KEY", src, f"{name} must not reference provider credentials")

    def test_extraction_module_is_the_only_phase3_caller_of_the_provider(self):
        phase3_non_caller_modules = ("eligibility.py", "extraction_prompt.py", "extraction_validate.py")
        for name in phase3_non_caller_modules:
            src = (BACKEND / "app" / name).read_text(encoding="utf-8")
            self.assertNotIn("make_provider", src, f"{name} must not call the provider layer")
        extraction_src = (BACKEND / "app" / "extraction.py").read_text(encoding="utf-8")
        self.assertIn("make_provider", extraction_src)
        self.assertIn("check_eligibility", extraction_src)


class MockProviderOfflineExtractionTests(unittest.TestCase):
    """Full round-trip through app.extraction.run_extraction using the REAL,
    unmodified MockProvider (config.provider == "mock") — proves the whole
    pipeline is offline-safe end to end, independent of any test-only stub."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn, self.identity_conn, self.config = make_dbs(self.tmp.name)
        self.assertEqual(self.config.provider, "mock")
        self.clock_n = 0
        self.camp, self.guide = make_active_campaign_with_approved_guide(self.conn, self.config, self._clock)
        self.participant = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                            self.camp["campaign_id"])
        q1 = self.guide["questions"][0]["question_id"]
        self.response = make_response(self.conn, self.config, self._clock, self.camp, self.guide,
                                      self.participant, [{"question_id": q1, "answer": "a synthetic pain point"}])

    def _clock(self):
        self.clock_n += 1
        return f"2026-01-01T00:00:{self.clock_n:02d}Z"

    def test_mock_provider_extraction_completes_without_network_or_crash(self):
        import socket
        from app import extraction
        from app.eligibility import ExtractionError

        original_connect = socket.socket.connect

        def guard(self, *a, **k):
            raise AssertionError("network connection attempted during MockProvider extraction")

        socket.socket.connect = guard
        try:
            # MockProvider echoes the grounding-facts text (plain prose, not
            # our JSON schema) back verbatim, so this deterministically ends
            # in a safely-handled invalid_provider_output — never a network
            # call, never an unhandled crash.
            with self.assertRaises(ExtractionError) as ctx:
                extraction.run_extraction(self.conn, self.config, RESEARCHER,
                                          self.response["response_id"], self._clock())
        finally:
            socket.socket.connect = original_connect
        self.assertEqual(ctx.exception.code, "invalid_provider_output")
        runs = extraction.list_runs_for_response(self.conn, self.response["response_id"])
        self.assertEqual(runs[-1]["status"], "failed")


@unittest.skipUnless(os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("MV_RUN_LIVE_TESTS") == "1",
                     "live provider test requires ANTHROPIC_API_KEY and MV_RUN_LIVE_TESTS=1")
class LiveExtractionSmoke(unittest.TestCase):
    def test_live_extraction(self):
        from app import extraction
        from app.config import Config

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        conn, identity_conn, config = make_dbs(tmp.name)
        config.provider = "anthropic"
        config.api_key = os.environ["ANTHROPIC_API_KEY"]
        clock_n = [0]

        def clock():
            clock_n[0] += 1
            return f"2026-01-01T00:00:{clock_n[0]:02d}Z"

        camp, guide = make_active_campaign_with_approved_guide(conn, config, clock)
        participant = make_participant(conn, identity_conn, config, clock, camp["campaign_id"])
        q1 = guide["questions"][0]["question_id"]
        response = make_response(conn, config, clock, camp, guide, participant,
                                 [{"question_id": q1, "answer": "We lose money every week to late supplier payments."}])
        run, observations = extraction.run_extraction(conn, config, RESEARCHER, response["response_id"], clock())
        self.assertIn(run["status"], ("completed", "failed"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
