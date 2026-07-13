"""Phase 1 HTTP endpoint handlers (framework-free; used by server.py and tests).

Routes (Phase 1 only — no participants/responses/ingestion/extraction/review/
candidates/findings/analysis/Part A proposals/Copilot tools yet):

  GET    /health
  POST   /api/merchant-voice/campaigns
  GET    /api/merchant-voice/campaigns
  GET    /api/merchant-voice/campaigns/{campaign_id}
  PATCH  /api/merchant-voice/campaigns/{campaign_id}
  POST   /api/merchant-voice/campaigns/{campaign_id}/transition

  POST   /api/merchant-voice/campaigns/{campaign_id}/guides
  GET    /api/merchant-voice/campaigns/{campaign_id}/guides
  GET    /api/merchant-voice/guides/{guide_id}
  PATCH  /api/merchant-voice/guides/{guide_id}
  POST   /api/merchant-voice/guides/{guide_id}/approve
  POST   /api/merchant-voice/guides/{guide_id}/new-version
"""

import json
import re

from . import campaigns, guides
from .auth import AuthError, authenticate
from .db import DbError
from .models import ValidationError

ERROR_STATUS = {"invalid_request": 400, "unauthorized": 401, "forbidden": 403,
                "not_found": 404, "conflict": 409, "internal": 500}

CAMPAIGN_RE = re.compile(r"^/api/merchant-voice/campaigns/([^/]+)$")
CAMPAIGN_TRANSITION_RE = re.compile(r"^/api/merchant-voice/campaigns/([^/]+)/transition$")
CAMPAIGN_GUIDES_RE = re.compile(r"^/api/merchant-voice/campaigns/([^/]+)/guides$")
GUIDE_RE = re.compile(r"^/api/merchant-voice/guides/([^/]+)$")
GUIDE_APPROVE_RE = re.compile(r"^/api/merchant-voice/guides/([^/]+)/approve$")
GUIDE_NEW_VERSION_RE = re.compile(r"^/api/merchant-voice/guides/([^/]+)/new-version$")


def error_body(code, message):
    return {"schema_version": "1.0", "error": {"code": code, "message": message}}


class Api:
    def __init__(self, config, mv_conn, now_fn):
        self.config = config
        self.conn = mv_conn
        self.now = now_fn

    def handle(self, method, path, headers, body_bytes):
        """Returns (status, dict_body). Never raises; never leaks stack traces."""
        try:
            if path == "/health" and method == "GET":
                return 200, {"schema_version": "1.0", "status": "ok",
                             "synthetic_only": self.config.synthetic_only,
                             "warning": "prototype authentication; synthetic-data-only; not for production"}
            try:
                principal = authenticate(self.config, headers.get("Authorization", ""))
            except AuthError as exc:
                return ERROR_STATUS.get(exc.code, 401), error_body(exc.code, str(exc))
            return self._route(method, path, principal, body_bytes)
        except Exception:  # never leak stack traces
            return 500, error_body("internal", "an internal error occurred")

    def _json_body(self, body_bytes):
        if not body_bytes:
            return {}
        try:
            data = json.loads(body_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValidationError("body must be valid JSON")
        if not isinstance(data, dict):
            raise ValidationError("body must be a JSON object")
        return data

    def _route(self, method, path, principal, body_bytes):
        try:
            if path == "/api/merchant-voice/campaigns":
                if method == "POST":
                    return 201, campaigns.create(self.conn, self.config, principal,
                                                 self._json_body(body_bytes), self.now())
                if method == "GET":
                    return 200, {"schema_version": "1.0", "campaigns": campaigns.list_all(self.conn)}

            m = CAMPAIGN_TRANSITION_RE.match(path)
            if m and method == "POST":
                data = self._json_body(body_bytes)
                new_status = data.get("workflow_status")
                if not new_status:
                    raise ValidationError("workflow_status is required")
                return 200, campaigns.transition(self.conn, principal, m.group(1), new_status,
                                                 self.now(), reason=data.get("reason"))

            m = CAMPAIGN_GUIDES_RE.match(path)
            if m:
                if method == "POST":
                    data = self._json_body(body_bytes)
                    return 201, guides.create(self.conn, principal, m.group(1),
                                              data.get("questions", []), self.now())
                if method == "GET":
                    return 200, {"schema_version": "1.0",
                                 "guides": guides.list_versions(self.conn, m.group(1))}

            m = CAMPAIGN_RE.match(path)
            if m:
                if method == "GET":
                    return 200, campaigns.get(self.conn, m.group(1))
                if method == "PATCH":
                    return 200, campaigns.update_draft(self.conn, principal, m.group(1),
                                                       self._json_body(body_bytes), self.config, self.now())

            m = GUIDE_APPROVE_RE.match(path)
            if m and method == "POST":
                return 200, guides.approve(self.conn, self.config, principal, m.group(1), self.now())

            m = GUIDE_NEW_VERSION_RE.match(path)
            if m and method == "POST":
                data = self._json_body(body_bytes)
                return 201, guides.new_version_from_approved(self.conn, principal, m.group(1),
                                                              self.now(), data.get("questions"))

            m = GUIDE_RE.match(path)
            if m:
                if method == "GET":
                    return 200, guides.get(self.conn, m.group(1))
                if method == "PATCH":
                    data = self._json_body(body_bytes)
                    return 200, guides.update_draft(self.conn, principal, m.group(1),
                                                    data.get("questions", []), self.now())

            return 404, error_body("not_found", "unknown endpoint")
        except AuthError as exc:
            return ERROR_STATUS.get(exc.code, 403), error_body(exc.code, str(exc))
        except ValidationError as exc:
            return 400, error_body("invalid_request", str(exc))
        except DbError as exc:
            msg = str(exc)
            code, status = ("conflict", 409) if "already exists" in msg else ("not_found", 404)
            return status, error_body(code, msg)
