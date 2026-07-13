"""Read-only JSON API + static host for the assistant UI.

Serves the engines' read-models as JSON under /api/* and (optionally) the built
React app from web/dist. Strictly read-only: every handler is a GET that reads
engine output; there are no POST/PUT/DELETE routes, so the server cannot mutate
scorecards, evidence, the knowledge base, or impact state.

Run:
    python3 executive-ui/api/server.py [--port 8000] [--root <repo>]

During development the Vite dev server (port 5173) proxies /api here. For a
single-process deploy, build the web app (`npm run build` in executive-ui/web)
and this server will also serve web/dist.
"""

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from . import router, serialize
except ImportError:  # run directly as a script (python3 executive-ui/api/server.py)
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from api import router, serialize

UI_DIR = Path(__file__).resolve().parents[1]
WEB_DIST = UI_DIR / "web" / "dist"

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml", ".ico": "image/x-icon", ".map": "application/json",
    ".woff": "font/woff", ".woff2": "font/woff2",
}

OPP_ID = re.compile(r"^OPP-\d{3}$")


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
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.end_headers()

    # -- routing ----------------------------------------------------------- #
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
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
            if path == "/chat":
                msg = (query.get("q") or query.get("message") or [""])[0]
                return self._json(router.route(msg, root))
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


def make_server(port=8000, root="."):
    Handler.repo_root = str(Path(root).resolve())
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    ap = argparse.ArgumentParser(description="Read-only Opportunity Intelligence API")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--root", default=str(UI_DIR.parents[0]))
    args = ap.parse_args()
    httpd = make_server(args.port, args.root)
    print(f"Read-only API on http://127.0.0.1:{args.port}  (root={Handler.repo_root})")
    print("Endpoints: /api/overview /api/opportunities/OPP-nnn /api/commercial/OPP-nnn "
          "/api/experiments /api/journal /api/monitoring /api/chat?q=")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
