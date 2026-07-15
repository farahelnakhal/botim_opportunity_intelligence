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
    from . import generate, router, serialize
except ImportError:  # run directly as a script (python3 executive-ui/api/server.py)
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from api import generate, router, serialize

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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
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

    def _legacy_disabled(self):
        return self._error(404, "legacy ungrounded endpoint disabled — set "
                                "ENABLE_LEGACY_UNGROUNDED_ROUTES=1 to enable, or use /copilot-api/chat")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/copilot-api/"):
            return self._proxy_to_copilot("DELETE", path[len("/copilot-api"):], parsed.query, b"")
        return self._error(404, "not found")

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
        try:
            if path in ("", "/", "/overview"):
                return self._json(serialize.build_payload(root))
            if path == "/experiments":
                return self._json(serialize.experiments_payload(root))
            if path == "/journal":
                return self._json(serialize.journal_payload(root))
            if path == "/monitoring":
                return self._json(serialize.monitoring_payload(root))
            m = re.match(r"^/commercial/(OPP-\d{3})$", path)
            if m:
                data = serialize.commercial_payload(m.group(1), root)
                return self._json(data) if data else self._error(404, "no commercial model")
            m = re.match(r"^/opportunities/(OPP-\d{3})$", path)
            if m:
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
