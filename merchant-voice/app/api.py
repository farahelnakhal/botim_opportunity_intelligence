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

Phase 3 routes (AI-assisted extraction of pending-review observations —
the model may only PROPOSE; there is no approval endpoint in this phase):

  POST   /api/merchant-voice/responses/{response_id}/extract
  GET    /api/merchant-voice/responses/{response_id}/extraction-runs
  GET    /api/merchant-voice/extraction-runs/{run_id}
  GET    /api/merchant-voice/responses/{response_id}/observations
  GET    /api/merchant-voice/observations/{observation_id}

Phase 4 routes (human review of observations, evidence candidates, approved
findings, campaign analysis — no Part A write anywhere in this service):

  GET    /api/merchant-voice/review/observations
  PATCH  /api/merchant-voice/observations/{observation_id}
  POST   /api/merchant-voice/observations/{observation_id}/approve
  POST   /api/merchant-voice/observations/{observation_id}/reject
  POST   /api/merchant-voice/observations/{observation_id}/merge

  POST   /api/merchant-voice/evidence-candidates
  GET    /api/merchant-voice/evidence-candidates
  GET    /api/merchant-voice/evidence-candidates/{candidate_id}
  PATCH  /api/merchant-voice/evidence-candidates/{candidate_id}
  POST   /api/merchant-voice/evidence-candidates/{candidate_id}/submit
  POST   /api/merchant-voice/evidence-candidates/{candidate_id}/approve
  POST   /api/merchant-voice/evidence-candidates/{candidate_id}/reject

  GET    /api/merchant-voice/findings
  GET    /api/merchant-voice/findings/{finding_id}
  POST   /api/merchant-voice/findings/{finding_id}/publish
  POST   /api/merchant-voice/findings/{finding_id}/suppress

  GET    /api/merchant-voice/campaigns/{campaign_id}/analysis
  GET    /api/merchant-voice/segments/{segment_id}/findings
  GET    /api/merchant-voice/opportunities/{opportunity_id}/findings
  GET    /api/merchant-voice/assumptions/{assumption_id}/findings

Viewer has NO access to Phase 2/3 routes, review-queue/observation-edit
routes, or evidence-candidate routes (all researcher+ at minimum) —
enforced here. Viewer MAY read published findings (GET /findings,
GET /findings/{id}, and the segment/opportunity/assumption finding
lookups — always published-only regardless of role) and campaign analysis
(aggregate counts only — no sample statement text; researcher+ see the
same analysis with sample statements included).

