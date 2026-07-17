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


if __name__ == "__main__":
    unittest.main()
