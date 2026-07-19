"""Read-only JSON API + static host for the assistant UI.

Serves the engines' read-models as JSON under /api/* and (optionally) the built
React app from web/dist. Read-only with respect to the knowledge base: GET
endpoints read engine output; the only POST routes are /api/chat and
/api/analyze, which accept a request body (conversation history) and compute a
response — they never write to a scorecard, evidence record, or any file.
There are no PUT/DELETE routes at all.

Run:
    python3 executive-ui/api/server.py [--port 8000] [--host 127.0.0.1] [--root <repo>]

PORT/HOST env vars are honored (the convention most container platforms use),
so `PORT=7860 HOST=0.0.0.0 python3 executive-ui/api/server.py` also works.

During development the Vite dev server (port 5173) proxies /api here. For a
single-process deploy, build the web app (`npm run build` in executive-ui/web)
and this server will also serve web/dist.
"""

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from . import (auth_store, generate, modes, monitoring_runner, router,
                   serialize, user_store)
except ImportError:  # run directly as a script (python3 executive-ui/api/server.py)
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from api import (auth_store, generate, modes, monitoring_runner, router,
                     serialize, user_store)

# shared.research lives at the repo root (the platform layer, reused later by
# the runner/monitoring), not under executive-ui — make the root importable
# when run as a script.
try:
    from shared import freshness
    from shared.research import store as research_store
    from shared.research import profiles as research_profiles
    from shared.research import providers as research_providers
    from shared.research import runner as research_runner
    from shared.research import revalidate as research_revalidate
    from shared.research import extract as research_extract
    from shared.llm import provider as llm_provider
    from shared import workspace as workspace_pkg
    from shared import documents as documents_pkg
    from shared import email as email_pkg
    from shared.email import monitoring_digest
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from shared import freshness
    from shared.research import store as research_store
    from shared.research import profiles as research_profiles
    from shared.research import providers as research_providers
    from shared.research import runner as research_runner
    from shared.research import revalidate as research_revalidate
    from shared.research import extract as research_extract
    from shared.llm import provider as llm_provider
    from shared import workspace as workspace_pkg
    from shared import documents as documents_pkg
    from shared import email as email_pkg
    from shared.email import monitoring_digest


class _ExtractionLLMConfig:
    """Minimal config for the extraction model — the canonical BOTIM_LLM_*
    resolution (shared.llm.provider) without a cross-service import of
    copilot-backend's Config. Timeout is bounded per extraction call."""

    def __init__(self):
        resolved = llm_provider.resolve_llm_env()
        self.provider = resolved["provider"]
        self.api_key = resolved["api_key"]
        self.model = resolved["model"]
        self.base_url = resolved["base_url"]
        self.timeout_s = int(os.environ.get("RESEARCH_EXTRACT_TIMEOUT_S", 60))

UI_DIR = Path(__file__).resolve().parents[1]
WEB_DIST = UI_DIR / "web" / "dist"

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml", ".ico": "image/x-icon", ".map": "application/json",
    ".woff": "font/woff", ".woff2": "font/woff2",
}

OPP_ID = re.compile(r"^OPP-\d{3}$")

# Integration Phase 2 — this server also fronts copilot-backend so a single
# process/origin can serve both APIs in a single-container deploy. The
# upstream is a FIXED, operator-configured address (never derived from a
# request) — this is a narrow, single-destination passthrough, not an open
# proxy: no arbitrary host/URL from user input is ever honored.
COPILOT_UPSTREAM = os.environ.get("COPILOT_UPSTREAM_URL", "http://127.0.0.1:8010").rstrip("/")
COPILOT_PROXY_TIMEOUT_S = 30

# Phase 3 — /chat and /analyze (reachable as either /api/... or the
# /executive-api/... alias) are the pre-copilot-backend, ungrounded scaffold
# (executive-ui/api/generate.py, router.py). The chat UI now talks to the
# grounded copilot-backend via /copilot-api/* instead, so this legacy pair is
# disabled by default and only reachable when explicitly opted into.
LEGACY_UNGROUNDED_ROUTES_ENABLED = os.environ.get("ENABLE_LEGACY_UNGROUNDED_ROUTES") == "1"
LEGACY_ROUTE_PATHS = ("/chat", "/analyze")

# Same default as copilot-backend's own COPILOT_MAX_BODY_BYTES (see
# copilot-backend/app/config.py) — enforced here too so an oversized body is
# rejected at the proxy, before it is ever read into memory, not only after
# forwarding it to copilot-backend.
COPILOT_PROXY_MAX_BODY_BYTES = int(os.environ.get("COPILOT_MAX_BODY_BYTES", 65536))


# Phase 6 — one shared runtime store for user-created opportunities (path
# from USER_OPPORTUNITIES_DB_PATH, default runtime/user-opportunities.db).
# Lazy so importing this module never touches the filesystem.
_USER_STORE = None


def get_user_store():
    global _USER_STORE
    if _USER_STORE is None:
        _USER_STORE = user_store.UserStore()
    return _USER_STORE


# Phase R1 — shared runtime store for research runs (path from
# RESEARCH_DB_PATH, default runtime/research.db). Lazy for the same reason.
_RESEARCH_STORE = None


def get_research_store():
    global _RESEARCH_STORE
    if _RESEARCH_STORE is None:
        _RESEARCH_STORE = research_store.ResearchStore()
    return _RESEARCH_STORE


# Phase R5/PR4 — shared runtime store for versioned analysis workspaces
# (path from WORKSPACE_DB_PATH, default runtime/workspace.db). Lazy too.
_WORKSPACE_STORE = None


def get_workspace_store():
    global _WORKSPACE_STORE
    if _WORKSPACE_STORE is None:
        _WORKSPACE_STORE = workspace_pkg.WorkspaceStore()
    return _WORKSPACE_STORE


# Phase R8a — accounts + sessions (path from AUTH_DB_PATH, default
# runtime/auth.db). Lazy for the same reason.
_AUTH_STORE = None


def get_auth_store():
    global _AUTH_STORE
    if _AUTH_STORE is None:
        _AUTH_STORE = auth_store.AuthStore()
    return _AUTH_STORE


# Phase R7 — uploaded-document store (path from DOCUMENTS_DB_PATH, default
# runtime/documents.db). Lazy like the others.
_DOCUMENT_STORE = None


def get_document_store():
    global _DOCUMENT_STORE
    if _DOCUMENT_STORE is None:
        _DOCUMENT_STORE = documents_pkg.DocumentStore()
    return _DOCUMENT_STORE


# Phase R6 — outbound email sender, resolved fresh each call from the SMTP_*
# environment (so a deploy can configure it without a restart quirk). Returns
# a real SMTP sender when configured, else an honest unconfigured sender that
# fails loudly. Tests inject a MockEmailSender by monkeypatching this.
def get_email_sender():
    return email_pkg.make_sender()


SESSION_COOKIE = "botim_session"


def auth_required():
    """Phase R8a — enforcement is opt-in per deployment. Default 'off'
    preserves the existing single-tenant behavior; any value other than an
    explicit off-switch enables enforcement (a typo FAILS CLOSED — it never
    silently disables auth). Read per request so tests can toggle it."""
    value = os.environ.get("BOTIM_AUTH_MODE", "off").strip().lower()
    return value not in ("", "off", "0", "disabled", "none")


def registration_open():
    """Open registration by default; the operator can close it once the
    intended accounts exist (AUTH_ALLOW_REGISTRATION=0)."""
    return os.environ.get("AUTH_ALLOW_REGISTRATION", "1").strip().lower() \
        not in ("0", "off", "false", "no")


