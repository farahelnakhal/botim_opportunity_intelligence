"""Safe structured logging.

Logged: request id, conversation id, intent/route, tools used, latency,
outcome category. NEVER logged: API keys, provider payloads, prompts,
reasoning, or full conversation contents.
"""

import json
import logging
import uuid

logger = logging.getLogger("copilot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def new_request_id():
    return "req_" + uuid.uuid4().hex[:10]


def log_request(request_id, method, path, status, latency_ms,
                conversation_id=None, intent=None, tools=None):
    logger.info(json.dumps({
        "request_id": request_id, "method": method, "path": path,
        "status": status, "latency_ms": round(latency_ms, 1),
        "conversation_id": conversation_id, "intent": intent,
        "tools": tools or [],
        "outcome": "ok" if status < 400 else ("client_error" if status < 500 else "server_error"),
    }))
