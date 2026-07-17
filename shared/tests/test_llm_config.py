"""Canonical BOTIM_LLM_* configuration resolution + the OpenAI-compatible
provider. Offline (injected fetch); mock is only ever explicit."""

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.llm import provider as llm  # noqa: E402


class Resolution(unittest.TestCase):
    def test_canonical_variables_win(self):
        r = llm.resolve_llm_env({"BOTIM_LLM_API_KEY": "k1", "BOTIM_LLM_MODEL": "m1",
                                 "BOTIM_LLM_BASE_URL": "https://llm.example/v1",
                                 "ANTHROPIC_API_KEY": "ignored"})
        self.assertEqual((r["provider"], r["api_key"], r["model"], r["base_url"]),
                         ("openai_compatible", "k1", "m1", "https://llm.example/v1"))
        self.assertIn("BOTIM_LLM_API_KEY", r["source"])
        self.assertNotIn("k1", r["source"])  # source note never carries the key

    def test_anthropic_key_is_an_alias_only(self):
        r = llm.resolve_llm_env({"ANTHROPIC_API_KEY": "sk-ant-xyz"})
        self.assertEqual(r["provider"], "anthropic")
        self.assertEqual(r["api_key"], "sk-ant-xyz")
        self.assertIn("alias", r["source"])

    def test_groq_alias_implies_the_groq_endpoint(self):
        r = llm.resolve_llm_env({"GROQ_API_KEY": "gk", "BOTIM_LLM_MODEL": "llama-3.3-70b"})
        self.assertEqual(r["provider"], "openai_compatible")
        self.assertEqual(r["base_url"], llm.GROQ_BASE_URL)

    def test_claude_model_infers_anthropic_without_base_url(self):
        r = llm.resolve_llm_env({"BOTIM_LLM_API_KEY": "any-key",
                                 "BOTIM_LLM_MODEL": "claude-sonnet-5"})
        self.assertEqual(r["provider"], "anthropic")

    def test_non_claude_key_without_base_url_resolves_openai_compatible(self):
        r = llm.resolve_llm_env({"BOTIM_LLM_API_KEY": "gsk_abc",
                                 "BOTIM_LLM_MODEL": "llama-3.3-70b"})
        self.assertEqual(r["provider"], "openai_compatible")
        self.assertEqual(r["base_url"], "")  # generate() demands it with a clear message

    def test_no_key_is_unconfigured_never_mock(self):
        r = llm.resolve_llm_env({})
        self.assertEqual(r["provider"], "unconfigured")

    def test_mock_is_only_ever_explicit(self):
        self.assertEqual(llm.resolve_llm_env({"BOTIM_LLM_PROVIDER": "mock"})["provider"], "mock")
        self.assertEqual(llm.resolve_llm_env({"COPILOT_PROVIDER": "mock"})["provider"], "mock")

    def test_explicit_provider_overrides_inference(self):
        r = llm.resolve_llm_env({"BOTIM_LLM_PROVIDER": "anthropic",
                                 "BOTIM_LLM_API_KEY": "k", "BOTIM_LLM_MODEL": "x",
                                 "BOTIM_LLM_BASE_URL": "https://ignored.example"})
        self.assertEqual(r["provider"], "anthropic")


class _Cfg:
    def __init__(self, **kw):
        self.provider = kw.get("provider", "openai_compatible")
        self.api_key = kw.get("api_key", "k")
        self.model = kw.get("model", "m")
        self.base_url = kw.get("base_url", "https://llm.example/v1")
        self.timeout_s = 5


class MakeProvider(unittest.TestCase):
    def test_all_provider_names_construct(self):
        self.assertIsInstance(llm.make_provider(_Cfg(provider="mock")), llm.MockProvider)
        self.assertIsInstance(llm.make_provider(_Cfg(provider="anthropic")), llm.AnthropicProvider)
        self.assertIsInstance(llm.make_provider(_Cfg(provider="openai_compatible")),
                              llm.OpenAICompatibleProvider)
        self.assertIsInstance(llm.make_provider(_Cfg(provider="unconfigured")),
                              llm.UnconfiguredProvider)

    def test_unconfigured_fails_honestly_naming_the_canonical_variable(self):
        with self.assertRaises(llm.ProviderError) as cm:
            llm.make_provider(_Cfg(provider="unconfigured")).generate([], [], "s", _Cfg())
        self.assertIn("BOTIM_LLM_API_KEY", str(cm.exception))