Still not implemented (Phase 5): Part A proposal generation/preview,
synthetic export, authoritative EV creation, Copilot Merchant Voice tools.
"""

import json
import re

from . import (analysis, campaigns, candidates, csv_import, extraction, findings, guides,
              observation_review, participants, responses, suppression, transcripts)
from .auth import AuthError, authenticate, require_any_role
from .db import DbError
from .eligibility import ExtractionError
from .models import Phase4Error, ValidationError

ERROR_STATUS = {
    "invalid_request": 400, "unauthorized": 401, "forbidden": 403, "not_found": 404, "conflict": 409,
    "internal": 500,
    # Phase 3 extraction error codes
    "extraction_not_permitted": 403, "consent_denied": 403, "ai_processing_denied": 403,
    "retention_expired": 403, "redaction_incomplete": 409, "response_purged": 409,
    "transcript_pending_deletion": 409, "provider_timeout": 504, "provider_error": 502,
    "invalid_provider_output": 502, "unsupported_excerpt": 400, "duplicate_extraction": 409,
    # Phase 4 review/candidate/finding error codes
    "invalid_transition": 409, "source_immutable": 400, "self_approval_forbidden": 403,
    "observation_not_approved": 409, "source_suppressed": 409, "incompatible_segment": 400,
    "incompatible_method": 400, "missing_support": 400, "stale_source_version": 409,
    "candidate_not_reviewable": 409, "finding_not_publishable": 409, "finding_needs_revalidation": 409,
    "quote_permission_denied": 403, "consent_invalid": 403,
    "contradiction_exclusion_requires_reason": 400,
}

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

RESPONSE_EXTRACT_RE = re.compile(r"^/api/merchant-voice/responses/([^/]+)/extract$")
RESPONSE_EXTRACTION_RUNS_RE = re.compile(r"^/api/merchant-voice/responses/([^/]+)/extraction-runs$")
EXTRACTION_RUN_RE = re.compile(r"^/api/merchant-voice/extraction-runs/([^/]+)$")
RESPONSE_OBSERVATIONS_RE = re.compile(r"^/api/merchant-voice/responses/([^/]+)/observations$")
OBSERVATION_RE = re.compile(r"^/api/merchant-voice/observations/([^/]+)$")

OBSERVATION_APPROVE_RE = re.compile(r"^/api/merchant-voice/observations/([^/]+)/approve$")
OBSERVATION_REJECT_RE = re.compile(r"^/api/merchant-voice/observations/([^/]+)/reject$")
OBSERVATION_MERGE_RE = re.compile(r"^/api/merchant-voice/observations/([^/]+)/merge$")

CANDIDATE_RE = re.compile(r"^/api/merchant-voice/evidence-candidates/([^/]+)$")
CANDIDATE_SUBMIT_RE = re.compile(r"^/api/merchant-voice/evidence-candidates/([^/]+)/submit$")
CANDIDATE_APPROVE_RE = re.compile(r"^/api/merchant-voice/evidence-candidates/([^/]+)/approve$")
CANDIDATE_REJECT_RE = re.compile(r"^/api/merchant-voice/evidence-candidates/([^/]+)/reject$")

FINDING_RE = re.compile(r"^/api/merchant-voice/findings/([^/]+)$")
FINDING_PUBLISH_RE = re.compile(r"^/api/merchant-voice/findings/([^/]+)/publish$")
FINDING_SUPPRESS_RE = re.compile(r"^/api/merchant-voice/findings/([^/]+)/suppress$")

CAMPAIGN_ANALYSIS_RE = re.compile(r"^/api/merchant-voice/campaigns/([^/]+)/analysis$")
SEGMENT_FINDINGS_RE = re.compile(r"^/api/merchant-voice/segments/([^/]+)/findings$")
OPPORTUNITY_FINDINGS_RE = re.compile(r"^/api/merchant-voice/opportunities/([^/]+)/findings$")
ASSUMPTION_FINDINGS_RE = re.compile(r"^/api/merchant-voice/assumptions/([^/]+)/findings$")

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

            # --- Phase 3: extraction --------------------------------------------
            m = RESPONSE_EXTRACT_RE.match(path)
            if m and method == "POST":
                data = self._json_body(body_bytes)
                run, observations = extraction.run_extraction(
                    self.conn, self.config, principal, m.group(1), self.now(),
                    rerun=bool(data.get("rerun", False)))
                return 201, {"schema_version": "1.0", "extraction_run": run, "observations": observations}

            m = RESPONSE_EXTRACTION_RUNS_RE.match(path)
            if m and method == "GET":
                require_any_role(principal, RESEARCH_ROLES)
                return 200, {"schema_version": "1.0",
                            "extraction_runs": extraction.list_runs_for_response(self.conn, m.group(1))}

            m = EXTRACTION_RUN_RE.match(path)
            if m and method == "GET":
                require_any_role(principal, RESEARCH_ROLES)
                return 200, extraction.get_run(self.conn, m.group(1))

            m = RESPONSE_OBSERVATIONS_RE.match(path)
            if m and method == "GET":
                require_any_role(principal, RESEARCH_ROLES)
                return 200, {"schema_version": "1.0",
                            "observations": extraction.list_observations_for_response(self.conn, m.group(1))}

            m = OBSERVATION_APPROVE_RE.match(path)
            if m and method == "POST":
                data = self._json_body(body_bytes)
                return 200, observation_review.approve(self.conn, self.config, principal, m.group(1),
                                                       self.now(), reason=data.get("reason"))

            m = OBSERVATION_REJECT_RE.match(path)
            if m and method == "POST":
                data = self._json_body(body_bytes)
                reason_code = data.get("reason")
                if not reason_code:
                    raise ValidationError("reason is required")
                return 200, observation_review.reject(self.conn, principal, m.group(1), reason_code,
                                                      self.now(), reason_detail=data.get("reason_detail"))

            m = OBSERVATION_MERGE_RE.match(path)
            if m and method == "POST":
                data = self._json_body(body_bytes)
                duplicates = data.get("duplicate_observation_ids", [])
                canonical, superseded = observation_review.merge(
                    self.conn, principal, m.group(1), duplicates, self.now(), reason=data.get("reason"))
                return 200, {"schema_version": "1.0", "canonical": canonical, "superseded": superseded}

            if path == "/api/merchant-voice/review/observations" and method == "GET":
                require_any_role(principal, RESEARCH_ROLES)
                return 200, {"schema_version": "1.0",
                            "observations": observation_review.list_review_queue(self.conn)}

            m = OBSERVATION_RE.match(path)
            if m:
                require_any_role(principal, RESEARCH_ROLES)
                if method == "GET":
                    return 200, extraction.get_observation(self.conn, m.group(1))
                if method == "PATCH":
                    return 200, observation_review.edit(self.conn, principal, m.group(1),
                                                       self._json_body(body_bytes), self.now())

            # --- Phase 4: evidence candidates -----------------------------------
            if path == "/api/merchant-voice/evidence-candidates":
                if method == "POST":
                    return 201, candidates.create(self.conn, principal, self.config,
                                                  self._json_body(body_bytes), self.now())
                if method == "GET":
                    require_any_role(principal, RESEARCH_ROLES)
                    return 200, {"schema_version": "1.0",
                                "evidence_candidates": candidates.list_all(self.conn)}

            m = CANDIDATE_SUBMIT_RE.match(path)
            if m and method == "POST":
                return 200, candidates.submit(self.conn, principal, m.group(1), self.now())

            m = CANDIDATE_APPROVE_RE.match(path)
            if m and method == "POST":
                data = self._json_body(body_bytes)
                candidate, finding = candidates.approve(self.conn, self.config, principal, m.group(1),
                                                        self.now(), reason=data.get("reason"))
                return 200, {"schema_version": "1.0", "evidence_candidate": candidate, "finding": finding}

            m = CANDIDATE_REJECT_RE.match(path)
            if m and method == "POST":
                data = self._json_body(body_bytes)
                reason_code = data.get("reason")
                if not reason_code:
                    raise ValidationError("reason is required")
                return 200, candidates.reject(self.conn, principal, m.group(1), reason_code, self.now(),
                                              reason_detail=data.get("reason_detail"))

            m = CANDIDATE_RE.match(path)
            if m:
                require_any_role(principal, RESEARCH_ROLES)
                if method == "GET":
                    return 200, candidates.get(self.conn, m.group(1))
                if method == "PATCH":
                    return 200, candidates.update_draft(self.conn, principal, m.group(1),
                                                        self._json_body(body_bytes), self.now())

            # --- Phase 4: findings -----------------------------------------------
            m = FINDING_PUBLISH_RE.match(path)
            if m and method == "POST":
                return 200, findings.publish(self.conn, principal, m.group(1), self.now())

            m = FINDING_SUPPRESS_RE.match(path)
            if m and method == "POST":
                data = self._json_body(body_bytes)
                return 200, findings.suppress(self.conn, principal, m.group(1), self.now(),
                                             reason=data.get("reason"))

            m = FINDING_RE.match(path)
            if m and method == "GET":
                if principal["role"] == "viewer":
                    return 200, findings.get_published(self.conn, m.group(1))
                return 200, findings.get(self.conn, m.group(1))

            if path == "/api/merchant-voice/findings" and method == "GET":
                published_only = principal["role"] == "viewer"
                return 200, {"schema_version": "1.0",
                            "findings": findings.list_all(self.conn, published_only=published_only)}

            # --- Phase 4: analysis / cross-cutting finding lookups ----------------
            m = CAMPAIGN_ANALYSIS_RE.match(path)
            if m and method == "GET":
                include_detail = principal["role"] != "viewer"
                return 200, {"schema_version": "1.0",
                            **analysis.compute_campaign_analysis(self.conn, m.group(1), include_detail=include_detail)}

            m = SEGMENT_FINDINGS_RE.match(path)
            if m and method == "GET":
                return 200, {"schema_version": "1.0", "findings": findings.list_for_segment(self.conn, m.group(1))}

            m = OPPORTUNITY_FINDINGS_RE.match(path)
            if m and method == "GET":
                return 200, {"schema_version": "1.0",
                            "findings": findings.list_for_opportunity(self.conn, m.group(1))}

            m = ASSUMPTION_FINDINGS_RE.match(path)
            if m and method == "GET":
                return 200, {"schema_version": "1.0",
                            "findings": findings.list_for_assumption(self.conn, m.group(1))}

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
        except ExtractionError as exc:
            return ERROR_STATUS.get(exc.code, 403), error_body(exc.code, str(exc))
        except Phase4Error as exc:
            return ERROR_STATUS.get(exc.code, 403), error_body(exc.code, str(exc))
        except DbError as exc:
            msg = str(exc)
            code, status = ("conflict", 409) if "already exists" in msg else ("not_found", 404)
            return status, error_body(code, msg)
