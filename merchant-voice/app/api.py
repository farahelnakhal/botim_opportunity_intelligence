"""HTTP endpoint handlers (framework-free; used by server.py and tests).

Phase 1 routes: campaigns, guides (see git history for the exact Phase 1
route list — unchanged in Phase 2).

Phase 2 routes (participants, responses, CSV bulk import, transcripts,
consent/deletion, maintenance):

  POST   /api/merchant-voice/participants
  GET    /api/merchant-voice/campaigns/{campaign_id}/participants
  GET    /api/merchant-voice/participants/{participant_id}
  PATCH  /api/merchant-voice/participants/{participant_id}
  POST   /api/merchant-voice/participants/{participant_id}/withdraw-consent
  POST   /api/merchant-voice/participants/{participant_id}/request-deletion

  POST   /api/merchant-voice/responses
  GET    /api/merchant-voice/responses/{response_id}
  GET    /api/merchant-voice/campaigns/{campaign_id}/responses

  POST   /api/merchant-voice/imports/csv/preview
  POST   /api/merchant-voice/imports/csv/commit

  POST   /api/merchant-voice/responses/{response_id}/transcript
  GET    /api/merchant-voice/responses/{response_id}/transcript-metadata

  POST   /api/merchant-voice/maintenance/expire-retention
  POST   /api/merchant-voice/maintenance/retry-transcript-deletions

Viewer has NO access to any Phase 2 route (participants/responses/CSV/
transcripts/maintenance are all researcher+ at minimum) — enforced here,
before dispatching to the service layer, in addition to whatever role
checks the service functions themselves apply.

Still not implemented (Phase 3+): AI extraction, observation review,
evidence candidates, approved findings, strength analysis, campaign
aggregation, Part A proposals, Copilot tools.
"""

import json
import re

from . import campaigns, csv_import, guides, participants, responses, suppression, transcripts
from .auth import AuthError, authenticate, require_any_role
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

CAMPAIGN_PARTICIPANTS_RE = re.compile(r"^/api/merchant-voice/campaigns/([^/]+)/participants$")
PARTICIPANT_RE = re.compile(r"^/api/merchant-voice/participants/([^/]+)$")
PARTICIPANT_WITHDRAW_RE = re.compile(r"^/api/merchant-voice/participants/([^/]+)/withdraw-consent$")
PARTICIPANT_DELETE_RE = re.compile(r"^/api/merchant-voice/participants/([^/]+)/request-deletion$")

CAMPAIGN_RESPONSES_RE = re.compile(r"^/api/merchant-voice/campaigns/([^/]+)/responses$")
RESPONSE_RE = re.compile(r"^/api/merchant-voice/responses/([^/]+)$")
RESPONSE_TRANSCRIPT_RE = re.compile(r"^/api/merchant-voice/responses/([^/]+)/transcript$")
RESPONSE_TRANSCRIPT_META_RE = re.compile(r"^/api/merchant-voice/responses/([^/]+)/transcript-metadata$")

RESEARCH_ROLES = ("researcher", "reviewer", "admin")


def error_body(code, message):
    return {"schema_version": "1.0", "error": {"code": code, "message": message}}


