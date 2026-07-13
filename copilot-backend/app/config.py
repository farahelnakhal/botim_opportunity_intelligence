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
        self.provider = e.get("COPILOT_PROVIDER", "anthropic")
        self.model = e.get("COPILOT_MODEL", "claude-sonnet-5")
        self.api_key = e.get("ANTHROPIC_API_KEY", "")
        self.timeout_s = _int("COPILOT_TIMEOUT_S", 60) if env is None else int(e.get("COPILOT_TIMEOUT_S", 60))
        self.max_history = int(e.get("COPILOT_MAX_HISTORY", 20))
        self.max_tool_iterations = int(e.get("COPILOT_MAX_TOOL_ITERATIONS", 3))
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

    def require_token(self):
        """Non-local binds require an API token; refuse to start otherwise."""
        return self.host not in ("127.0.0.1", "localhost", "::1")