# Phase R8b — per-user daily quotas on expensive actions, enforced only
# under required-auth mode (no identity, no quota). Overridable per action:
# QUOTA_CHAT_PER_DAY, QUOTA_RESEARCH_EXECUTE_PER_DAY, ...
QUOTA_DEFAULTS = {"chat": 200, "research_execute": 25, "research_extract": 25,
                  "workspace_refresh": 25, "monitoring_run": 25,
                  "document_upload": 25, "monitoring_workspace_run": 6}


def monitoring_run_quota_limit(ws, owner_user_id):
    """R6 scheduled-run quota, SCALED by the owner's active subscriptions so a
    multi-chat user is not silently cut off at a flat cap: base-per-subscription
    (QUOTA_MONITORING_WORKSPACE_RUN_PER_DAY, default 6) × active subscriptions."""
    base = quota_limit("monitoring_workspace_run")
    active = ws.count_enabled_subscriptions(owner_user_id) if owner_user_id else 0
    return base * max(1, active)


def quota_limit(action):
    raw = os.environ.get(f"QUOTA_{action.upper()}_PER_DAY", "")
    try:
        return max(1, int(raw)) if raw.strip() else QUOTA_DEFAULTS[action]
    except ValueError:
        return QUOTA_DEFAULTS[action]


def _cookie_secure():
    """Secure flag on the session cookie: on by default (production is
    HTTPS), explicitly disable with AUTH_COOKIE_SECURE=0 for plain-HTTP
    local runs; test mode defaults it off so the offline suites work."""
    explicit = os.environ.get("AUTH_COOKIE_SECURE")
    if explicit is not None:
        return explicit.strip().lower() not in ("0", "off", "false", "no")
    return modes.get_mode() != "test"


