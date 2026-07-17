"""Provider-neutral conversation-model interface (canonical implementation).

This is the single, canonical home for the model-provider abstraction used by
every backend service in this repository (copilot-backend, merchant-voice,
and any future service). Everything vendor-specific — request shape, headers,
response parsing, tool-call parsing, stop-reason mapping, error mapping —
lives inside the provider classes ONLY. Callers (orchestrators, tool
registries, APIs, storage, tests) depend only on the neutral
ConversationModel interface and MUST NOT branch on provider identity.

Canonical configuration (vendor-neutral — see resolve_llm_env below):

    BOTIM_LLM_API_KEY    the model API key (required for any live provider)
    BOTIM_LLM_MODEL      the model name
    BOTIM_LLM_BASE_URL   OpenAI-compatible endpoint base (Groq, Ollama,
                         vLLM, OpenAI, …) — required unless the target is
                         inferable (a claude-* model / sk-ant- key means
                         Anthropic; GROQ_API_KEY implies the Groq endpoint)
    BOTIM_LLM_PROVIDER   explicit override: anthropic | openai_compatible |
                         mock (mock is ONLY ever selected explicitly — a
                         missing key never silently degrades to mock)

Vendor-specific variables are OPTIONAL ALIASES that resolve into the
canonical values, never independent configuration: ANTHROPIC_API_KEY and
GROQ_API_KEY alias BOTIM_LLM_API_KEY; COPILOT_MODEL aliases BOTIM_LLM_MODEL;
COPILOT_PROVIDER aliases BOTIM_LLM_PROVIDER (kept for tests/back-compat).

Import this module as `shared.llm.provider` (a real Python package — no
sys.path manipulation, no dynamic/file-based imports, no reaching into
hyphenated directories). copilot-backend/app/provider.py re-exports these
names for backward compatibility only; new code must import from here.
"""

import json
import os
import urllib.error
import urllib.request

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# Descriptive client identifier sent on every live request — API vendors use
# it to identify the calling application (matches the research module's
# convention). Never contains secrets.
USER_AGENT = "BOTIM-Opportunity-Intelligence-copilot/1.0"


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
                     "anthropic-version": self.VERSION,
                     "user-agent": USER_AGENT},
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


class OpenAICompatibleProvider(ConversationModel):
    """Any OpenAI-chat-completions-compatible endpoint (Groq, OpenAI, Ollama,
    LM Studio, vLLM, …). Requires configuration.base_url. Tool use maps to
    the OpenAI 'tools'/'tool_calls' function-calling format; endpoints that
    reject the tools parameter get one retry without tools (the deterministic
    grounding tool plan has already run — model-initiated tools are a bonus,
    not a requirement)."""

    def __init__(self, fetch_fn=None):
        self._fetch = fetch_fn  # (url, body_bytes, headers, timeout_s) -> bytes

    def _http(self, url, body, headers, timeout_s):
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.read()

    def generate(self, messages, tools, system_prompt, configuration):
        if not configuration.api_key:
            raise ProviderError("no API key configured (set BOTIM_LLM_API_KEY)",
                                retryable=False)
        base_url = (getattr(configuration, "base_url", "") or "").rstrip("/")
        if not base_url:
            raise ProviderError(
                "BOTIM_LLM_BASE_URL is required for an OpenAI-compatible provider "
                "(or set BOTIM_LLM_PROVIDER=anthropic for a claude model)",
                retryable=False)
        oai_messages = [{"role": "system", "content": system_prompt}]
        oai_messages += [{"role": m["role"], "content": m["content"]} for m in messages]
        body = {"model": configuration.model, "max_tokens": 2048,
                "messages": oai_messages}
        if tools:
            body["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t["description"],
                "parameters": t["input_schema"]}} for t in tools]
        headers = {"content-type": "application/json",
                   "authorization": f"Bearer {configuration.api_key}",
                   "user-agent": USER_AGENT}
        fetch = self._fetch or self._http
        url = f"{base_url}/chat/completions"
        for attempt in (1, 2):
            try:
                raw = fetch(url, json.dumps(body).encode("utf-8"), headers,
                            configuration.timeout_s)
                break
            except urllib.error.HTTPError as exc:
                # some compatible endpoints reject function calling — retry
                # once without tools before giving up
                if exc.code == 400 and attempt == 1 and "tools" in body:
                    body.pop("tools", None)
                    continue
                retryable = exc.code in (429, 500, 502, 503, 529)
                raise ProviderError(f"provider HTTP {exc.code}", retryable=retryable)
            except TimeoutError:
                raise ProviderError("provider timeout", retryable=True, timeout=True)
            except urllib.error.URLError as exc:
                if isinstance(getattr(exc, "reason", None), TimeoutError):
                    raise ProviderError("provider timeout", retryable=True, timeout=True)
                raise ProviderError("provider unreachable", retryable=True)
        try:
            data = json.loads(raw.decode("utf-8"))
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            raise ProviderError("provider returned a malformed response", retryable=True)
        tool_calls = []
        for call in message.get("tool_calls") or []:
            fn = call.get("function") or {}
            try:
                arguments = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append({"id": call.get("id", ""), "name": fn.get("name", ""),
                               "arguments": arguments if isinstance(arguments, dict) else {}})
        stop = "tool_use" if (tool_calls and choice.get("finish_reason") == "tool_calls") else "end"
        return ModelResponse(content=message.get("content") or "", tool_calls=tool_calls,
                             stop_reason=stop, usage=data.get("usage", {}))


