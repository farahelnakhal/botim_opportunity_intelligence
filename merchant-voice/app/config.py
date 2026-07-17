"""Environment-driven configuration for the Merchant Voice backend.

PROTOTYPE-GRADE: token-to-role auth only, no user directory, no session
revocation, no TLS termination. Synthetic-data-only by default. Secrets are
never logged; token values are read but never echoed back anywhere.
"""

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

VALID_ROLES = ("viewer", "researcher", "reviewer", "admin")


def _int(e, name, default):
    try:
        return int(e.get(name, default))
    except (TypeError, ValueError):
        return default


def _bool(e, name, default=False):
    return e.get(name, "1" if default else "0") == "1"


class Config:
    def __init__(self, env=None):
        e = env if env is not None else os.environ

        self.host = e.get("MV_HOST", "127.0.0.1")
        self.port = _int(e, "MV_PORT", 8020)
        self.cors_origin = e.get("MV_CORS_ORIGIN", "http://localhost:8000")

        self.db_path = Path(e.get("MV_DB_PATH", BACKEND_ROOT / "data" / "mv.db"))
        self.identity_db_path = Path(e.get("MV_IDENTITY_DB_PATH", BACKEND_ROOT / "data" / "identity.db"))
        self.transcript_dir = Path(e.get("MV_TRANSCRIPT_DIR", BACKEND_ROOT / "data" / "transcripts"))
        # Root that Phase 5 synthetic-only export resolves
        # knowledge-base/customer-evidence/merchant-voice-candidates/ under.
        # Defaults to the real repo root; tests override this to a tmp dir
        # so exports never touch the real knowledge-base.
        self.export_root = Path(e.get("MV_EXPORT_ROOT", REPO_ROOT))

        self.max_body_bytes = _int(e, "MV_MAX_BODY_BYTES", 5 * 1024 * 1024)
        self.max_concurrency = _int(e, "MV_MAX_CONCURRENCY", 4)

        # Canonical BOTIM_LLM_* configuration with MV_PROVIDER/MV_MODEL as
        # service-local overrides (Merchant Voice keeps its safe default of
        # mock — extraction on a live model is an explicit opt-in here).
        from shared.llm.provider import resolve_llm_env
        llm = resolve_llm_env(e)
        self.provider = e.get("MV_PROVIDER", "mock")
        self.model = e.get("MV_MODEL") or llm["model"]
        self.api_key = llm["api_key"]
        self.base_url = llm["base_url"]
        self.timeout_s = _int(e, "MV_PROVIDER_TIMEOUT_S", 60)

        # "label:token:role,label:token:role,..." — labels are for safe
        # introspection only; the raw token is never exposed after parsing.
        self.token_roles = self._parse_tokens(e.get("MV_TOKENS", ""))

        self.allow_self_approval = _bool(e, "MV_ALLOW_SELF_APPROVAL", default=False)
        self.synthetic_only = _bool(e, "MV_SYNTHETIC_ONLY", default=True)

        self.csv_preview_ttl_s = _int(e, "MV_CSV_PREVIEW_TTL_S", 900)

    @staticmethod
    def _parse_tokens(raw):
        """Returns {token: {"role": role, "label": label}}. Never logs values."""
        out = {}
        for entry in raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":")
            if len(parts) != 3:
                continue
            label, token, role = (p.strip() for p in parts)
            if role in VALID_ROLES and token:
                out[token] = {"role": role, "label": label, "enabled": True}
        return out

    def require_token(self):
        return self.host not in ("127.0.0.1", "localhost", "::1")

    def has_valid_tokens(self):
        return bool(self.token_roles)
