#!/usr/bin/env python3
"""BOTIM Product Discovery Copilot backend — stdlib HTTP JSON API.

Binds 127.0.0.1 by default. A non-local bind refuses to start without
COPILOT_API_TOKEN. CORS allows only the configured executive-UI origin.

Run:  python3 copilot-backend/server.py
"""

import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import logging_util                      # noqa: E402

USER_ID_RE = re.compile(r"^USER-[0-9a-f]{12}$")
from app.api import Api, error_body               # noqa: E402
from app.config import Config                     # noqa: E402
from app.orchestrator import Orchestrator         # noqa: E402
from app.store import ConversationStore           # noqa: E402


def build_handler(api, config, semaphore):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CopilotBackend/1.0"

        def log_message(self, *args):  # route through safe structured logging only
            pass

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", config.cors_origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

        def _send(self, status, body):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self):
            if not config.api_token:
                return True
            header = self.headers.get("Authorization", "")
            return header == f"Bearer {config.api_token}"

        def _handle(self, method):
            request_id = logging_util.new_request_id()
            start = time.time()
            if not self._authorized():
                self._send(401, error_body("unauthorized", "missing or invalid API token"))
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > config.max_body_bytes:
                self._send(413, error_body("message_too_long", "request body too large"))
                return
            body = self.rfile.read(length) if length else b""
            if not semaphore.acquire(timeout=config.timeout_s):
                self._send(429, error_body("rate_limited", "server busy", retryable=True))
                return
            # Phase R8b — proxy-authenticated identity. Honored ONLY when the
            # deployment explicitly trusts the fronting proxy
            # (COPILOT_TRUST_PROXY_USER=1, the single-container deploy where
            # this backend binds 127.0.0.1 and is reachable only through the
            # executive proxy, which strips client-supplied copies).
            user_id = None
            if config.trust_proxy_user:
                header = self.headers.get("X-Botim-User", "")
                if USER_ID_RE.match(header):
                    user_id = header
            try:
                status, payload = api.handle(method, self.path, body, user_id=user_id)
            finally:
                semaphore.release()
            self._send(status, payload)
            logging_util.log_request(request_id, method, self.path, status,
                                     (time.time() - start) * 1000,
                                     conversation_id=payload.get("conversation_id"))

        def do_POST(self):
            self._handle("POST")

        def do_GET(self):
            self._handle("GET")

        def do_DELETE(self):
            self._handle("DELETE")

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

    return Handler


def main():
    config = Config()
    if config.require_token() and not config.api_token:
        sys.exit("refusing to bind non-locally without COPILOT_API_TOKEN "
                 f"(host={config.host}); set the token or use 127.0.0.1")
    store = ConversationStore(config.db_path)
    api = Api(Orchestrator(config, store), store)
    semaphore = threading.BoundedSemaphore(config.max_concurrency)
    server = ThreadingHTTPServer((config.host, config.port),
                                 build_handler(api, config, semaphore))
    # Startup health report — active provider/model from the canonical
    # BOTIM_LLM_* resolution (safe source note only; never key values).
    print(f"copilot backend listening on http://{config.host}:{config.port} "
          f"(provider={config.provider}, model={config.model}, "
          f"CORS origin={config.cors_origin})")
    print(f"copilot llm config: {config.llm_source}")
    if config.provider == "unconfigured":
        print("copilot WARNING: no model provider configured — chat will return "
              "honest provider errors until BOTIM_LLM_API_KEY is set "
              "(BOTIM_LLM_PROVIDER=mock selects the deterministic demo responder).")
    server.serve_forever()


if __name__ == "__main__":
    main()