class Handler(BaseHTTPRequestHandler):
    repo_root = "."

    def log_message(self, *args):  # quieter console
        pass

    # -- helpers ----------------------------------------------------------- #
    def _json(self, obj, status=200, extra_headers=None):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (extra_headers or []):
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, msg):
        self._json({"error": msg}, status=status)

    # -- Phase R8a: sessions -------------------------------------------------- #

    def _session_token(self):
        header = self.headers.get("Cookie")
        if not header:
            return None
        from http.cookies import SimpleCookie
        try:
            jar = SimpleCookie()
            jar.load(header)
        except Exception:
            return None
        morsel = jar.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def _current_user(self):
        token = self._session_token()
        if not token:
            return None
        try:
            return get_auth_store().session_user(token)
        except auth_store.AuthError:
            return None

    def _session_cookie_header(self, token, clear=False):
        parts = [f"{SESSION_COOKIE}={'' if clear else token}", "Path=/",
                 "HttpOnly", "SameSite=Lax",
                 f"Max-Age={0 if clear else auth_store.SESSION_TTL_DAYS * 86400}"]
        if _cookie_secure():
            parts.append("Secure")
        return ("Set-Cookie", "; ".join(parts))

    def _require_session(self):
        """The signed-in user, or an emitted 401 (returns None). Callers must
        stop when None. Only consulted when auth_required()."""
        user = self._current_user()
        if user is None:
            self._json({"error": "authentication required",
                        "code": "auth_required"}, status=401)
        return user

    def _quota_guard(self, action):
        """Phase R8b — count-and-record one expensive action for the current
        user. True = proceed; False = a 429 was already emitted. A no-op
        (True) when enforcement is off — no identity, no quota."""
        if not auth_required():
            return True
        user = self._current_user()
        if user is None:   # the session guard upstream already handles this
            return True
        try:
            get_auth_store().check_quota(user["id"], action, quota_limit(action))
            return True
        except auth_store.AuthError as exc:
            self._error(exc.status, str(exc))
            return False

    def _research_owner_guard(self, store, run_id):
        """Phase R8b — True when the current user may act on the run (own
        run or legacy NULL-owner). Emits an indistinguishable 404 otherwise."""
        if not auth_required():
            return True
        user = self._current_user()
        run = store.get_run(run_id)
        if user is not None and run.get("owner_user_id") not in (None, user["id"]):
            self._error(404, "research run not found")
            return False
        return True

    # /auth/* — always reachable (sign-in must work before a session exists)
    def _auth_api(self, method, sub):
        store = get_auth_store()
        try:
            if sub == "/auth/me" and method == "GET":
                return self._json({"auth_mode": "required" if auth_required() else "off",
                                   "registration_open": registration_open(),
                                   "user": self._current_user()})
            if sub == "/auth/register" and method == "POST":
                if not registration_open():
                    return self._error(403, "registration is closed on this deployment")
                body = self._read_json_body()
                user = store.register(body.get("email"), body.get("password"),
                                      display_name=body.get("display_name"))
                _, token = store.login(body.get("email"), body.get("password"))
                return self._json({"user": user}, status=201,
                                  extra_headers=[self._session_cookie_header(token)])
            if sub == "/auth/login" and method == "POST":
                body = self._read_json_body()
                user, token = store.login(body.get("email"), body.get("password"))
                return self._json({"user": user},
                                  extra_headers=[self._session_cookie_header(token)])
            if sub == "/auth/logout" and method == "POST":
                store.logout(self._session_token())
                return self._json({"signed_out": True},
                                  extra_headers=[self._session_cookie_header("", clear=True)])
            return self._error(404, "unknown auth endpoint")
        except auth_store.AuthError as exc:
            return self._error(exc.status, str(exc))
        except Exception as exc:  # never leak hashes/SQL/paths
            return self._error(500, f"{type(exc).__name__}: internal error")

    def do_OPTIONS(self):  # CORS preflight
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, Authorization")
        self.end_headers()

    # -- copilot-backend passthrough (Phase 2) ------------------------------ #
    # Forwards /copilot-api/<sub> to COPILOT_UPSTREAM + /api/<sub> unchanged.
    # Bounded: fixed upstream, bounded timeout, request body size-limited here
    # (Phase 3, before ever being buffered — see do_POST/do_GET/do_DELETE)
    # as well as by copilot-backend itself; never proxies to a caller-supplied
    # URL.
    def _proxy_to_copilot(self, method, sub_path, query, body_bytes):
        url = f"{COPILOT_UPSTREAM}/api{sub_path}"
        if query:
            url += "?" + query
        headers = {"content-type": "application/json", "accept": "application/json"}
        # Phase R8b — propagate the session-validated identity to the copilot
        # backend so conversations can be owner-scoped. The header dict is
        # built fresh here (a client-supplied X-Botim-User is never
        # forwarded); copilot honors it only with COPILOT_TRUST_PROXY_USER=1.
        if auth_required():
            user = self._current_user()
            if user:
                headers["x-botim-user"] = user["id"]
        # Forwarded unchanged, never logged (see log_message override above
        # and logging_util on the copilot-backend side — neither ever prints
        # header values).
        auth = self.headers.get("Authorization")
        if auth:
            headers["authorization"] = auth
        req = urllib.request.Request(url, data=body_bytes if body_bytes else None, method=method,
                                     headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=COPILOT_PROXY_TIMEOUT_S) as r:
                status = r.status
                data = r.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            data = exc.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            return self._json({"schema_version": "1.0", "error": {
                "code": "provider_error", "message": "the conversational backend is unavailable",
                "retryable": True}}, status=502)
        try:
            payload = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._error(502, "malformed response from conversational backend")
        return self._json(payload, status=status)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return {}

    # POST is used ONLY for compute endpoints that need a request body (chat /
    # analyze with conversation history). It never writes to the knowledge base
    # or any engine state — it computes a response and returns it.
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/copilot-api/"):
            # Phase R8a — under required-auth mode, chat needs a session too
            if auth_required() and self._require_session() is None:
                return
            # Phase R8b — chat calls count against the user's daily quota
            if path.endswith("/chat") and not self._quota_guard("chat"):
                return
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length > COPILOT_PROXY_MAX_BODY_BYTES:
                # Rejected on the declared Content-Length alone — never
                # buffered into memory first.
                return self._json({"schema_version": "1.0", "error": {
                    "code": "message_too_long", "message": "request body too large",
                    "retryable": False}}, status=413)
            body = self.rfile.read(length) if length else b""
            return self._proxy_to_copilot("POST", path[len("/copilot-api"):], parsed.query, body)
        if path.startswith("/executive-api/"):
            path = "/api" + path[len("/executive-api"):]
        if not path.startswith("/api/"):
            return self._error(404, "not found")
        sub = path[len("/api"):]
        # Phase R8a — sign-in/register/logout are reachable without a session;
        # every other API write requires one when enforcement is on.
        if sub.startswith("/auth/"):
            return self._auth_api("POST", sub)
        # Phase R6 — the scheduled-monitoring tick is authenticated by a shared
        # secret (external cron), NOT a user session; it must bypass the session
        # gate exactly like /auth/*.
        if sub == "/monitoring/tick":
            return self._monitoring_tick()
        if auth_required() and self._require_session() is None:
            return
        # Phase 6/7 — user-opportunity writes (create / archive / restore /
        # monitoring pause+resume)
        if sub.startswith("/user-opportunities"):
            return self._user_api("POST", sub, parse_qs(parsed.query))
        # Phase R2 — research-run writes (create + execute). Bounded, honest:
        # execution with no configured provider finishes the run as 'failed'
        # with a stated reason — it never fabricates results.
        if sub.startswith("/research/"):
            return self._research_post(sub)
        if sub in LEGACY_ROUTE_PATHS and not LEGACY_UNGROUNDED_ROUTES_ENABLED:
            return self._legacy_disabled()
        body = self._read_json_body()
        msg = str(body.get("q") or body.get("message") or "")
        history = body.get("history") if isinstance(body.get("history"), list) else None
        try:
            if sub == "/analyze":
                return self._json(generate.analyze(msg, self.repo_root, history=history))
            if sub == "/chat":
                return self._json(router.route(msg, self.repo_root))
            return self._error(405, f"{sub} does not accept POST (read-only)")
        except Exception as exc:
            return self._error(500, f"{type(exc).__name__}: {exc}")

    # -- Phase R2/R3: research helpers -------------------------------------- #
    @staticmethod
    def _research_run_detail(store, run_id):
        """Full run with deterministic freshness computed on each source from
        its STORED publication date (same pure date math as Phase 4 evidence
        freshness — computed, never invented). Retrieval time is deliberately
        excluded: automated retrieval is always recent, so counting it would
        mark every external source permanently 'fresh'; a source without a
        publication date is honestly 'unknown'."""
        run = store.get_run(run_id, include_children=True)
        for source in run.get("sources", []):
            source.update(freshness.compute({
                "publication_date": source.get("published_at"),
            }))
        return run

    # -- Phase R2: research-run writes -------------------------------------- #
    def _research_post(self, sub):
        store = get_research_store()
        try:
            if sub in ("/research/runs", "/research/runs/"):
                body = self._read_json_body()
                profile_name = body.get("profile")
                owner = self._current_user() if auth_required() else None
                run = store.create_run(body,
                                       owner_user_id=owner["id"] if owner else None)
                # a profile pre-plans the run's queries deterministically
                if profile_name:
                    try:
                        pairs = research_profiles.generate_queries(
                            profile_name, body.get("context") or {})
                    except KeyError:
                        return self._error(400, f"unknown research profile "
                                                f"'{profile_name}' (available: "
                                                f"{', '.join(research_profiles.available_profiles())})")
                    for objective, query_text in pairs:
                        store.add_query(run["id"], {"objective": objective,
                                                    "query_text": query_text})
                elif isinstance(body.get("queries"), list):
                    for q in body["queries"][:research_profiles.PROFILE_MAX_QUERIES]:
                        if isinstance(q, str) and q.strip():
                            store.add_query(run["id"], {"query_text": q.strip()})
                return self._json(store.get_run(run["id"], include_children=True), status=201)
            m = re.match(r"^/research/runs/(RRUN-[0-9a-f]{12})/execute$", sub)
            if m:
                if not self._research_owner_guard(store, m.group(1)):
                    return
                if not self._quota_guard("research_execute"):
                    return
                try:
                    provider = research_providers.from_env()
                except research_providers.SearchProviderError as exc:
                    return self._error(400, str(exc))
                finished = research_runner.execute_run(store, m.group(1), provider)
                return self._json(self._research_run_detail(store, finished["id"]))
            # Phase R3 — human-authored candidate claims + review decisions.
            # Approval never mints an EV id or touches the knowledge base.
            m = re.match(r"^/research/runs/(RRUN-[0-9a-f]{12})/candidates$", sub)
            if m:
                if not self._research_owner_guard(store, m.group(1)):
                    return
                body = self._read_json_body()
                return self._json(store.add_candidate(m.group(1), body), status=201)
            m = re.match(r"^/research/candidates/(RCAND-[0-9a-f]{12})/review$", sub)
            if m:
                # ownership follows the candidate's run (Phase R8b)
                cand = store.get_candidate(m.group(1))
                if not self._research_owner_guard(store, cand["run_id"]):
                    return
                body = self._read_json_body()
                return self._json(store.review_candidate(
                    m.group(1), body.get("action"), note=body.get("note")))
            # Phase R4b — re-check the run's sources; append-only outcomes,
            # nothing auto-applied. Works on finished runs (that is the point).
            m = re.match(r"^/research/runs/(RRUN-[0-9a-f]{12})/revalidate$", sub)
            if m:
                if not self._research_owner_guard(store, m.group(1)):
                    return
                summary = research_revalidate.revalidate_run(store, m.group(1))
                detail = self._research_run_detail(store, m.group(1))
                detail["revalidation_summary"] = summary
                return self._json(detail)
            # PR3 — LLM-assisted claim extraction with source verification.
            # Accepted claims land as pending_review candidates (origin
            # 'extracted'); nothing shortcuts human review. Needs a live model.
            m = re.match(r"^/research/runs/(RRUN-[0-9a-f]{12})/extract$", sub)
            if m:
                if not self._research_owner_guard(store, m.group(1)):
                    return
                if not self._quota_guard("research_extract"):
                    return
                cfg = _ExtractionLLMConfig()
                if cfg.provider not in ("anthropic", "openai_compatible"):
                    return self._error(400, "no model provider configured for extraction "
                                            "(set BOTIM_LLM_API_KEY)")
                provider = llm_provider.make_provider(cfg)
                summary = research_extract.extract_claims(store, m.group(1), provider, cfg)
                detail = self._research_run_detail(store, m.group(1))
                detail["extraction_summary"] = summary
                return self._json(detail)
            return self._error(404, "unknown research endpoint")
        except research_store.ResearchStoreError as exc:
            return self._error(exc.status, str(exc))
        except Exception as exc:  # never leak a stack trace
            return self._error(500, f"{type(exc).__name__}: {exc}")

    # -- Phase 6/7: user-opportunity + monitoring-config API ---------------- #
    # All writes go through user_store.UserStore (separate runtime SQLite DB;
    # the committed knowledge base stays read-only). Committed OPP- ids never
    # match the UOPP- routes, so demo/reference records cannot be edited here.
    def _user_api(self, method, sub, query):
        m = re.match(r"^/user-opportunities"
                     r"(?:/(UOPP-[0-9a-f]{12})"
                     r"(?:/(archive|restore|monitoring|workspace|documents)"
                     r"(?:/(pause|resume|run|events|refresh|versions|diff|monitoring))?)?)?/?$", sub)
        if not m:
            # a syntactically different id shape (e.g. OPP-010) is a client
            # error, not a missing record — never resolves to committed data
            if sub.startswith("/user-opportunities/"):
                return self._error(400, "invalid user-opportunity id")
            return self._error(404, "unknown endpoint")
        opp_id, action, mon_action = m.group(1), m.group(2), m.group(3)
        store = get_user_store()
        # Phase R8a — per-user scoping under required-auth mode. Legacy rows
        # (NULL owner, created before auth existed) stay visible to every
        # signed-in user; new records belong to their creator; another
        # user's record answers 404 (indistinguishable from nonexistent).
        owner = self._current_user() if auth_required() else None
        try:
            if method == "GET" and opp_id is None:
                include_archived = (query.get("include_archived") or ["0"])[0] in ("1", "true")
                return self._json({"user_opportunities": store.list(
                    include_archived=include_archived,
                    visible_to=owner["id"] if owner else None)})
            if method == "POST" and opp_id is None:
                return self._json(store.create(
                    self._read_json_body(),
                    owner_user_id=owner["id"] if owner else None), status=201)
            if opp_id is None:
                return self._error(405, "method not allowed")
            if owner is not None:
                record_owner = store.get(opp_id).get("owner_user_id")
                if record_owner is not None and record_owner != owner["id"]:
                    return self._error(404, "user opportunity not found")
            if action is None:
                if method == "GET":
                    return self._json(store.get(opp_id))
                if method == "PATCH":
                    return self._json(store.update(opp_id, self._read_json_body()))
                if method == "DELETE":
                    confirm = (query.get("confirm") or [None])[0]
                    return self._json(store.delete(opp_id, confirm=confirm))
                return self._error(405, "method not allowed")
            if action == "documents":
                return self._documents_api(method, opp_id, owner)
            if action == "workspace":
                return self._workspace_api(method, opp_id, mon_action, store)
            if action == "archive" and method == "POST":
                return self._json(store.archive(opp_id))
            if action == "restore" and method == "POST":
                return self._json(store.restore(opp_id))
            if action == "monitoring":
                if mon_action == "pause" and method == "POST":
                    return self._json(store.monitoring_pause(opp_id))
                if mon_action == "resume" and method == "POST":
                    return self._json(store.monitoring_resume(opp_id))
                # Phase R4a — MANUAL monitoring run (no scheduler exists;
                # cadence remains intended configuration). Provider failure
                # is recorded honestly on the config, never fabricated away.
                if mon_action == "run" and method == "POST":
                    if not self._quota_guard("monitoring_run"):
                        return
                    try:
                        provider = research_providers.from_env()
                    except research_providers.SearchProviderError as exc:
                        return self._error(400, str(exc))
                    try:
                        result = monitoring_runner.run_monitoring(
                            store, get_research_store(), opp_id, provider)
                    except monitoring_runner.MonitoringRunError as exc:
                        return self._error(exc.status, str(exc))
                    result["config"] = store.monitoring_get(opp_id)
                    return self._json(result)
                if mon_action == "events" and method == "GET":
                    limit = (query.get("limit") or ["50"])[0]
                    return self._json({"events": store.monitoring_events(
                        opp_id, limit=int(limit) if str(limit).isdigit() else 50)})
                if mon_action is None:
                    if method == "GET":
                        config = store.monitoring_get(opp_id)
                        if config.get("status") == "not_configured":
                            # editable configuration-draft suggestions from the
                            # saved fields — never auto-enabled
                            config["suggested_topics"] = user_store.suggested_monitoring_topics(
                                store.get(opp_id))
                        return self._json(config)
                    if method == "PUT":
                        return self._json(store.monitoring_put(opp_id, self._read_json_body()))
                    if method == "DELETE":
                        return self._json(store.monitoring_delete(opp_id))
                return self._error(405, "method not allowed")
            return self._error(405, "method not allowed")
        except user_store.StoreError as exc:
            return self._error(exc.status, str(exc))
        except Exception as exc:  # never leak SQL/stack detail
            return self._error(500, f"{type(exc).__name__}: internal error")

    # -- Phase R7: uploaded documents ---------------------------------------- #
    # POST .../documents           -> upload {filename, content_base64};
    #                                  extraction is synchronous and honest —
    #                                  a failed extraction fails the upload.
    # GET  .../documents           -> list for this opportunity
    # DELETE /api/documents/{DOC-} -> permanent delete (document + chunks)
    def _documents_api(self, method, opp_id, owner):
        docs = get_document_store()
        try:
            if method == "GET":
                return self._json({"documents": docs.list_documents(
                    opp_id, visible_to=owner["id"] if owner else None)})
            if method == "POST":
                if not self._quota_guard("document_upload"):
                    return
                body = self._read_json_body()
                filename = body.get("filename")
                encoded = body.get("content_base64")
                if not isinstance(filename, str) or not isinstance(encoded, str):
                    return self._error(400, "body must carry 'filename' and 'content_base64'")
                import base64
                try:
                    data = base64.b64decode(encoded, validate=True)
                except (ValueError, TypeError):
                    return self._error(400, "content_base64 is not valid base64")
                try:
                    text, meta = documents_pkg.extract_text(filename, data)
                except documents_pkg.ExtractionError as exc:
                    return self._error(exc.status, str(exc))
                chunks = documents_pkg.chunk_text(text)
                doc = docs.add_document(opp_id, filename, meta, chunks,
                                        owner_user_id=owner["id"] if owner else None)
                return self._json(doc, status=201)
            return self._error(405, "method not allowed")
        except documents_pkg.DocumentStoreError as exc:
            return self._error(exc.status, str(exc))
        except Exception as exc:  # never leak content/SQL
            return self._error(500, f"{type(exc).__name__}: internal error")

    def _document_delete(self, doc_id):
        docs = get_document_store()
        try:
            doc = docs.get_document(doc_id)
            # the document follows its opportunity's ownership AND its own
            owner = self._current_user() if auth_required() else None
            if owner is not None:
                if doc.get("owner_user_id") not in (None, owner["id"]):
                    return self._error(404, "document not found")
                rec = get_user_store().get(doc["opportunity_id"])
                if rec.get("owner_user_id") not in (None, owner["id"]):
                    return self._error(404, "document not found")
            return self._json(docs.delete_document(doc_id))
        except documents_pkg.DocumentStoreError as exc:
            return self._error(exc.status, str(exc))
        except user_store.StoreError:
            # opportunity gone but the document remains -> still deletable
            return self._json(docs.delete_document(doc_id))
        except Exception as exc:
            return self._error(500, f"{type(exc).__name__}: internal error")

    # -- Phase R5/PR4: versioned analysis workspace -------------------------- #
    # POST .../workspace/refresh  -> run the full chain, append a new version
    # GET  .../workspace          -> latest complete version (+staleness)
    # GET  .../workspace/versions -> version summaries (newest first)
    # Follow-up chat NEVER hits refresh — the chain runs only on the explicit
    # triggers locked in docs/decision-log.md.
    def _workspace_api(self, method, opp_id, sub_action, store):
        ws = get_workspace_store()
        try:
            opp = store.get(opp_id)  # 404 for unknown opportunity
            if sub_action == "monitoring":
                return self._workspace_monitoring(method, opp_id, ws, opp)
            if sub_action == "refresh" and method == "POST":
                if not self._quota_guard("workspace_refresh"):
                    return
                body = self._read_json_body()
                # first build for this opportunity is 'first_analysis'; later
                # explicit refreshes are 'manual_refresh'
                trigger = ("first_analysis" if not ws.list_versions(opp_id, limit=1)
                           else "manual_refresh")
                search_provider, llm, llm_cfg = self._resolve_build_providers()
                viewer = self._current_user() if auth_required() else None
                version = workspace_pkg.build_workspace(
                    ws, get_research_store(), opp, trigger=trigger,
                    question=body.get("question") if isinstance(body.get("question"), str) else None,
                    search_provider=search_provider,
                    llm_provider=llm, llm_config=llm_cfg,
                    document_store=get_document_store(),
                    viewer_user_id=viewer["id"] if viewer else None)
                return self._json(self._workspace_view(ws, version), status=201)
            if sub_action == "versions" and method == "GET":
                return self._json({"versions": ws.list_versions(opp_id)})
            if sub_action == "diff" and method == "GET":
                # deterministic diff of the two newest COMPLETE versions —
                # the same pure comparison R6 notifications will use
                complete = [v for v in ws.list_versions(opp_id)
                            if v["status"] == "complete"][:2]
                if len(complete) < 2:
                    return self._json({"diff": None,
                                       "note": "fewer than two complete versions exist "
                                               "— nothing to compare yet"})
                newer = ws.get_version(complete[0]["id"])
                older = ws.get_version(complete[1]["id"])
                return self._json({"diff": workspace_pkg.compare_versions(older, newer)})
            if sub_action is None and method == "GET":
                latest = ws.latest(opp_id)
                if latest is None:
                    return self._json({"workspace": None,
                                       "note": "no analysis workspace exists yet — "
                                               "run a refresh to build the first version"})
                return self._json({"workspace": self._workspace_view(ws, latest)})
            return self._error(405, "method not allowed")
        except workspace_pkg.WorkspaceStoreError as exc:
            return self._error(exc.status, str(exc))
        except user_store.StoreError as exc:
            return self._error(exc.status, str(exc))
        except research_store.ResearchStoreError as exc:
            return self._error(exc.status, str(exc))
        except Exception as exc:  # never leak SQL/stack detail
            return self._error(500, f"{type(exc).__name__}: internal error")

    @staticmethod
    def _workspace_view(ws, version):
        """A version enriched with deterministic staleness and the CURRENT
        review status of its candidate claims (read from the research store —
        approvals attach to claims, so they survive across versions)."""
        view = dict(version)
        view["is_stale"] = ws.is_stale(version)
        claims = []
        if version.get("research_run_id") and version.get("claim_ids"):
            try:
                detail = get_research_store().get_run(version["research_run_id"],
                                                      include_children=True)
                by_id = {c["id"]: c for c in detail.get("candidate_evidence", [])}
                for cid in version["claim_ids"]:
                    c = by_id.get(cid)
                    if c:
                        claims.append({"id": c["id"], "claim": c["claim"],
                                       "status": c["status"], "origin": c.get("origin"),
                                       "source_ids": c.get("source_ids", [])})
            except research_store.ResearchStoreError:
                pass  # claims stay listable by id even if the run vanished
        view["claims"] = claims
        return view

    # -- Phase R6: scheduled-monitoring subscription (consent/recipients) ---- #
    # GET    .../workspace/monitoring -> this chat's subscription + recipients
    # POST   .../workspace/monitoring -> the signed-in user opts THEMSELVES in
    #                                    (their own registered account email;
    #                                    no free text), sets the cadence, and is
    #                                    emailed a DOUBLE-OPT-IN confirmation
    #                                    link. Re-POSTing while unconfirmed
    #                                    resends it. No mail (incl. monitoring
    #                                    mail) goes out until confirmed.
    # DELETE .../workspace/monitoring -> the signed-in user opts themselves out
    # A recipient is always a signed-in account acting through its own session
    # (its registered email), and must confirm control of that address via the
    # tokened link before becoming eligible — see the decision log.
    def _workspace_monitoring(self, method, opp_id, ws, opp):
        # Monitoring email is meaningless without an identity to scope it to.
        # When auth enforcement is off on this deployment, say so honestly
        # rather than returning a confusing "sign in" error for a sign-in
        # system that isn't switched on.
        if not auth_required():
            return self._error(403, "scheduled monitoring email is unavailable on "
                                    "this deployment — it requires sign-in to be "
                                    "enabled (BOTIM_AUTH_MODE=required) so recipients "
                                    "are tied to a signed-in account")
        user = self._current_user()
        if user is None:
            return self._error(401, "sign in to manage monitoring email")
        if method == "GET":
            sub = ws.get_subscription(opp_id)
            owner_id = (sub or {}).get("owner_user_id") or opp.get("owner_user_id") or user["id"]
            quota = None
            try:
                quota = get_auth_store().quota_status(
                    owner_id, "monitoring_workspace_run",
                    monitoring_run_quota_limit(ws, owner_id))
            except auth_store.AuthError:
                pass  # honest: no quota view rather than a crash
            return self._json({"subscription": sub, "quota": quota})
        if method == "POST":
            body = self._read_json_body()
            cadence = body.get("cadence_hours")
            # the subscription is owned by the opportunity's owner; a legacy
            # shared record (NULL owner) is anchored to the first subscriber so
            # quota and scheduling always tie to a real account (never NULL).
            owner_id = opp.get("owner_user_id") or user["id"]
            result = ws.subscribe(opp_id, owner_user_id=owner_id,
                                  recipient_user_id=user["id"],
                                  recipient_email=user["email"],
                                  cadence_hours=cadence)
            confirmation = self._maybe_send_confirmation(user["email"], opp, result)
            return self._json({"subscription": ws.get_subscription(opp_id),
                               "confirmation": confirmation}, status=201)
        if method == "DELETE":
            return self._json(ws.unsubscribe_recipient(opp_id, user["id"]))
        return self._error(405, "method not allowed")

    def _public_base(self):
        """Absolute base URL for links emailed to users. Prefer an explicit
        MONITORING_PUBLIC_BASE_URL; otherwise derive from the Host header
        (https unless the host is clearly a plain-HTTP local/test address)."""
        base = os.environ.get("MONITORING_PUBLIC_BASE_URL")
        if base:
            return base.rstrip("/")
        host = self.headers.get("Host") or "localhost"
        scheme = "http" if host.startswith(("127.0.0.1", "localhost")) else "https"
        return f"{scheme}://{host}"

    def _maybe_send_confirmation(self, to_email, opp, subscribe_result):
        """Send the double-opt-in confirmation email if this opt-in produced a
        confirm token. Honest states: already-confirmed -> nothing to send;
        send failure / unconfigured SMTP -> reported truthfully (the recipient
        simply stays unconfirmed and receives no mail), never a fake success."""
        token = subscribe_result.get("confirm_token")
        if not token:  # already confirmed — no confirmation needed
            return {"required": False, "email_sent": False,
                    "note": "this address is already confirmed"}
        title = opp.get("title") or opp.get("id") or "this opportunity"
        ttl = int(os.environ.get("MONITORING_CONFIRM_TTL_HOURS", 48))
        link = f"{self._public_base()}/api/monitoring/confirm?token={token}"
        subject = f"Confirm monitoring email for {title}"
        text = (
            "You asked to receive scheduled analysis-monitoring updates for the "
            f"opportunity \"{title}\".\n\n"
            f"Confirm this address to start receiving them:\n{link}\n\n"
            f"This link expires in {ttl} hours. Until it is confirmed, no email "
            "is sent — if you didn't request this, simply ignore this message.")
        try:
            get_email_sender().send(to_email, subject, text)
            return {"required": True, "email_sent": True, "sent_to": to_email,
                    "note": f"confirmation email sent to {to_email}; "
                            "monitoring starts once you confirm"}
        except email_pkg.EmailError as exc:
            # unconfigured SMTP or a delivery failure — honest, not fabricated
            return {"required": True, "email_sent": False, "sent_to": to_email,
                    "note": f"could not send the confirmation email ({exc}) — "
                            "no monitoring mail will go out until confirmed"}

    def _monitoring_confirm(self, query):
        """Tokened, login-free confirmation (the link in the opt-in email).
        Reachable without a session even under required-auth mode."""
        token = (query.get("token") or [None])[0]
        try:
            get_workspace_store().confirm_recipient(token)
        except workspace_pkg.WorkspaceStoreError as exc:
            return self._error(exc.status, str(exc))
        return self._html_page(
            "Monitoring confirmed",
            "<h1>Monitoring confirmed</h1><p>This address is now confirmed. "
            "You'll receive an email only when a scheduled re-run finds a "
            "material change — never for an unchanged or failed run. Every "
            "message includes a one-click unsubscribe link.</p>")

    def _monitoring_unsubscribe(self, query):
        """Tokened, login-free unsubscribe (the link in a monitoring email).
        Reachable without a session even under required-auth mode."""
        token = (query.get("token") or [None])[0]
        try:
            get_workspace_store().unsubscribe_by_token(
                token, os.environ.get("MONITORING_UNSUBSCRIBE_SIGNING_KEY", ""))
        except workspace_pkg.WorkspaceStoreError as exc:
            return self._error(exc.status, str(exc))
        return self._html_page(
            "Unsubscribed",
            "<h1>Unsubscribed</h1><p>You will no longer receive scheduled "
            "analysis-monitoring emails for this opportunity. You can opt back "
            "in any time from its Analysis tab.</p>")

    def _html_page(self, title, body_html):
        """A tiny self-contained confirmation page for a link opened from an
        email client (unsubscribe / confirm) — no session, no app shell."""
        from html import escape
        page = (f"<!doctype html><html lang=en><meta charset=utf-8>"
                f"<title>{escape(title)}</title>"
                "<body style=\"font-family:system-ui,sans-serif;max-width:34rem;"
                "margin:3rem auto;padding:0 1rem;line-height:1.5\">"
                f"{body_html}</body></html>")
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        # the page never echoes the token, but set no-referrer defensively so a
        # future external link on it could never leak the token via Referer
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _resolve_build_providers():
        """Resolve the search + LLM providers for a workspace build from the
        environment (same discipline as the manual refresh). A missing provider
        is returned as None so the builder records an HONEST gap on a complete
        version — it never fabricates a step. Shared by the manual refresh and
        the scheduled tick so both paths call the same orchestrator identically."""
        try:
            search_provider = research_providers.from_env()
        except research_providers.SearchProviderError:
            search_provider = None
        cfg = _ExtractionLLMConfig()
        llm = (llm_provider.make_provider(cfg)
               if cfg.provider in ("anthropic", "openai_compatible") else None)
        return search_provider, llm, (cfg if llm else None)

    # -- Phase R6: scheduled-monitoring tick (external-cron dispatcher) ------- #
    # POST /api/monitoring/tick  (shared-secret protected; NO user session)
    # For each due subscription: atomically claim-and-advance (idempotent
    # against an at-least-once cron), skip if a build is already running, else
    # run the SAME orchestrator the manual refresh uses with trigger
    # 'monitoring', then (PR6c) diff the result and email opted-in+confirmed
    # recipients ONLY on a material change. Every outcome is recorded honestly
    # on the subscription — a no-change / partial / failed run never emails.
    def _monitoring_tick(self):
        expected = os.environ.get("MONITORING_TICK_TOKEN", "").strip()
        if not expected:
            # the feature is not enabled on this deployment — do not disclose it
            return self._error(404, "not found")
        import hmac
        provided = self.headers.get("X-Monitoring-Token", "") or ""
        if not hmac.compare_digest(provided, expected):
            return self._error(401, "invalid monitoring token")
        ws = get_workspace_store()
        store = get_user_store()
        try:
            max_chats = max(1, int(os.environ.get("MONITORING_TICK_MAX_CHATS", "25")))
        except ValueError:
            max_chats = 25
        summary = {"claimed": 0, "chats": []}
        for cand in ws.due_subscriptions(limit=max_chats):
            opp_id = cand["opportunity_id"]
            claimed = ws.claim_due(opp_id)
            if claimed is None:
                continue  # a concurrent / double-fired tick already took it
            summary["claimed"] += 1
            outcome = self._run_scheduled_build(ws, store, claimed)
            summary[outcome] = summary.get(outcome, 0) + 1
            summary["chats"].append({"opportunity_id": opp_id, "outcome": outcome})
        return self._json(summary)

    def _run_scheduled_build(self, ws, store, claimed):
        """Run one claimed subscription's chain, then decide whether to email.
        Concurrency: skip (never queue) when a build is already running for this
        chat — reusing R5's running/complete distinction. Returns the recorded
        outcome (emailed / no_change / partial_no_email / email_unavailable /
        skipped_in_progress / failed)."""
        opp_id = claimed["opportunity_id"]
        if ws.latest(opp_id, status="running") is not None:
            ws.record_run_result(opp_id, "skipped_in_progress")
            return "skipped_in_progress"
        try:
            opp = store.get(opp_id)
        except user_store.StoreError:
            ws.record_run_result(opp_id, "failed: opportunity no longer exists")
            return "failed"
        # R6 quota — count against the owner's per-user daily cap (scaled by
        # active subscriptions) BEFORE the expensive chain. Over quota -> skip
        # honestly, no build, no email. check_quota both counts and enforces.
        owner = claimed.get("owner_user_id")
        if owner:
            try:
                get_auth_store().check_quota(owner, "monitoring_workspace_run",
                                             monitoring_run_quota_limit(ws, owner))
            except auth_store.AuthError:
                ws.record_run_result(opp_id, "skipped_quota")
                return "skipped_quota"
        try:
            search_provider, llm, llm_cfg = self._resolve_build_providers()
            version = workspace_pkg.build_workspace(
                ws, get_research_store(), opp, trigger="monitoring",
                search_provider=search_provider, llm_provider=llm,
                llm_config=llm_cfg, document_store=get_document_store(),
                viewer_user_id=claimed.get("owner_user_id"))
        except Exception as exc:  # honest failure, never a fabricated success
            ws.record_run_result(opp_id, f"failed: {type(exc).__name__}")
            return "failed"
        return self._email_on_material_change(ws, claimed, opp, version)

    def _resolve_claims(self, version):
        """Resolve a version's claim ids to {id, claim, status} using the
        CURRENT review status from the research store (approvals live on
        claims). Empty when the run is gone — never fabricated."""
        rid, cids = version.get("research_run_id"), version.get("claim_ids") or []
        if not (rid and cids):
            return []
        try:
            detail = get_research_store().get_run(rid, include_children=True)
        except research_store.ResearchStoreError:
            return []
        by_id = {c["id"]: c for c in detail.get("candidate_evidence", [])}
        return [{"id": c["id"], "claim": c["claim"], "status": c["status"]}
                for cid in cids if (c := by_id.get(cid))]

    def _email_on_material_change(self, ws, claimed, opp, version):
        """Diff the new version against the baseline and email only on a real
        material change. No-change / degraded / send-unavailable all record an
        honest outcome and send nothing. Advances last_notified_version only
        when the delta has been dealt with (emailed, or baseline established)."""
        opp_id = opp["id"]
        completed = version.get("completed_at")
        # baseline: the version we last notified about; fall back to the prior
        # complete version. The first-ever complete version just seeds it.
        baseline = None
        lnv = claimed.get("last_notified_version")
        if lnv is not None:
            baseline = ws.version_by_number(opp_id, lnv)
        if baseline is None:
            prior = [v for v in ws.list_versions(opp_id)
                     if v["status"] == "complete" and v["version"] < version["version"]]
            baseline = ws.get_version(prior[0]["id"]) if prior else None
        if baseline is None:
            ws.record_run_result(opp_id, "no_change", ran_at=completed,
                                 last_notified_version=version["version"])
            return "no_change"

        ev = monitoring_digest.evaluate(
            baseline, version, self._resolve_claims(baseline), self._resolve_claims(version))
        if ev["degraded"]:
            ws.record_run_result(opp_id, "partial_no_email", ran_at=completed)
            return "partial_no_email"
        if not ev["material"]:
            ws.record_run_result(opp_id, "no_change", ran_at=completed,
                                 last_notified_version=version["version"])
            return "no_change"

        # material — email every eligible (confirmed) recipient, if we can.
        sender = get_email_sender()
        signing_key = os.environ.get("MONITORING_UNSUBSCRIBE_SIGNING_KEY", "").strip()
        base = self._public_base()
        workspace_url = f"{base}/report/{opp_id}"
        recipients = ws.eligible_recipients(opp_id)
        sent = 0
        for r in recipients:
            unsub = workspace_pkg.sign_unsubscribe_token(r["id"], signing_key)
            if not unsub:   # no signing key -> cannot offer a working opt-out
                break
            try:
                digest = monitoring_digest.render(opp, baseline, version, ev,
                                                  workspace_url,
                                                  f"{base}/api/monitoring/unsubscribe?token={unsub}")
                sender.send(r["recipient_email"], digest["subject"], digest["text_body"])
                sent += 1
            except (email_pkg.EmailError, monitoring_digest.DigestError):
                continue  # honest per-recipient failure; try the rest
        if sent:
            ws.record_run_result(opp_id, "emailed", ran_at=completed,
                                 last_notified_version=version["version"])
            return "emailed"
        # a real change we could not deliver (no SMTP / no signing key / all
        # sends failed): do NOT advance the baseline, so it retries once fixed.
        ws.record_run_result(opp_id, "email_unavailable", ran_at=completed)
        return "email_unavailable"

    # -- Phase 5: mode-aware read models ------------------------------------ #
    def _mode_overview(self, root, mode):
        """The overview payload with the effective mode applied. In normal
        mode the synthetic demo corpus is not presented as portfolio content;
        the reference evidence layer (used by the grounded Copilot) remains.
        No silent fallback between modes ever happens here."""
        p = serialize.build_payload(root)
        p["meta"]["app_mode"] = mode
        if not modes.demo_corpus_visible(mode):
            p["opportunities"] = []
            p["archived"] = []
            p["assumptions"] = []
            p["briefs"] = []
            p["feed"] = []
            p["impact_proposals"] = []
            p["meta"]["counts"] = {**p["meta"]["counts"], "opportunities": 0,
                                   "archived": 0, "assumptions": 0, "feed": 0}
            p["meta"]["generated_note"] = (
                "normal mode — demo portfolio hidden; "
                f"{len(p['evidence'])} reference evidence records available to the copilot")
        return p

    def _mode_monitoring(self, root, mode):
        """Monitoring payload with user monitoring configurations attached
        and, in normal mode, the demo/KB event corpus hidden with an honest
        summary state (never fabricated events)."""
        mon = serialize.monitoring_payload(root)
        try:
            configs = get_user_store().monitoring_list()
        except Exception:
            configs = []
        mon["user_monitoring"] = {
            "configs": configs,
            "note": ("No monitoring runner is connected yet — an enabled "
                     "configuration is 'Configured — awaiting monitoring run', "
                     "never claimed to be actively monitoring."),
        }
        if not modes.demo_corpus_visible(mode):
            mon["events"], mon["alerts"], mon["summaries"] = [], [], []
            enabled = [c for c in configs if c.get("enabled")]
            if not configs:
                status, note = "never-run", ("No monitoring is configured yet. Demo "
                                             "monitoring data is hidden in normal mode.")
            elif enabled:
                status, note = "no-events", ("Monitoring is configured for "
                                             f"{len(enabled)} opportunit"
                                             f"{'y' if len(enabled) == 1 else 'ies'} — "
                                             "awaiting the first monitoring run; no "
                                             "events exist yet.")
            else:
                status, note = "no-events", "All monitoring configurations are paused."
            mon["summary_state"] = {
                "status": status, "status_note": note,
                "last_checked": None, "latest_event_at": None,
                "event_count": 0, "open_alert_count": 0,
                "unresolved_warning_count": 0,
                "monitored_entity_count": len(configs) or None,
                "external_source_count": None, "internal_only": None,
            }
        return mon

    def _legacy_disabled(self):
        return self._error(404, "legacy ungrounded endpoint disabled — set "
                                "ENABLE_LEGACY_UNGROUNDED_ROUTES=1 to enable, or use /copilot-api/chat")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if auth_required() and self._require_session() is None:  # Phase R8a
            return
        if path.startswith("/copilot-api/"):
            return self._proxy_to_copilot("DELETE", path[len("/copilot-api"):], parsed.query, b"")
        sub = self._executive_sub(path)
        if sub is not None and sub.startswith("/user-opportunities"):
            return self._user_api("DELETE", sub, parse_qs(parsed.query))
        if sub is not None:
            m = re.match(r"^/documents/(DOC-[0-9a-f]{12})$", sub)
            if m:  # Phase R7 — permanent document deletion
                return self._document_delete(m.group(1))
        return self._error(404, "not found")

    def do_PATCH(self):
        parsed = urlparse(self.path)
        if auth_required() and self._require_session() is None:  # Phase R8a
            return
        sub = self._executive_sub(parsed.path)
        if sub is not None and sub.startswith("/user-opportunities"):
            return self._user_api("PATCH", sub, parse_qs(parsed.query))
        return self._error(404, "not found")

    def do_PUT(self):
        parsed = urlparse(self.path)
        if auth_required() and self._require_session() is None:  # Phase R8a
            return
        sub = self._executive_sub(parsed.path)
        if sub is not None and sub.startswith("/user-opportunities"):
            return self._user_api("PUT", sub, parse_qs(parsed.query))
        return self._error(404, "not found")

    @staticmethod
    def _executive_sub(path):
        """The '/api'-relative sub-path for either accepted prefix, else None."""
        if path.startswith("/executive-api/"):
            return path[len("/executive-api"):]
        if path.startswith("/api/"):
            return path[len("/api"):]
        return None

    # -- routing ----------------------------------------------------------- #
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/copilot-api/"):
            # Phase R8a — the proxy requires a session under required-auth mode
            if auth_required() and self._require_session() is None:
                return
            return self._proxy_to_copilot("GET", path[len("/copilot-api"):], parsed.query, b"")
        if path.startswith("/executive-api/"):
            return self._api(path[len("/executive-api"):], parse_qs(parsed.query))
        if path.startswith("/api/"):
            return self._api(path[len("/api"):], parse_qs(parsed.query))
        # static files stay reachable — the sign-in screen has to load
        return self._static(path)

    def _api(self, path, query):
        root = self.repo_root
        mode = modes.get_mode()
        # Phase R8a — /auth/me is the mode/identity probe and must work
        # without a session; everything else requires one when enforcement
        # is on (the read models include user data and grounded evidence).
        if path.startswith("/auth/"):
            return self._auth_api("GET", path)
        # Phase R6 — tokened unsubscribe/confirm links must work from an email
        # client with no session, even under required-auth mode (like /auth/*).
        if path == "/monitoring/unsubscribe":
            return self._monitoring_unsubscribe(query)
        if path == "/monitoring/confirm":
            return self._monitoring_confirm(query)
        if auth_required() and self._require_session() is None:
            return
        try:
            # Phase 6/7 — user-opportunity reads (mode-independent: persisted
            # user records are real product data in every mode)
            if path.startswith("/user-opportunities"):
                return self._user_api("GET", path, query)
            # Phase R1 — read-only research-run state (runtime store; real
            # product data in every mode, like user opportunities). No write
            # routes exist until the research runner (Phase R2).
            if path == "/research/runs":
                status = (query.get("status") or [None])[0]
                opp_ref = (query.get("opportunity_ref") or [None])[0]
                limit = (query.get("limit") or ["100"])[0]
                viewer = self._current_user() if auth_required() else None
                try:
                    runs = get_research_store().list_runs(
                        status=status, opportunity_ref=opp_ref,
                        limit=int(limit) if str(limit).isdigit() else 100,
                        visible_to=viewer["id"] if viewer else None)
                except research_store.ResearchStoreError as exc:
                    return self._error(exc.status, str(exc))
                return self._json({"runs": runs})
            if path == "/research/candidates":
                status_f = (query.get("status") or [None])[0]
                opp_ref = (query.get("opportunity_ref") or [None])[0]
                viewer = self._current_user() if auth_required() else None
                try:
                    return self._json({"candidates": get_research_store().list_candidates(
                        status=status_f, opportunity_ref=opp_ref,
                        visible_to=viewer["id"] if viewer else None)})
                except research_store.ResearchStoreError as exc:
                    return self._error(exc.status, str(exc))
            m = re.match(r"^/research/runs/([A-Za-z0-9-]{1,40})$", path)
            if m:
                try:
                    if not self._research_owner_guard(get_research_store(), m.group(1)):
                        return
                    return self._json(self._research_run_detail(
                        get_research_store(), m.group(1)))
                except research_store.ResearchStoreError as exc:
                    return self._error(exc.status, str(exc))
            if path in ("", "/", "/overview"):
                return self._json(self._mode_overview(root, mode))
            if path == "/experiments":
                if not modes.demo_corpus_visible(mode):
                    return self._json([])
                return self._json(serialize.experiments_payload(root))
            if path == "/journal":
                if not modes.demo_corpus_visible(mode):
                    return self._json({"predictions": [], "calibration": None,
                                       "note": "Demo predictions are hidden in normal mode."})
                return self._json(serialize.journal_payload(root))
            if path == "/monitoring":
                return self._json(self._mode_monitoring(root, mode))
            # Phase 4 — bounded, read-only per-event summary. The id segment
            # is strictly shaped here AND re-validated in serialize.py; a
            # traversal attempt never matches this route at all.
            m = re.match(r"^/monitoring/summary/([A-Za-z0-9-]{1,32})$", path)
            if m:
                if not modes.demo_corpus_visible(mode):
                    return self._error(404, "demo monitoring summaries are not available in normal mode")
                try:
                    data = serialize.monitoring_summary_payload(m.group(1), root)
                except ValueError:
                    return self._error(400, "invalid monitoring event id")
                return self._json(data) if data else self._error(404, "no summary for that event")
            m = re.match(r"^/commercial/(OPP-\d{3})$", path)
            if m:
                if not modes.demo_corpus_visible(mode):
                    return self._error(404, "demo commercial models are not available in normal mode")
                data = serialize.commercial_payload(m.group(1), root)
                return self._json(data) if data else self._error(404, "no commercial model")
            # Phase 4/6 — full web-report read model for one opportunity.
            # UOPP- ids resolve from the runtime user store in every mode;
            # committed OPP- briefs are demo corpus, hidden in normal mode.
            m = re.match(r"^/brief/([A-Za-z0-9-]{1,40})$", path)
            if m:
                rid = m.group(1)
                if rid.startswith("UOPP-"):
                    try:
                        return self._json(serialize.user_brief_payload(
                            get_user_store(), rid))
                    except user_store.StoreError as exc:
                        return self._error(exc.status, str(exc))
                if not modes.demo_corpus_visible(mode):
                    return self._error(404, "demo reports are not available in normal mode")
                try:
                    data = serialize.brief_payload(rid, root)
                except ValueError:
                    return self._error(400, "invalid opportunity id")
                return self._json(data) if data else self._error(404, "no such opportunity")
            m = re.match(r"^/opportunities/(OPP-\d{3})$", path)
            if m:
                if not modes.demo_corpus_visible(mode):
                    return self._error(404, "demo opportunities are not available in normal mode")
                ov = serialize.build_payload(root)
                for o in ov["opportunities"] + ov["archived"]:
                    if o["id"] == m.group(1):
                        return self._json(o)
                return self._error(404, "no such opportunity")
            if path in LEGACY_ROUTE_PATHS and not LEGACY_UNGROUNDED_ROUTES_ENABLED:
                return self._legacy_disabled()
            if path == "/chat":
                msg = (query.get("q") or query.get("message") or [""])[0]
                return self._json(router.route(msg, root))
            if path == "/analyze":
                msg = (query.get("q") or query.get("message") or [""])[0]
                return self._json(generate.analyze(msg, root))
            return self._error(404, f"unknown endpoint {path}")
        except Exception as exc:  # never leak a stack trace to the client
            return self._error(500, f"{type(exc).__name__}: {exc}")

    def _static(self, path):
        if not WEB_DIST.is_dir():
            return self._error(503, "web app not built — run `npm run build` in executive-ui/web")
        rel = path.lstrip("/") or "index.html"
        target = (WEB_DIST / rel).resolve()
        if not str(target).startswith(str(WEB_DIST.resolve())):
            return self._error(403, "forbidden")
        if not target.is_file():
            target = WEB_DIST / "index.html"  # SPA fallback
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _CONTENT_TYPES.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_server(port=8000, root=".", host="127.0.0.1"):
    Handler.repo_root = str(Path(root).resolve())
    return ThreadingHTTPServer((host, port), Handler)


