#!/usr/bin/env python3
"""Merchant Voice & Validation backend — stdlib HTTP JSON API (Phase 1).

PROTOTYPE-GRADE AUTHENTICATION. SYNTHETIC-DATA-ONLY IN VERSION 1.
NOT APPROVED FOR REAL MERCHANT DATA. NOT FOR PRODUCTION USE.

Binds 127.0.0.1 by default. Refuses to start without configured tokens
(MV_TOKENS). A non-local bind additionally requires tokens (mandatory either
way in this service). CORS allows only the configured frontend origin.

Run:  python3 merchant-voice/server.py
"""

import datetime
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import Api, error_body               # noqa: E402
from app.config import Config                     # noqa: E402
from app.db import connect_identity, connect_mv    # noqa: E402

STARTUP_WARNING = (
    "=" * 78 + "\n"
    "MERCHANT VOICE & VALIDATION BACKEND — PROTOTYPE\n"
    "  * Authentication is PROTOTYPE-GRADE (static token->role map). This is\n"
    "    NOT production identity/access management.\n"
    "  * SYNTHETIC-DATA-ONLY. No real merchant data may be used with this\n"
    "    service until privacy/security review has explicitly approved it.\n"
    "  * NOT approved for production use.\n" + "=" * 78
)


def _now():
    return datetime.datetime.utcnow().isoformat() + "Z"


def build_handler(api, config, semaphore):
    class Handler(BaseHTTPRequestHandler):
        server_version = "MerchantVoice/1.0"

        def log_message(self, *args):  # no default stderr logging of raw requests
            pass

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", config.cors_origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

        def _send(self, status, body):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _handle(self, method):
            length = int(self.headers.get("Content-Length") or 0)
            if length > config.max_body_bytes:
                self._send(413, error_body("invalid_request", "request body too large"))
                return
            body = self.rfile.read(length) if length else b""
            if not semaphore.acquire(timeout=config.timeout_s):
                self._send(503, error_body("internal", "server busy"))
                return
            try:
                status, payload = api.handle(method, self.path, dict(self.headers), body)
            finally:
                semaphore.release()
            self._send(status, payload)

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def do_PATCH(self):
            self._handle("PATCH")

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

    return Handler


def main():
    config = Config()
    print(STARTUP_WARNING)
    if not config.has_valid_tokens():
        sys.exit("refusing to start: no tokens configured (set MV_TOKENS, e.g. "
                 "'admin:REPLACE_ME:admin'). This service requires mandatory "
                 "token authentication even on localhost.")
    mv_conn = connect_mv(config.db_path)
    identity_conn = connect_identity(config.identity_db_path)
    api = Api(config, mv_conn, identity_conn, _now)
    semaphore = threading.BoundedSemaphore(config.max_concurrency)
    server = ThreadingHTTPServer((config.host, config.port), build_handler(api, config, semaphore))
    print(f"merchant-voice backend listening on http://{config.host}:{config.port} "
         f"(synthetic_only={config.synthetic_only}, CORS origin={config.cors_origin})")
    server.serve_forever()


if __name__ == "__main__":
    main()
