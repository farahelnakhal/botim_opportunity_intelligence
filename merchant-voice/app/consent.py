"""Deterministic consent/privacy gate checks, shared by participant
creation, response ingestion, and the (not-yet-built) Phase 3 AI extraction.

These functions are pure and side-effect free: they read participant/
response/answer dicts and a caller-supplied `now` timestamp (ISO8601 UTC,
matching the format used everywhere else in this service so plain string
comparison is a valid ordering check) and return booleans. No network, no
provider call, no database write.

The AI-processing gate (`ai_processing_allowed`) is implemented now, in
Phase 2, even though nothing calls a provider with merchant content yet
(Phase 3). This lets the gate be tested and enforced from day one, so a
future extraction step can only ever call it — it cannot bypass it.
"""


def is_retention_expired(record, now):
    expires = record.get("retention_expires_at")
    return bool(expires) and expires <= now


def is_suppressed(record):
    return record.get("suppression_status") == "suppressed"


def consent_is_valid(participant, now):
    """True only if consent is currently granted, not expired by retention,
    and the participant has not been suppressed for any reason."""
    if participant.get("consent_status") != "granted":
        return False
    if is_retention_expired(participant, now):
        return False
    if is_suppressed(participant):
        return False
    return True


def quote_allowed(participant, answer):
    if is_suppressed(participant):
        return False
    if not participant.get("quote_permission"):
        return False
    if not answer.get("is_direct_quote"):
        return False
    if answer.get("content_purged"):
        return False
    return True


def ai_processing_allowed(participant, response, answers, now):
    """All of the following must hold before any future provider call may
    process this response's content:
      - consent is valid (granted, not expired, not suppressed)
      - participant.ai_processing_permission is True
      - the response itself is not blocked/suppressed
      - every answer's redaction completed successfully (none pending/failed)
    """
    if not consent_is_valid(participant, now):
        return False
    if not participant.get("ai_processing_permission"):
        return False
    if response.get("processing_status") in ("blocked_for_ai", "suppressed"):
        return False
    if not answers:
        return False
    for answer in answers:
        if answer.get("content_purged"):
            return False
        if answer.get("redaction_status") != "complete":
            return False
    return True


def snapshot(participant):
    """The consent fields captured onto a response at submission time."""
    return {k: participant[k] for k in (
        "consent_status", "permitted_use", "quote_permission", "ai_processing_permission",
        "data_classification")}


def compute_processing_status(participant, response_draft, answers, now):
    """Derives the initial processing_status for a newly-ingested response."""
    if any(a.get("redaction_status") == "failed" for a in answers):
        return "blocked_for_ai"
    draft = {**response_draft, "processing_status": "received"}
    if ai_processing_allowed(participant, draft, answers, now):
        return "eligible_for_ai_processing"
    return "received"
