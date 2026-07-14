"""Manual response + raw-answer ingestion service (mv.db only).

No response ever becomes evidence here — this module only stores raw
research data with a consent snapshot, duplicate flag, and redaction
status. Findings/candidates/Part A proposals are out of scope until later
phases.

Content-visibility rule (applies uniformly to get()/list_for_campaign()):
once a participant is suppressed (withdrawn, retention_expired, or
deletion_request), every answer's `original_answer` is returned as null
with `content_visible: false` — regardless of whether the underlying row
has actually been purged (retention_expired/deletion_request) or merely
access-suppressed while the raw text is still physically retained
(withdrawn). This is enforced at read time so there is a single code path
that can never accidentally leak suppressed content.
"""

import hashlib
import uuid

from . import audit, guides, participants
from . import consent as consent_module
from .auth import require_any_role
from .consent import compute_processing_status, consent_is_valid
from .db import DbError, dumps, loads
from .models import (RESPONSE_ID_RE, ANSWER_ID_RE, ValidationError,
                     validate_answer_input, validate_response_input)
from .redaction import process_answer


def normalized_hash(text):
    normalized = " ".join(text.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def existing_duplicate(conn, participant_id, question_id, answer_hash, exclude_response_id=None):
    """Duplicate key: (participant_id, question_id, normalized answer hash) —
    checked against already-committed, non-purged answers."""
    row = conn.execute(
        "SELECT ra.answer_id FROM raw_answers ra JOIN responses r ON ra.response_id = r.response_id "
        "WHERE r.participant_id=? AND ra.question_id=? AND ra.normalized_answer_hash=? "
        "AND ra.content_purged=0" + (" AND r.response_id != ?" if exclude_response_id else ""),
        (participant_id, question_id, answer_hash) + ((exclude_response_id,) if exclude_response_id else ())
    ).fetchone()
    return row is not None


def _answer_row_to_dict(row):
    (answer_id, response_id, question_id, original_answer, language, transcript_location,
     is_direct_quote, redaction_status, sensitive_data_flags, content_purged,
     created_at, _normalized_hash) = row
    return {
        "answer_id": answer_id, "response_id": response_id, "question_id": question_id,
        "original_answer": original_answer, "language": language,
        "transcript_location": transcript_location, "is_direct_quote": bool(is_direct_quote),
        "redaction_status": redaction_status, "sensitive_data_flags": loads(sensitive_data_flags),
        "content_purged": bool(content_purged), "created_at": created_at,
    }


def _answers_for(conn, response_id):
    rows = conn.execute(
        "SELECT answer_id, response_id, question_id, original_answer, language, transcript_location, "
        "is_direct_quote, redaction_status, sensitive_data_flags_json, content_purged, created_at, "
        "normalized_answer_hash FROM raw_answers WHERE response_id=? ORDER BY created_at",
        (response_id,)).fetchall()
    return [_answer_row_to_dict(r) for r in rows]


def _apply_visibility(answers, participant_suppressed):
    out = []
    for a in answers:
        a = dict(a)
        if participant_suppressed or a["content_purged"]:
            a["original_answer"] = None
            a["content_visible"] = False
        else:
            a["content_visible"] = True
        out.append(a)
    return out


def _response_row_to_dict(row):
    (response_id, campaign_id, participant_id, guide_id, guide_version, method, ingestion_source,
     submitted_at, processing_status, duplicate_status, consent_snapshot, transcript_status,
     created_by, created_at, updated_at) = row
    return {
        "response_id": response_id, "campaign_id": campaign_id, "participant_id": participant_id,
        "guide_id": guide_id, "guide_version": guide_version, "method": method,
        "ingestion_source": ingestion_source, "submitted_at": submitted_at,
        "processing_status": processing_status, "duplicate_status": duplicate_status,
        "consent_snapshot": loads(consent_snapshot), "transcript_status": transcript_status,
        "created_by": created_by, "created_at": created_at, "updated_at": updated_at,
    }


def create(conn, config, principal, data, now):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    validate_response_input(data)

    campaign = conn.execute("SELECT method, workflow_status FROM campaigns WHERE campaign_id=?",
                            (data["campaign_id"],)).fetchone()
    if campaign is None:
        raise DbError(f"campaign not found: {data['campaign_id']}")
    campaign_method, campaign_status = campaign
    if campaign_status != "active":
        raise ValidationError("campaign must be active to accept responses")
    if data["method"] != campaign_method:
        raise ValidationError("response method must match the campaign's method")

    participant = participants.get(conn, data["participant_id"])
    if participant["campaign_id"] != data["campaign_id"]:
        raise ValidationError("participant does not belong to the referenced campaign")
    if participant["suppression_status"] == "suppressed":
        raise ValidationError("participant is suppressed; no new responses may be recorded")
    if not consent_is_valid(participant, now):
        raise ValidationError("participant consent is not valid (missing, withdrawn, or expired)")

    guide = guides.get(conn, data["guide_id"])
    if guide["campaign_id"] != data["campaign_id"]:
        raise ValidationError("guide does not belong to the referenced campaign")
    if guide["workflow_status"] != "approved":
        raise ValidationError("responses may only be ingested against an approved guide version")
    valid_question_ids = {q["question_id"] for q in guide["questions"]}

    answers_in = data["answers"]
    seen_question_ids = set()
    for i, a in enumerate(answers_in):
        validate_answer_input(a, i)
        if a["question_id"] in seen_question_ids:
            raise ValidationError(f"duplicate question_id within one response: {a['question_id']}")
        seen_question_ids.add(a["question_id"])
        if a["question_id"] not in valid_question_ids:
            raise ValidationError(f"question does not belong to the referenced guide version: {a['question_id']}")

    response_id = data.get("response_id") or ("MVR-" + uuid.uuid4().hex[:10])
    if not RESPONSE_ID_RE.match(response_id):
        raise ValidationError(f"invalid response_id: {response_id!r}")
    existing = conn.execute("SELECT 1 FROM responses WHERE response_id=?", (response_id,)).fetchone()
    if existing:
        raise ValidationError(f"response_id already exists: {response_id}")

    answer_rows = []
    any_duplicate = False
    for a in answers_in:
        answer_hash = normalized_hash(a["answer"])
        is_dup = existing_duplicate(conn, data["participant_id"], a["question_id"], answer_hash)
        any_duplicate = any_duplicate or is_dup
        redaction_status, flags = process_answer(a["answer"])
        answer_rows.append({
            "answer_id": "MVA-" + uuid.uuid4().hex[:10],
            "question_id": a["question_id"], "original_answer": a["answer"],
            "language": a.get("language", "en"), "transcript_location": None,
            "is_direct_quote": bool(a.get("is_direct_quote", False)),
            "redaction_status": redaction_status, "sensitive_data_flags": flags,
            "content_purged": False, "normalized_answer_hash": answer_hash,
            "is_duplicate": is_dup,
        })

    processing_status = compute_processing_status(
        participant, {"processing_status": "received"},
        [{"redaction_status": r["redaction_status"], "content_purged": False} for r in answer_rows], now)

    submitted_at = data.get("submitted_at") or now
    consent_snapshot = consent_module.snapshot(participant)
    duplicate_status = "duplicate" if any_duplicate else "unique"

    with conn:
        conn.execute(
            "INSERT INTO responses (response_id, campaign_id, participant_id, guide_id, guide_version, "
            "method, ingestion_source, submitted_at, processing_status, duplicate_status, "
            "consent_snapshot_json, transcript_status, created_by, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (response_id, data["campaign_id"], data["participant_id"], data["guide_id"], guide["version"],
             data["method"], "manual", submitted_at, processing_status, duplicate_status,
             dumps(consent_snapshot), "none", principal["label"], now, now))
        for ar in answer_rows:
            if not ANSWER_ID_RE.match(ar["answer_id"]):
                raise ValidationError(f"invalid answer_id: {ar['answer_id']!r}")
            conn.execute(
                "INSERT INTO raw_answers (answer_id, response_id, question_id, original_answer, "
                "language, transcript_location, is_direct_quote, redaction_status, "
                "sensitive_data_flags_json, content_purged, created_at, normalized_answer_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (ar["answer_id"], response_id, ar["question_id"], ar["original_answer"], ar["language"],
                 ar["transcript_location"], int(ar["is_direct_quote"]), ar["redaction_status"],
                 dumps(ar["sensitive_data_flags"]), int(ar["content_purged"]), now,
                 ar["normalized_answer_hash"]))
        audit.record(conn, principal["label"], principal["role"], "create", "response", response_id, now,
                    safe_diff={"campaign_id": data["campaign_id"], "participant_id": data["participant_id"],
                              "answer_count": len(answer_rows), "duplicate_status": duplicate_status,
                              "processing_status": processing_status})
        participants.mark_enrolled_if_invited(conn, data["participant_id"], now)

    return get(conn, response_id)