class Api:
    def __init__(self, config, mv_conn, identity_conn, now_fn):
        self.config = config
        self.conn = mv_conn
        self.identity_conn = identity_conn
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
            # --- Phase 1: campaigns / guides ---------------------------------
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

            # --- Phase 2: participants ---------------------------------------
            if path == "/api/merchant-voice/participants" and method == "POST":
                return 201, participants.create(self.conn, self.identity_conn, self.config, principal,
                                                self._json_body(body_bytes), self.now())

            m = CAMPAIGN_PARTICIPANTS_RE.match(path)
            if m and method == "GET":
                require_any_role(principal, RESEARCH_ROLES)
                return 200, {"schema_version": "1.0",
                            "participants": participants.list_for_campaign(self.conn, m.group(1))}

            m = PARTICIPANT_WITHDRAW_RE.match(path)
            if m and method == "POST":
                data = self._json_body(body_bytes)
                require_any_role(principal, RESEARCH_ROLES)
                result = suppression.suppress_participant(
                    self.conn, principal, m.group(1), "withdrawn", self.now(),
                    transcript_dir=self.config.transcript_dir, reason=data.get("reason"))
                return 200, {"schema_version": "1.0", **result}

            m = PARTICIPANT_DELETE_RE.match(path)
            if m and method == "POST":
                data = self._json_body(body_bytes)
                require_any_role(principal, ("admin",))
                result = suppression.suppress_participant(
                    self.conn, principal, m.group(1), "deletion_request", self.now(),
                    transcript_dir=self.config.transcript_dir, reason=data.get("reason"))
                return 200, {"schema_version": "1.0", **result}

            m = PARTICIPANT_RE.match(path)
            if m:
                require_any_role(principal, RESEARCH_ROLES)
                if method == "GET":
                    return 200, participants.get(self.conn, m.group(1))
                if method == "PATCH":
                    return 200, participants.update(self.conn, self.identity_conn, self.config, principal,
                                                    m.group(1), self._json_body(body_bytes), self.now())

            # --- Phase 2: responses -------------------------------------------
            if path == "/api/merchant-voice/responses" and method == "POST":
                return 201, responses.create(self.conn, self.config, principal,
                                             self._json_body(body_bytes), self.now())

            m = CAMPAIGN_RESPONSES_RE.match(path)
            if m and method == "GET":
                require_any_role(principal, RESEARCH_ROLES)
                return 200, {"schema_version": "1.0",
                            "responses": responses.list_for_campaign(self.conn, m.group(1))}

            m = RESPONSE_TRANSCRIPT_RE.match(path)
            if m and method == "POST":
                return 201, transcripts.ingest(self.conn, self.config, principal, m.group(1),
                                              self._json_body(body_bytes), self.now())

            m = RESPONSE_TRANSCRIPT_META_RE.match(path)
            if m and method == "GET":
                require_any_role(principal, RESEARCH_ROLES)
                return 200, transcripts.get_metadata(self.conn, m.group(1))

            m = RESPONSE_RE.match(path)
            if m and method == "GET":
                require_any_role(principal, RESEARCH_ROLES)
                return 200, responses.get(self.conn, m.group(1))

            # --- Phase 2: CSV bulk import --------------------------------------
            if path == "/api/merchant-voice/imports/csv/preview" and method == "POST":
                return 200, csv_import.preview(self.conn, self.config, principal,
                                              self._json_body(body_bytes), self.now())

            if path == "/api/merchant-voice/imports/csv/commit" and method == "POST":
                return 200, csv_import.commit(self.conn, self.config, principal,
                                             self._json_body(body_bytes), self.now())

            # --- Phase 2: maintenance ------------------------------------------
            if path == "/api/merchant-voice/maintenance/expire-retention" and method == "POST":
                require_any_role(principal, ("admin",))
                result = suppression.expire_retention(self.conn, principal, self.config.transcript_dir, self.now())
                return 200, {"schema_version": "1.0", **result}

            if path == "/api/merchant-voice/maintenance/retry-transcript-deletions" and method == "POST":
                require_any_role(principal, ("admin",))
                result = suppression.retry_pending_transcript_deletions(
                    self.conn, principal, self.config.transcript_dir, self.now())
                return 200, {"schema_version": "1.0", **result}

            m = CAMPAIGN_RE.match(path)
            if m:
                if method == "GET":
                    return 200, campaigns.get(self.conn, m.group(1))
                if method == "PATCH":
                    return 200, campaigns.update_draft(self.conn, principal, m.group(1),
                                                       self._json_body(body_bytes), self.config, self.now())

            return 404, error_body("not_found", "unknown endpoint")
        except AuthError as exc:
            return ERROR_STATUS.get(exc.code, 403), error_body(exc.code, str(exc))
        except ValidationError as exc:
            return 400, error_body("invalid_request", str(exc))
        except csv_import.CsvTokenError as exc:
            return 409, error_body("conflict", str(exc))
        except DbError as exc:
            msg = str(exc)
            code, status = ("conflict", 409) if "already exists" in msg else ("not_found", 404)
            return status, error_body(code, msg)
