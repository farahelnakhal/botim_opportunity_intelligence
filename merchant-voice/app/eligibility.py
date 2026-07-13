"""Canonical extraction eligibility check — the ONE gate every extraction
entry point must call before it may ever construct a prompt or call the
provider. No code path in this service may call the provider with merchant
content without going through this function first.

All failures raise ExtractionError with one of the structured error codes
in models.EXTRACTION_ERROR_CODES; callers are responsible for auditing the
denial (never with raw content) and returning a safe error — this function
itself does not touch the audit log or the provider.
"""

from . import campaigns, participants, responses
from .consent import is_retention_expired
from .db import DbError
from .models import CAMPAIGN_METHODS


class ExtractionError(DbError):
    def __init__(self, message, code="extraction_not_permitted"):
        super().__init__(message)
        self.code = code


def check_eligibility(conn, response_id, now):
    """Returns (response, participant, campaign, eligible_answers) if and
    only if every gate passes. eligible_answers is the list of this
    response's non-purged, fully-redacted raw answers — the only content an
    extraction call may ever see."""
    response = responses.get(conn, response_id)  # DbError -> not_found if missing
    participant = participants.get(conn, response["participant_id"])
    campaign = campaigns.get(conn, response["campaign_id"])

    if campaign["method"] not in CAMPAIGN_METHODS:
        raise ExtractionError(f"campaign method is invalid: {campaign['method']!r}",
                              code="extraction_not_permitted")

    if participant["suppression_status"] == "suppressed":
        raise ExtractionError("participant is suppressed", code="consent_denied")

    if participant["consent_status"] != "granted":
        raise ExtractionError("participant consent is not granted", code="consent_denied")

    if not participant["ai_processing_permission"]:
        raise ExtractionError("participant has not granted ai_processing_permission",
                              code="ai_processing_denied")

    if is_retention_expired(participant, now):
        raise ExtractionError("participant retention has expired", code="retention_expired")

    if response["processing_status"] == "blocked_for_ai":
        raise ExtractionError("response processing_status is blocked_for_ai",
                              code="ai_processing_denied")
    if response["processing_status"] == "suppressed":
        raise ExtractionError("response processing_status is suppressed", code="consent_denied")

    if response["transcript_status"] in ("pending_deletion", "deletion_failed"):
        raise ExtractionError("transcript deletion is pending for this response",
                              code="transcript_pending_deletion")

    eligible_answers = [a for a in response["answers"] if not a["content_purged"]]
    if not eligible_answers:
        raise ExtractionError("response content has been purged", code="response_purged")

    if any(a["redaction_status"] != "complete" for a in eligible_answers):
        raise ExtractionError("redaction is not complete for every answer in this response",
                              code="redaction_incomplete")

    if any(a["original_answer"] is None or not a["original_answer"].strip() for a in eligible_answers):
        raise ExtractionError("no redacted response content is available to extract from",
                              code="response_purged")

    return response, participant, campaign, eligible_answers