def get(conn, response_id):
    row = conn.execute(
        "SELECT response_id, campaign_id, participant_id, guide_id, guide_version, method, "
        "ingestion_source, submitted_at, processing_status, duplicate_status, consent_snapshot_json, "
        "transcript_status, created_by, created_at, updated_at FROM responses WHERE response_id=?",
        (response_id,)).fetchone()
    if row is None:
        raise DbError(f"response not found: {response_id}")
    response = _response_row_to_dict(row)
    participant = participants.get(conn, response["participant_id"])
    answers = _answers_for(conn, response_id)
    response["answers"] = _apply_visibility(answers, participant["suppression_status"] == "suppressed")
    return response


def list_for_campaign(conn, campaign_id, include_suppressed=False):
    query = ("SELECT response_id, campaign_id, participant_id, guide_id, guide_version, method, "
            "ingestion_source, submitted_at, processing_status, duplicate_status, consent_snapshot_json, "
            "transcript_status, created_by, created_at, updated_at FROM responses WHERE campaign_id=?")
    if not include_suppressed:
        query += " AND processing_status != 'suppressed'"
    query += " ORDER BY created_at"
    rows = conn.execute(query, (campaign_id,)).fetchall()
    out = []
    for r in rows:
        response = _response_row_to_dict(r)
        participant = participants.get(conn, response["participant_id"])
        answers = _answers_for(conn, response["response_id"])
        response["answers"] = _apply_visibility(answers, participant["suppression_status"] == "suppressed")
        out.append(response)
    return out
