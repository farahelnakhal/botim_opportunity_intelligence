"""Environment-driven configuration. No secrets are ever logged or echoed."""

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class Config:
    def __init__(self, env=None):
        e = env if env is not None else os.environ
        # Canonical, vendor-neutral LLM configuration (BOTIM_LLM_API_KEY /
        # BOTIM_LLM_MODEL / BOTIM_LLM_BASE_URL / BOTIM_LLM_PROVIDER), with
        # ANTHROPIC_API_KEY / GROQ_API_KEY / COPILOT_MODEL / COPILOT_PROVIDER
        # as optional aliases — see shared.llm.provider.resolve_llm_env.
        # Mock is only ever selected explicitly, never because a key is absent.
        from shared.llm.provider import resolve_llm_env
        llm = resolve_llm_env(e)
        self.provider = llm["provider"]
        self.model = llm["model"]
        self.api_key = llm["api_key"]
        self.base_url = llm["base_url"]
        self.llm_source = llm["source"]  # safe note for logs/health — never the key
        self.timeout_s = _int("COPILOT_TIMEOUT_S", 60) if env is None else int(e.get("COPILOT_TIMEOUT_S", 60))
        self.max_history = int(e.get("COPILOT_MAX_HISTORY", 20))
        self.max_tool_iterations = int(e.get("COPILOT_MAX_TOOL_ITERATIONS", 3))
        # Bounded retry for RETRYABLE provider failures (429 rate limits,
        # transient 5xx, timeouts). Kept small and capped so total time stays
        # well within the executive-API proxy's 30s budget — a persistent
        # outage still surfaces honestly rather than hanging.
        self.max_provider_retries = int(e.get("COPILOT_PROVIDER_MAX_RETRIES", 2))
        self.provider_retry_base_s = float(e.get("COPILOT_PROVIDER_RETRY_BASE_S", 0.75))
        self.provider_retry_max_s = float(e.get("COPILOT_PROVIDER_RETRY_MAX_S", 4.0))
        self.max_response_chars = int(e.get("COPILOT_MAX_RESPONSE_CHARS", 20000))
        self.max_message_chars = int(e.get("COPILOT_MAX_MESSAGE_CHARS", 4000))
        self.max_body_bytes = int(e.get("COPILOT_MAX_BODY_BYTES", 65536))
        self.host = e.get("COPILOT_HOST", "127.0.0.1")
        self.port = int(e.get("COPILOT_PORT", 8010))
        self.cors_origin = e.get("COPILOT_CORS_ORIGIN", "http://localhost:8000")
        self.api_token = e.get("COPILOT_API_TOKEN", "")
        self.debug_trace = e.get("COPILOT_DEBUG_TRACE", "") == "1"
        self.max_concurrency = int(e.get("COPILOT_MAX_CONCURRENCY", 4))
        self.db_path = Path(e.get("COPILOT_DB_PATH", BACKEND_ROOT / "data" / "conversations.db"))
        # Merchant Voice's mv.db, opened READ-ONLY (see app/mv_tools.py) —
        # never identity.db, never read-write.
        self.mv_db_path = Path(e.get("COPILOT_MV_DB_PATH", REPO_ROOT / "merchant-voice" / "data" / "mv.db"))

    def require_token(self):
        """Non-local binds require an API token; refuse to start otherwise."""
        return self.host not in ("127.0.0.1", "localhost", "::1")
