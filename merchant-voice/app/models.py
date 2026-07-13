"""Phase 1 validated models and enums: campaigns and research guides.

All merchant-content models beyond this (participants, responses, ...) are
out of scope for Phase 1 and are added in later phases.
"""

import re

from .db import DbError

CAMPAIGN_METHODS = ("survey", "interview", "concept_test")
CAMPAIGN_STATUSES = ("draft", "approved", "active", "paused", "completed", "archived")
DATA_CLASSIFICATIONS = ("synthetic", "internal", "confidential", "restricted")

# Phase 1: only "synthetic" is actually usable while MV_SYNTHETIC_ONLY is on;
# other values are modeled now so the enum is stable for later phases.
CAMPAIGN_ID_RE = re.compile(r"^MVC-[A-Za-z0-9-]{1,40}$")
GUIDE_ID_RE = re.compile(r"^MVG-[A-Za-z0-9-]{1,40}$")

# draft -> approved -> active -> paused -> completed -> archived, with the
# ability to resume from paused back to active, and archive from most states.
CAMPAIGN_TRANSITIONS = {
    "draft": {"approved"},
    "approved": {"active", "draft"},
    "active": {"paused", "completed"},
    "paused": {"active", "completed"},
    "completed": {"archived"},
    "archived": set(),
}
# archive is allowed as a terminal override from any non-archived state
ARCHIVABLE_FROM = {"draft", "approved", "active", "paused", "completed"}

QUESTION_PURPOSES = ("problem", "behaviour", "workaround", "frequency", "severity",
                     "willingness_to_pay", "switching_barrier", "trust",
                     "concept_reaction", "rejection_condition", "follow_up")
QUESTION_TYPES = ("open_text", "single_choice", "multi_choice", "scale", "yes_no")
GUIDE_STATUSES = ("draft", "approved")

OPP_RE = re.compile(r"^OPP-\d{3}$")
SEG_RE = re.compile(r"^SEG-[a-z0-9][a-z0-9-]{0,60}$")
ASM_RE = re.compile(r"^ASM-OPP-\d{3}-[a-z0-9_]{1,40}$")


class ValidationError(DbError):
    pass


def validate_campaign_input(data, synthetic_only):
    errors = []
    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("title is required")
    objective = data.get("objective")
    if not isinstance(objective, str) or not objective.strip():
        errors.append("objective is required")
    method = data.get("method")
    if method not in CAMPAIGN_METHODS:
        errors.append(f"method must be one of {CAMPAIGN_METHODS}")
    research_questions = data.get("research_questions", [])
    if not isinstance(research_questions, list) or not all(isinstance(q, str) for q in research_questions):
        errors.append("research_questions must be a list of strings")
    for field in ("target_segments", "linked_opportunities", "linked_assumptions"):
        val = data.get(field, [])
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            errors.append(f"{field} must be a list of strings")
    for seg in data.get("target_segments", []) or []:
        if isinstance(seg, str) and not SEG_RE.match(seg):
            errors.append(f"invalid target_segments id: {seg!r}")
    for opp in data.get("linked_opportunities", []) or []:
        if isinstance(opp, str) and not OPP_RE.match(opp):
            errors.append(f"invalid linked_opportunities id: {opp!r}")
    for asm in data.get("linked_assumptions", []) or []:
        if isinstance(asm, str) and not ASM_RE.match(asm):
            errors.append(f"invalid linked_assumptions id: {asm!r}")
    classification = data.get("data_classification", "synthetic")
    if classification not in DATA_CLASSIFICATIONS:
        errors.append(f"data_classification must be one of {DATA_CLASSIFICATIONS}")
    if synthetic_only and classification != "synthetic":
        errors.append("synthetic-only mode is enabled: data_classification must be 'synthetic'")
    for date_field in ("start_date", "end_date"):
        val = data.get(date_field)
        if val is not None and not isinstance(val, str):
            errors.append(f"{date_field} must be a string date or null")
    if errors:
        raise ValidationError("; ".join(errors))


def validate_transition(current_status, new_status):
    if new_status == "archived" and current_status in ARCHIVABLE_FROM:
        return
    allowed = CAMPAIGN_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise ValidationError(
            f"invalid transition '{current_status}' -> '{new_status}' "
            f"(allowed: {sorted(allowed) + (['archived'] if current_status in ARCHIVABLE_FROM else [])})")


