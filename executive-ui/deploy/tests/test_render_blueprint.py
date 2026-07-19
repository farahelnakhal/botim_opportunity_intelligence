"""Render blueprint sanity — the deployed config must be production-shaped:
normal mode, canonical BOTIM_LLM_* configuration, and secrets kept ON
REQUEST (sync: false), never a committed value. Text-based checks only
(stdlib — no PyYAML dependency)."""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RENDER = (REPO / "render.yaml").read_text(encoding="utf-8")


def _block(key):
    """The lines belonging to a `- key: <key>` env var entry."""
    lines = RENDER.splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"\s*-\s*key:\s*{re.escape(key)}\s*$", line):
            out = [line]
            for nxt in lines[i + 1:]:
                if re.match(r"\s*-\s*key:", nxt):
                    break
                out.append(nxt)
            return "\n".join(out)
    return None


class RenderBlueprint(unittest.TestCase):
    def test_app_mode_is_normal_not_demo(self):
        block = _block("BOTIM_APP_MODE")
        self.assertIsNotNone(block, "BOTIM_APP_MODE should be explicit in the blueprint")
        self.assertRegex(block, r"value:\s*normal")

    def test_canonical_llm_vars_present(self):
        for key in ("BOTIM_LLM_BASE_URL", "BOTIM_LLM_MODEL", "BOTIM_LLM_API_KEY"):
            self.assertIsNotNone(_block(key), key)

    def test_api_key_is_on_request_never_a_committed_value(self):
        block = _block("BOTIM_LLM_API_KEY")
        self.assertIn("sync: false", block)
        # a `value:` line would mean a hardcoded secret — never allowed
        self.assertNotRegex(block, r"\n\s*value:")

    def test_no_secret_value_looks_committed_anywhere(self):
        # no bearer-ish/model-key token pattern is ever written as a value
        self.assertNotRegex(RENDER, r"value:\s*(gsk_|sk-ant-|sk-)[A-Za-z0-9]")

    def test_search_provider_key_also_on_request(self):
        block = _block("BRAVE_SEARCH_API_KEY")
        if block is not None:  # optional, but if present must be a secret
            self.assertIn("sync: false", block)
            self.assertNotRegex(block, r"\n\s*value:")

    def test_model_is_a_synthesis_capable_default(self):
        # not the small/instant tier — the product's core value is
        # decision-oriented synthesis (documented in the blueprint comment)
        block = _block("BOTIM_LLM_MODEL")
        self.assertNotRegex(block, r"value:.*8b-instant")

    def test_r6_monitoring_secrets_are_on_request_never_committed(self):
        # the tick token, the unsubscribe signing key, and the SMTP password
        # are real secrets — declared for the deploy but prompted, never a value
        for key in ("MONITORING_TICK_TOKEN", "MONITORING_UNSUBSCRIBE_SIGNING_KEY",
                    "SMTP_HOST", "SMTP_FROM", "SMTP_USERNAME", "SMTP_PASSWORD"):
            block = _block(key)
            self.assertIsNotNone(block, f"{key} should be declared in the blueprint")
            self.assertIn("sync: false", block, key)
            self.assertNotRegex(block, r"\n\s*value:", key)

    def test_r6_safe_defaults_are_committed_values(self):
        # non-secret tunables ship with a committed default so the feature is
        # not inert on deploy (cadence bounds, caps, quota, SMTP transport)
        for key in ("MONITORING_TICK_MAX_CHATS", "MONITORING_MIN_CADENCE_HOURS",
                    "MONITORING_DEFAULT_CADENCE_HOURS", "MONITORING_CONFIRM_TTL_HOURS",
                    "QUOTA_MONITORING_WORKSPACE_RUN_PER_DAY", "SMTP_PORT"):
            block = _block(key)
            self.assertIsNotNone(block, f"{key} should be declared in the blueprint")
            self.assertRegex(block, r"value:\s*\S", key)
            self.assertNotIn("sync: false", block, key)


if __name__ == "__main__":
    unittest.main()
