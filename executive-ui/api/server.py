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
    from . import generate, modes, router, serialize, user_store
except ImportError:  # run directly as a script (python3 executive-ui/api/server.py)
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from api import generate, modes, router, serialize, user_store

# shared.research lives at the repo root (the platform layer, reused later by
# the runner/monitoring), not under executive-ui — make the root importable
# when run as a script.
try:
    from shared import freshness
    from shared.research import store as research_store
    from shared.research import profiles as research_profiles
    from shared.research import providers as research_providers
    from shared.research import runner as research_runner
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from shared import freshness
    from shared.research import store as research_store
    from shared.research import profiles as research_profiles
    from shared.research import providers as research_providers
    from shared.research import runner as research_runner

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


class Handler(BaseHTTPRequestHandler):
    repo_root = "."

    def log_message(self, *args):  # quieter console
        pass

    # -- helpers ----------------------------------------------------------- #
    def _json(self, obj, status=200):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, msg):
        self._json({"error": msg}, status=status)

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
                run = store.create_run(body)
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
                body = self._read_json_body()
                return self._json(store.add_candidate(m.group(1), body), status=201)
            m = re.match(r"^/research/candidates/(RCAND-[0-9a-f]{12})/review$", sub)
            if m:
                body = self._read_json_body()
                return self._json(store.review_candidate(
                    m.group(1), body.get("action"), note=body.get("note")))
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
                     r"(?:/(archive|restore|monitoring)(?:/(pause|resume))?)?)?/?$", sub)
        if not m:
            # a syntactically different id shape (e.g. OPP-010) is a client
            # error, not a missing record — never resolves to committed data
            if sub.startswith("/user-opportunities/"):
                return self._error(400, "invalid user-opportunity id")
            return self._error(404, "unknown endpoint")
        opp_id, action, mon_action = m.group(1), m.group(2), m.group(3)
        store = get_user_store()
        try:
            if method == "GET" and opp_id is None:
                include_archived = (query.get("include_archived") or ["0"])[0] in ("1", "true")
                return self._json({"user_opportunities": store.list(include_archived=include_archived)})
            if method == "POST" and opp_id is None:
                return self._json(store.create(self._read_json_body()), status=201)
            if opp_id is None:
                return self._error(405, "method not allowed")
            if action is None:
                if method == "GET":
                    return self._json(store.get(opp_id))
                if method == "PATCH":
                    return self._json(store.update(opp_id, self._read_json_body()))
                if method == "DELETE":
                    confirm = (query.get("confirm") or [None])[0]
                    return self._json(store.delete(opp_id, confirm=confirm))
                return self._error(405, "method not allowed")
            if action == "archive" and method == "POST":
                return self._json(store.archive(opp_id))
            if action == "restore" and method == "POST":
                return self._json(store.restore(opp_id))
            if action == "monitoring":
                if mon_action == "pause" and method == "POST":
                    return self._json(store.monitoring_pause(opp_id))
                if mon_action == "resume" and method == "POST":
                    return self._json(store.monitoring_resume(opp_id))
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
        if path.startswith("/copilot-api/"):
            return self._proxy_to_copilot("DELETE", path[len("/copilot-api"):], parsed.query, b"")
        sub = self._executive_sub(path)
        if sub is not None and sub.startswith("/user-opportunities"):
            return self._user_api("DELETE", sub, parse_qs(parsed.query))
        return self._error(404, "not found")

    def do_PATCH(self):
        parsed = urlparse(self.path)
        sub = self._executive_sub(parsed.path)
        if sub is not None and sub.startswith("/user-opportunities"):
            return self._user_api("PATCH", sub, parse_qs(parsed.query))
        return self._error(404, "not found")

    def do_PUT(self):
        parsed = urlparse(self.path)
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
            return self._proxy_to_copilot("GET", path[len("/copilot-api"):], parsed.query, b"")
        if path.startswith("/executive-api/"):
            return self._api(path[len("/executive-api"):], parse_qs(parsed.query))
        if path.startswith("/api/"):
            return self._api(path[len("/api"):], parse_qs(parsed.query))
        return self._static(path)

    def _api(self, path, query):
        root = self.repo_root
        mode = modes.get_mode()
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
                try:
                    runs = get_research_store().list_runs(
                        status=status, opportunity_ref=opp_ref,
                        limit=int(limit) if str(limit).isdigit() else 100)
                except research_store.ResearchStoreError as exc:
                    return self._error(exc.status, str(exc))
                return self._json({"runs": runs})
            if path == "/research/candidates":
                status_f = (query.get("status") or [None])[0]
                opp_ref = (query.get("opportunity_ref") or [None])[0]
                try:
                    return self._json({"candidates": get_research_store().list_candidates(
                        status=status_f, opportunity_ref=opp_ref)})
                except research_store.ResearchStoreError as exc:
                    return self._error(exc.status, str(exc))
            m = re.match(r"^/research/runs/([A-Za-z0-9-]{1,40})$", path)
            if m:
                try:
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
    # PORT is the convention most PaaS/container platforms (Hugging Face Spaces,
    # Render, Railway, ...) use to tell the app which port to bind.
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