def main():
    # PORT is the convention most PaaS/container platforms (Render, Railway,
    # ...) use to tell the app which port to bind.
    ap = argparse.ArgumentParser(description="Read-only Opportunity Intelligence API")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"),
                    help="Bind address. Use 0.0.0.0 to be reachable from outside a container.")
    ap.add_argument("--root", default=str(UI_DIR.parents[0]))
    ap.add_argument("--check-llm", metavar="PROMPT", nargs="?", const="Invoice financing for UAE logistics SMEs",
                    help="Run one analysis and report whether Claude answered (verifies ANTHROPIC_API_KEY), then exit.")
    args = ap.parse_args()

    if args.check_llm is not None:
        want = generate.provider()
        r = generate.analyze(args.check_llm, args.root)
        o = r["generated_opportunity"]
        model = generate.MODEL if want == "claude" else generate.LOCAL_MODEL if want == "local" else "—"
        print(f"configured provider   : {want}" + (f" ({model})" if want != "scaffold" else ""))
        print(f"engine that answered  : {o['engine']}"
              + ("  ✓ working" if o["engine"] == want and want != "scaffold"
                 else "  (offline scaffold)" if o["engine"] == "scaffold" else ""))
        if want != "scaffold" and o["engine"] == "scaffold" and generate._last_error:
            print(f"model error           : {generate._last_error}")
        print(f"result                : {o['name']} — {o['classification']} "
              f"(composite {o['composite']}, {o['assumption_count']}/17 assumptions)")
        return 0 if (want == "scaffold" or o["engine"] == want) else 1
    httpd = make_server(args.port, args.root, args.host)
    print(f"Read-only API on http://{args.host}:{args.port}  (root={Handler.repo_root})")
    print("Endpoints: /api/overview /api/opportunities/OPP-nnn /api/commercial/OPP-nnn "
          "/api/experiments /api/journal /api/monitoring /api/chat?q=")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