class OpenAICompatible(unittest.TestCase):
    def _provider(self, responses):
        calls = []

        def fetch(url, body, headers, timeout_s):
            calls.append((url, json.loads(body.decode()), headers))
            result = responses[min(len(calls) - 1, len(responses) - 1)]
            if isinstance(result, Exception):
                raise result
            return json.dumps(result).encode()
        return llm.OpenAICompatibleProvider(fetch_fn=fetch), calls

    def test_maps_messages_system_prompt_and_parses_content(self):
        p, calls = self._provider([{"choices": [{"message": {"content": "synthesized"},
                                                 "finish_reason": "stop"}]}])
        resp = p.generate([{"role": "user", "content": "q"}], [], "SYS", _Cfg())
        self.assertEqual(resp.content, "synthesized")
        url, body, headers = calls[0]
        self.assertTrue(url.endswith("/chat/completions"))
        self.assertEqual(body["messages"][0], {"role": "system", "content": "SYS"})
        self.assertEqual(headers["authorization"], "Bearer k")

    def test_parses_openai_tool_calls(self):
        p, _ = self._provider([{"choices": [{"finish_reason": "tool_calls", "message": {
            "content": None, "tool_calls": [{"id": "c1", "function": {
                "name": "get_opportunity", "arguments": "{\"opp_id\": \"OPP-010\"}"}}]}}]}])
        resp = p.generate([{"role": "user", "content": "q"}],
                          [{"name": "get_opportunity", "description": "d",
                            "input_schema": {"type": "object"}}], "SYS", _Cfg())
        self.assertEqual(resp.stop_reason, "tool_use")
        self.assertEqual(resp.tool_calls[0]["name"], "get_opportunity")
        self.assertEqual(resp.tool_calls[0]["arguments"], {"opp_id": "OPP-010"})

    def test_retries_once_without_tools_on_http_400(self):
        import urllib.error
        err = urllib.error.HTTPError("u", 400, "bad tools", {}, None)
        p, calls = self._provider([err, {"choices": [{"message": {"content": "ok"},
                                                      "finish_reason": "stop"}]}])
        resp = p.generate([{"role": "user", "content": "q"}],
                          [{"name": "t", "description": "d",
                            "input_schema": {"type": "object"}}], "SYS", _Cfg())
        self.assertEqual(resp.content, "ok")
        self.assertIn("tools", calls[0][1])
        self.assertNotIn("tools", calls[1][1])

    def test_missing_base_url_fails_with_clear_message(self):
        p = llm.OpenAICompatibleProvider(fetch_fn=lambda *a: b"{}")
        with self.assertRaises(llm.ProviderError) as cm:
            p.generate([], [], "s", _Cfg(base_url=""))
        self.assertIn("BOTIM_LLM_BASE_URL", str(cm.exception))

    def test_malformed_response_is_a_provider_error_not_a_crash(self):
        p = llm.OpenAICompatibleProvider(fetch_fn=lambda *a: b"not json")
        with self.assertRaises(llm.ProviderError):
            p.generate([{"role": "user", "content": "q"}], [], "s", _Cfg())


class ServiceConfigs(unittest.TestCase):
    def test_copilot_config_uses_canonical_resolution(self):
        sys.path.insert(0, str(REPO / "copilot-backend"))
        from app.config import Config
        cfg = Config(env={"BOTIM_LLM_API_KEY": "k", "BOTIM_LLM_MODEL": "llama-3.3-70b",
                          "BOTIM_LLM_BASE_URL": "https://llm.example/v1"})
        self.assertEqual(cfg.provider, "openai_compatible")
        self.assertEqual(cfg.model, "llama-3.3-70b")
        self.assertEqual(cfg.base_url, "https://llm.example/v1")
        # back-compat: tests everywhere still get mock via COPILOT_PROVIDER
        self.assertEqual(Config(env={"COPILOT_PROVIDER": "mock"}).provider, "mock")
        # no key + no explicit provider = unconfigured, never mock
        self.assertEqual(Config(env={}).provider, "unconfigured")


if __name__ == "__main__":
    unittest.main()
