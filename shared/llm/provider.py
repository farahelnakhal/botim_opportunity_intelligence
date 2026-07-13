"""Provider-neutral conversation-model interface (canonical implementation).

This is the single, canonical home for the model-provider abstraction used by
every backend service in this repository (copilot-backend, merchant-voice,
and any future service). Everything Anthropic-specific — request shape,
headers, response parsing, tool-call parsing, stop-reason mapping, usage
parsing, error mapping — lives inside AnthropicProvider ONLY. Callers
(orchestrators, tool registries, APIs, storage, tests) depend only on the
neutral ConversationModel interface and MUST NOT branch on provider identity.

Import this module as `shared.llm.provider` (a real Python package — no
sys.path manipulation, no dynamic/file-based imports, no reaching into
hyphenated directories). copilot-backend/app/provider.py re-exports these
names for backward compatibility only; new code must import from here.
"""

import json
import urllib.error
import urllib.request


class ProviderError(Exception):
    def __init__(self, message, retryable=False, timeout=False):
        super().__init__(message)
        self.retryable = retryable
        self.timeout = timeout


class ModelResponse:
    def __init__(self, content="", tool_calls=None, stop_reason="end", usage=None):
        self.content = content
        self.tool_calls = tool_calls or []   # [{"name":…, "arguments":{…}, "id":…}]
        self.stop_reason = stop_reason        # "end" | "tool_use"
        self.usage = usage or {}


class ConversationModel:
    """Interface: generate(messages, tools, system_prompt, configuration)."""

    def generate(self, messages, tools, system_prompt, configuration):
        raise NotImplementedError


class MockProvider(ConversationModel):
    """Deterministic offline provider for tests and keyless development.

    Echoes the GROUNDING FACTS block the caller supplies, so answers are
    exactly the deterministic grounded content (no network, no variability).
    """

    def generate(self, messages, tools, system_prompt, configuration):
        for m in reversed(messages):
            if m["role"] == "user" and "GROUNDING FACTS:" in m["content"]:
                facts = m["content"].split("GROUNDING FACTS:", 1)[1].strip()
                return ModelResponse(content=facts)
        return ModelResponse(content="I could not find grounded facts for this question.")


class AnthropicProvider(ConversationModel):
    API_URL = "https://api.anthropic.com/v1/messages"
    VERSION = "2023-06-01"

    def generate(self, messages, tools, system_prompt, configuration):
        if not configuration.api_key:
            raise ProviderError("no API key configured", retryable=False)
        body = {
            "model": configuration.model,
            "max_tokens": 2048,
            "system": system_prompt,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        }
        if tools:
            body["tools"] = [{"name": t["name"], "description": t["description"],
                              "input_schema": t["input_schema"]} for t in tools]
        req = urllib.request.Request(
            self.API_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={"content-type": "application/json",
                     "x-api-key": configuration.api_key,
                     "anthropic-version": self.VERSION},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=configuration.timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            retryable = exc.code in (429, 500, 502, 503, 529)
            raise ProviderError(f"provider HTTP {exc.code}", retryable=retryable)
        except TimeoutError:
            raise ProviderError("provider timeout", retryable=True, timeout=True)
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                raise ProviderError("provider timeout", retryable=True, timeout=True)
            raise ProviderError("provider unreachable", retryable=True)

        text, tool_calls = [], []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append({"id": block.get("id", ""), "name": block.get("name", ""),
                                   "arguments": block.get("input", {}) or {}})
        stop = "tool_use" if data.get("stop_reason") == "tool_use" else "end"
        return ModelResponse(content="\n".join(text), tool_calls=tool_calls,
                             stop_reason=stop, usage=data.get("usage", {}))


def make_provider(configuration):
    if configuration.provider == "mock":
        return MockProvider()
    if configuration.provider == "anthropic":
        return AnthropicProvider()
    raise ProviderError(f"unknown provider '{configuration.provider}'", retryable=False)