def validate_question_input(q, position):
    errors = []
    text = q.get("text")
    if not isinstance(text, str) or not text.strip():
        errors.append(f"question[{position}].text is required")
    purpose = q.get("purpose")
    if purpose not in QUESTION_PURPOSES:
        errors.append(f"question[{position}].purpose must be one of {QUESTION_PURPOSES}")
    qtype = q.get("question_type", "open_text")
    if qtype not in QUESTION_TYPES:
        errors.append(f"question[{position}].question_type must be one of {QUESTION_TYPES}")
    follow_ups = q.get("follow_up_prompts", [])
    if not isinstance(follow_ups, list) or not all(isinstance(f, str) for f in follow_ups):
        errors.append(f"question[{position}].follow_up_prompts must be a list of strings")
    linked_asm = q.get("linked_assumption")
    if linked_asm is not None and (not isinstance(linked_asm, str) or not ASM_RE.match(linked_asm)):
        errors.append(f"question[{position}].linked_assumption invalid: {linked_asm!r}")
    linked_hyp = q.get("linked_hypothesis")
    if linked_hyp is not None and not isinstance(linked_hyp, str):
        errors.append(f"question[{position}].linked_hypothesis must be a string or null")
    if errors:
        raise ValidationError("; ".join(errors))
    return errors


def validate_questions_input(questions):
    if not isinstance(questions, list) or not questions:
        raise ValidationError("guide requires a non-empty list of questions")
    for i, q in enumerate(questions):
        validate_question_input(q, i)


# --- Phase 2: participants, responses, raw answers, ingestion ---------------
#
# Merchant identity fields (protected_external_reference and identity-level
# consent/permission) live only in identity.db — see app/identity.py. A
# participant's own consent fields may only narrow, never widen, the linked
# identity's grant (enforced in app/participants.py). No merchant contact
# data (phone/email) is modeled; `protected_external_reference` is an opaque
# researcher-assigned reference, not a raw contact channel.

MERCHANT_IDENTITY_ID_RE = re.compile(r"^MID-[A-Za-z0-9-]{1,40}$")
PARTICIPANT_ID_RE = re.compile(r"^MVP-[A-Za-z0-9-]{1,40}$")
RESPONSE_ID_RE = re.compile(r"^MVR-[A-Za-z0-9-]{1,40}$")
ANSWER_ID_RE = re.compile(r"^MVA-[A-Za-z0-9-]{1,40}$")
CSV_TOKEN_ID_RE = re.compile(r"^MVX-[A-Za-z0-9-]{1,40}$")

CONSENT_STATUSES = ("granted", "withdrawn", "expired", "pending")
PERMITTED_USE_VALUES = ("internal_research_only", "internal_research_and_product_development")
PARTICIPANT_WORKFLOW_STATUSES = ("invited", "enrolled", "completed")
SUPPRESSION_STATUSES = ("none", "suppressed")
SUPPRESSION_CAUSES = ("withdrawn", "retention_expired", "deletion_request")

RESPONSE_METHODS = CAMPAIGN_METHODS
INGESTION_SOURCES = ("manual", "csv_import")
# received: stored, not yet gated for AI eligibility (or gate not yet satisfied)
# eligible_for_ai_processing: every future-Phase-3 gate currently passes
# blocked_for_ai: a redaction failure (or explicit per-row override) blocks it
# suppressed: participant suppressed for any cause — permanently excluded
PROCESSING_STATUSES = ("received", "eligible_for_ai_processing", "blocked_for_ai", "suppressed")
DUPLICATE_STATUSES = ("unique", "duplicate")
# response-level transcript_status (attach/removal lifecycle)
TRANSCRIPT_STATUSES = ("none", "stored", "pending_deletion", "deleted", "deletion_failed")
# transcripts.storage_status uses the same vocabulary minus "none"
TRANSCRIPT_STORAGE_STATUSES = ("stored", "pending_deletion", "deleted", "deletion_failed")

REDACTION_STATUSES = ("pending", "complete", "failed", "not_required")

# Deliberately small, explicit allow-list — no free-text language values.
SUPPORTED_LANGUAGES = ("en", "ar", "ur", "hi", "fr")

TRANSCRIPT_EXTENSIONS = {"txt": "text/plain", "md": "text/markdown", "vtt": "text/vtt"}
MAX_TRANSCRIPT_BYTES = 1 * 1024 * 1024
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_ANSWER_CHARS = 20_000