class UnconfiguredProvider(ConversationModel):
    """Selected when NO live key is configured and mock was not explicitly
    requested. Every call fails honestly — a missing key must never silently
    degrade to deterministic demo output outside demo/test mode."""

    def generate(self, messages, tools, system_prompt, configuration):
        raise ProviderError(
            "no model provider is configured — set BOTIM_LLM_API_KEY (+ "
            "BOTIM_LLM_MODEL, and BOTIM_LLM_BASE_URL for non-Anthropic "
            "endpoints), or run with BOTIM_LLM_PROVIDER=mock for the "
            "deterministic demo responder", retryable=False)


def resolve_llm_env(env=None):
    """The canonical LLM configuration from the environment.

    Returns {provider, api_key, model, base_url, source}. `source` is a safe
    human-readable note (which variables drove the resolution — never the
    key itself) for startup logs and health checks.

    Resolution order:
      1. api_key: BOTIM_LLM_API_KEY, else alias ANTHROPIC_API_KEY, else
         alias GROQ_API_KEY (which also implies the Groq base URL).
      2. model: BOTIM_LLM_MODEL, else alias COPILOT_MODEL, else the
         Anthropic default (only meaningful for the anthropic provider).
      3. base_url: BOTIM_LLM_BASE_URL (else the Groq default when the key
         came from GROQ_API_KEY).
      4. provider: BOTIM_LLM_PROVIDER, else alias COPILOT_PROVIDER, else
         inferred — base_url -> openai_compatible; sk-ant-/claude-* ->
         anthropic; any other key -> openai_compatible (its generate() will
         demand a base_url with a clear message); no key -> unconfigured.
    Mock is never inferred: it must be requested explicitly.
    """
    e = env if env is not None else os.environ
    key_source = None
    api_key = e.get("BOTIM_LLM_API_KEY") or ""
    if api_key:
        key_source = "BOTIM_LLM_API_KEY"
    elif e.get("ANTHROPIC_API_KEY"):
        api_key, key_source = e["ANTHROPIC_API_KEY"], "ANTHROPIC_API_KEY (alias)"
    elif e.get("GROQ_API_KEY"):
        api_key, key_source = e["GROQ_API_KEY"], "GROQ_API_KEY (alias)"

    model = e.get("BOTIM_LLM_MODEL") or e.get("COPILOT_MODEL") or DEFAULT_ANTHROPIC_MODEL
    base_url = e.get("BOTIM_LLM_BASE_URL") or ""
    if not base_url and key_source == "GROQ_API_KEY (alias)":
        base_url = GROQ_BASE_URL

    provider = (e.get("BOTIM_LLM_PROVIDER") or e.get("COPILOT_PROVIDER") or "").strip().lower()
    if not provider:
        if not api_key:
            provider = "unconfigured"
        elif base_url:
            provider = "openai_compatible"
        elif api_key.startswith("sk-ant") or model.lower().startswith("claude"):
            provider = "anthropic"
        else:
            provider = "openai_compatible"
    source = (f"provider={provider}"
              + (f", key from {key_source}" if key_source else ", no API key")
              + (f", base_url set" if base_url else ""))
    return {"provider": provider, "api_key": api_key, "model": model,
            "base_url": base_url, "source": source}


def make_provider(configuration):
    if configuration.provider == "mock":
        return MockProvider()
    if configuration.provider == "anthropic":
        return AnthropicProvider()
    if configuration.provider == "openai_compatible":
        return OpenAICompatibleProvider()
    if configuration.provider == "unconfigured":
        return UnconfiguredProvider()
    raise ProviderError(f"unknown provider '{configuration.provider}'", retryable=False)
