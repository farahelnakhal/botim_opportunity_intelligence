"""HTTP endpoint handlers (framework-free, used by server.py and tests).

Routes:
  POST   /api/chat
  GET    /api/conversations/{id}
  GET    /api/conversations/{id}/messages
  DELETE /api/conversations/{id}
"""

import json
import re

CONV_RE = re.compile(r"^conv_[0-9a-f]{12}$")

ERROR_STATUS = {"invalid_request": 400, "unauthorized": 401, "not_found": 404,
                "conversation_not_found": 404,
                "message_too_long": 413, "rate_limited": 429,
                "provider_error": 502, "provider_timeout": 504, "internal": 500}


def error_body(code, message, retryable=False):
    return {"schema_version": "1.0",
            "error": {"code": code, "message": message, "retryable": retryable}}


class Api:
    def __init__(self, orchestrator, store):
        self.orchestrator = orchestrator
        self.store = store

    def handle(self, method, path, body_bytes):
        """Returns (status, dict_body)."""
        try:
            return self._route(method, path, body_bytes)
        except Exception:  # never leak stack traces
            return 500, error_body("internal", "an internal error occurred")

    def _route(self, method, path, body_bytes):
        if method == "POST" and path == "/api/chat":
            return self._chat(body_bytes)
        m = re.match(r"^/api/conversations/([^/]+)(/messages)?$", path)
        if m:
            cid, messages = m.group(1), bool(m.group(2))
            if not CONV_RE.match(cid):
                return 400, error_body("invalid_request", "malformed conversation id")
            if method == "GET":
                return self._get_messages(cid) if messages else self._get_conversation(cid)
            if method == "DELETE" and not messages:
                return self._delete(cid)
        return 404, error_body("not_found", "unknown endpoint")

    def _chat(self, body_bytes):
        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return 400, error_body("invalid_request", "body must be valid JSON")
        if not isinstance(payload, dict):
            return 400, error_body("invalid_request", "body must be a JSON object")
        message = payload.get("message")
        conversation_id = payload.get("conversation_id")
        context = payload.get("context") or {}
        if conversation_id is not None and not (isinstance(conversation_id, str)
                                                and CONV_RE.match(conversation_id)):
            return 400, error_body("invalid_request", "malformed conversation id")
        if not isinstance(context, dict):
            return 400, error_body("invalid_request", "context must be an object")
        result = self.orchestrator.chat(message, conversation_id, context)
        if "error" in result:
            code = result["error"]["code"]
            return ERROR_STATUS.get(code, 500), {"schema_version": "1.0", "error": result["error"]}
        return 200, result

    def _get_conversation(self, cid):
        conv = self.store.get_conversation(cid)
        if conv is None:
            return 404, error_body("not_found", "conversation not found")
        return 200, {"schema_version": "1.0", **conv}

    def _get_messages(self, cid):
        if self.store.get_conversation(cid) is None:
            return 404, error_body("not_found", "conversation not found")
        return 200, {"schema_version": "1.0", "conversation_id": cid,
                     "messages": self.store.get_messages(cid)}

    def _delete(self, cid):
        if not self.store.delete_conversation(cid):
            return 404, error_body("not_found", "conversation not found")
        return 200, {"schema_version": "1.0", "deleted": True, "conversation_id": cid}