def _bool_field(data, key, default=False):
    val = data.get(key, default)
    if isinstance(val, bool):
        return val
    if isinstance(val, str) and val.lower() in ("true", "false", "1", "0"):
        return val.lower() in ("true", "1")
    raise ValidationError(f"{key} must be a boolean")


def validate_participant_input(data, synthetic_only):
    errors = []
    if not isinstance(data.get("campaign_id"), str) or not data["campaign_id"]:
        errors.append("campaign_id is required")
    if not isinstance(data.get("merchant_identity_id"), str) and not isinstance(data.get("merchant_identity"), dict):
        errors.append("either merchant_identity_id or a merchant_identity object is required")
    segment_id = data.get("segment_id")
    if segment_id is not None and (not isinstance(segment_id, str) or not SEG_RE.match(segment_id)):
        errors.append(f"invalid segment_id: {segment_id!r}")
    for field in ("industry", "company_size", "geography", "respondent_role"):
        val = data.get(field)
        if val is not None and not isinstance(val, str):
            errors.append(f"{field} must be a string or null")
    consent_status = data.get("consent_status", "pending")
    if consent_status not in CONSENT_STATUSES:
        errors.append(f"consent_status must be one of {CONSENT_STATUSES}")
    permitted_use = data.get("permitted_use")
    if permitted_use not in PERMITTED_USE_VALUES:
        errors.append(f"permitted_use must be one of {PERMITTED_USE_VALUES}")
    classification = data.get("data_classification", "synthetic")
    if classification not in DATA_CLASSIFICATIONS:
        errors.append(f"data_classification must be one of {DATA_CLASSIFICATIONS}")
    if synthetic_only and classification != "synthetic":
        errors.append("synthetic-only mode is enabled: data_classification must be 'synthetic'")
    retention_expires_at = data.get("retention_expires_at")
    if retention_expires_at is not None and not isinstance(retention_expires_at, str):
        errors.append("retention_expires_at must be a string timestamp or null")
    if errors:
        raise ValidationError("; ".join(errors))


def validate_merchant_identity_input(data, synthetic_only):
    errors = []
    ref = data.get("protected_external_reference")
    if ref is not None and not isinstance(ref, str):
        errors.append("protected_external_reference must be a string or null")
    consent_status = data.get("consent_status", "pending")
    if consent_status not in CONSENT_STATUSES:
        errors.append(f"consent_status must be one of {CONSENT_STATUSES}")
    permitted_use = data.get("permitted_use")
    if permitted_use not in PERMITTED_USE_VALUES:
        errors.append(f"permitted_use must be one of {PERMITTED_USE_VALUES}")
    classification = data.get("data_classification", "synthetic")
    if classification not in DATA_CLASSIFICATIONS:
        errors.append(f"data_classification must be one of {DATA_CLASSIFICATIONS}")
    if synthetic_only and classification != "synthetic":
        errors.append("synthetic-only mode is enabled: data_classification must be 'synthetic'")
    if errors:
        raise ValidationError("; ".join(errors))


def validate_response_input(data):
    errors = []
    for field in ("campaign_id", "participant_id", "guide_id"):
        if not isinstance(data.get(field), str) or not data[field]:
            errors.append(f"{field} is required")
    method = data.get("method")
    if method not in RESPONSE_METHODS:
        errors.append(f"method must be one of {RESPONSE_METHODS}")
    answers = data.get("answers")
    if not isinstance(answers, list) or not answers:
        errors.append("answers must be a non-empty list")
    submitted_at = data.get("submitted_at")
    if submitted_at is not None and not isinstance(submitted_at, str):
        errors.append("submitted_at must be a string timestamp or null")
    if errors:
        raise ValidationError("; ".join(errors))


def validate_answer_input(answer, position):
    errors = []
    if not isinstance(answer.get("question_id"), str) or not answer["question_id"]:
        errors.append(f"answers[{position}].question_id is required")
    text = answer.get("answer")
    if not isinstance(text, str) or not text.strip():
        errors.append(f"answers[{position}].answer is required")
    elif len(text) > MAX_ANSWER_CHARS:
        errors.append(f"answers[{position}].answer exceeds maximum length of {MAX_ANSWER_CHARS} characters")
    language = answer.get("language", "en")
    if language not in SUPPORTED_LANGUAGES:
        errors.append(f"answers[{position}].language must be one of {SUPPORTED_LANGUAGES}")
    if errors:
        raise ValidationError("; ".join(errors))
