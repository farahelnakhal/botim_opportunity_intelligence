"""CSV preview/commit for bulk (survey-style) response ingestion.

Preview performs no writes to participant/response/answer data — its only
write is a single-use, expiring preview-token bookkeeping row (binding file
hash + campaign + guide + actor) that commit must present unchanged. Commit
re-validates everything from scratch (participant/consent/guide state may
have changed since preview) and writes all-or-nothing inside one
transaction.

`participant_ref` must match an existing `participant_id` already created
via POST /participants — CSV import never creates merchant identities or
participants; it only maps rows onto participants that were already
properly consented.

Cell values are defensively neutralized against spreadsheet formula
injection (a value starting with '=', '+', '-', or '@' is prefixed with an
apostrophe) before being stored or echoed back, even though this service
never executes or evaluates cell content itself — the risk this guards
against is a human later opening an export in a spreadsheet application.
"""

import csv
import datetime
import hashlib
import io
import uuid

from . import audit, guides, participants, responses
from . import consent as consent_module
from .auth import require_any_role
from .db import DbError, dumps
from .models import (ANSWER_ID_RE, CSV_TOKEN_ID_RE, MAX_ANSWER_CHARS, MAX_CSV_BYTES, RESPONSE_ID_RE,
                     SEG_RE, SUPPORTED_LANGUAGES, ValidationError)
from .redaction import process_answer

REQUIRED_COLUMNS = ("participant_ref", "question_id", "answer")
OPTIONAL_COLUMNS = ("submitted_at", "language", "respondent_role", "segment_id",
                   "quote_permission", "ai_processing_permission")
FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@")


class CsvTokenError(DbError):
    pass


def _sanitize_cell(value):
    if isinstance(value, str) and value and value[0] in FORMULA_TRIGGER_CHARS:
        return "'" + value
    return value


def _parse_bool(value, field, errors, row_number):
    if value is None or value == "":
        return None
    if isinstance(value, str) and value.strip().lower() in ("true", "1"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("false", "0"):
        return False
    errors.append(f"row {row_number}: {field} must be true/false")
    return None


def _add_seconds(iso_ts, seconds):
    dt = datetime.datetime.fromisoformat(iso_ts.rstrip("Z"))
    dt = dt + datetime.timedelta(seconds=seconds)
    return dt.isoformat() + "Z"


def _load_campaign_and_guide(conn, campaign_id, guide_id):
    campaign = conn.execute("SELECT method, workflow_status FROM campaigns WHERE campaign_id=?",
                            (campaign_id,)).fetchone()
    if campaign is None:
        raise DbError(f"campaign not found: {campaign_id}")
    if campaign[1] != "active":
        raise ValidationError("campaign must be active to accept responses")
    guide = guides.get(conn, guide_id)
    if guide["campaign_id"] != campaign_id:
        raise ValidationError("guide does not belong to the referenced campaign")
    if guide["workflow_status"] != "approved":
        raise ValidationError("responses may only be ingested against an approved guide version")
    return campaign[0], guide


def _parse_rows(conn, campaign_id, guide, csv_text, now):
    reader = csv.DictReader(io.StringIO(csv_text))
    fieldnames = reader.fieldnames or []
    missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
    if missing:
        raise ValidationError(f"CSV is missing required columns: {missing}")

    valid_question_ids = {q["question_id"] for q in guide["questions"]}
    participant_cache = {}
    seen_in_batch = {}
    row_results = []

    for row_number, raw_row in enumerate(reader, start=2):
        row = {k: _sanitize_cell(v) for k, v in raw_row.items()}
        errors = []
        participant_ref = (row.get("participant_ref") or "").strip()
        question_id = (row.get("question_id") or "").strip()
        answer_text = row.get("answer") or ""

        participant = None
        if not participant_ref:
            errors.append("participant_ref is required")
        else:
            if participant_ref not in participant_cache:
                try:
                    candidate = participants.get(conn, participant_ref)
                    if candidate["campaign_id"] != campaign_id:
                        candidate = None
                except DbError:
                    candidate = None
                participant_cache[participant_ref] = candidate
            participant = participant_cache[participant_ref]
            if participant is None:
                errors.append("unknown participant_ref")
            elif participant["suppression_status"] == "suppressed" or not consent_module.consent_is_valid(
                    participant, now):
                errors.append("participant consent is not valid (missing, withdrawn, expired, or suppressed)")

        if not question_id:
            errors.append("question_id is required")
        elif question_id not in valid_question_ids:
            errors.append("question_id does not belong to the referenced guide version")

        if not answer_text.strip():
            errors.append("answer is required")
        elif len(answer_text) > MAX_ANSWER_CHARS:
            errors.append(f"answer exceeds maximum length of {MAX_ANSWER_CHARS} characters")

        language = (row.get("language") or "").strip() or "en"
        if language not in SUPPORTED_LANGUAGES:
            errors.append(f"language must be one of {SUPPORTED_LANGUAGES}")

        segment_id = (row.get("segment_id") or "").strip() or None
        if segment_id is not None and not SEG_RE.match(segment_id):
            errors.append(f"invalid segment_id: {segment_id!r}")

        quote_permission = _parse_bool(row.get("quote_permission"), "quote_permission", errors, row_number)
        ai_processing_permission = _parse_bool(
            row.get("ai_processing_permission"), "ai_processing_permission", errors, row_number)

        duplicate_of = None
        is_duplicate = False
        if not errors and participant is not None:
            answer_hash = responses.normalized_hash(answer_text)
            batch_key = (participant["participant_id"], question_id, answer_hash)
            if batch_key in seen_in_batch:
                is_duplicate = True
                duplicate_of = seen_in_batch[batch_key]
            else:
                seen_in_batch[batch_key] = row_number
                if responses.existing_duplicate(conn, participant["participant_id"], question_id, answer_hash):
                    is_duplicate = True

        status = "error" if errors else ("duplicate" if is_duplicate else "valid")
        row_results.append({
            "row_number": row_number, "participant_ref": participant_ref, "question_id": question_id,
            "answer": answer_text, "language": language, "segment_id": segment_id,
            "respondent_role": (row.get("respondent_role") or "").strip() or None,
            "submitted_at": (row.get("submitted_at") or "").strip() or None,
            "quote_permission": quote_permission, "ai_processing_permission": ai_processing_permission,
            "status": status, "errors": errors, "duplicate_of": duplicate_of,
            "participant_id": participant["participant_id"] if participant else None,
        })

    return row_results


def _summary(row_results):
    return {
        "row_count": len(row_results),
        "valid_count": sum(1 for r in row_results if r["status"] == "valid"),
        "duplicate_count": sum(1 for r in row_results if r["status"] == "duplicate"),
        "error_count": sum(1 for r in row_results if r["status"] == "error"),
    }


def preview(conn, config, principal, data, now):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    campaign_id = data.get("campaign_id")
    guide_id = data.get("guide_id")
    csv_text = data.get("csv_text")
    if not isinstance(campaign_id, str) or not campaign_id:
        raise ValidationError("campaign_id is required")
    if not isinstance(guide_id, str) or not guide_id:
        raise ValidationError("guide_id is required")
    if not isinstance(csv_text, str) or not csv_text:
        raise ValidationError("csv_text is required")
    if len(csv_text.encode("utf-8")) > MAX_CSV_BYTES:
        raise ValidationError(f"CSV exceeds the {MAX_CSV_BYTES} byte limit")

    _campaign_method, guide = _load_campaign_and_guide(conn, campaign_id, guide_id)
    row_results = _parse_rows(conn, campaign_id, guide, csv_text, now)

    file_hash = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
    token_id = "MVX-" + uuid.uuid4().hex[:12]
    expires_at = _add_seconds(now, config.csv_preview_ttl_s)
    with conn:
        conn.execute(
            "INSERT INTO csv_import_tokens (token_id, file_hash, campaign_id, guide_id, actor_label, "
            "expires_at, consumed_at, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (token_id, file_hash, campaign_id, guide_id, principal["label"], expires_at, None, now))

    return {
        "preview_token": token_id, "expires_at": expires_at,
        "summary": _summary(row_results), "rows": row_results,
    }


def commit(conn, config, principal, data, now):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    token_id = data.get("preview_token")
    campaign_id = data.get("campaign_id")
    guide_id = data.get("guide_id")
    csv_text = data.get("csv_text")
    if not isinstance(token_id, str) or not token_id:
        raise ValidationError("preview_token is required")
    if not CSV_TOKEN_ID_RE.match(token_id):
        raise ValidationError("invalid preview_token")
    if not isinstance(csv_text, str) or not csv_text:
        raise ValidationError("csv_text is required")

    token = conn.execute(
        "SELECT file_hash, campaign_id, guide_id, actor_label, expires_at, consumed_at "
        "FROM csv_import_tokens WHERE token_id=?", (token_id,)).fetchone()
    if token is None:
        raise CsvTokenError("csv preview token not found")
    file_hash, tok_campaign_id, tok_guide_id, actor_label, expires_at, consumed_at = token
    if consumed_at is not None:
        raise CsvTokenError("csv preview token has already been used")
    if expires_at <= now:
        raise CsvTokenError("csv preview token has expired; re-run preview")
    if tok_campaign_id != campaign_id or tok_guide_id != guide_id or actor_label != principal["label"]:
        raise CsvTokenError("csv preview token does not match the submitted campaign, guide, or actor")
    if hashlib.sha256(csv_text.encode("utf-8")).hexdigest() != file_hash:
        raise CsvTokenError("csv content has changed since preview; re-run preview")

    campaign_method, guide = _load_campaign_and_guide(conn, campaign_id, guide_id)
    row_results = _parse_rows(conn, campaign_id, guide, csv_text, now)

    groups = {}
    for r in row_results:
        if r["status"] == "error":
            continue
        groups.setdefault(r["participant_id"], []).append(r)

    created_response_ids = []
    created_answers = 0
    with conn:
        for participant_id, rows in groups.items():
            participant = participants.get(conn, participant_id)
            response_id = "MVR-" + uuid.uuid4().hex[:10]
            if not RESPONSE_ID_RE.match(response_id):
                raise ValidationError(f"invalid response_id: {response_id!r}")
            submitted_at = next((r["submitted_at"] for r in rows if r["submitted_at"]), now)
            any_duplicate = any(r["status"] == "duplicate" for r in rows)
            force_blocked = any(r["ai_processing_permission"] is False for r in rows)

            answer_rows = []
            for r in rows:
                redaction_status, flags = process_answer(r["answer"])
                answer_rows.append({
                    "answer_id": "MVA-" + uuid.uuid4().hex[:10], "question_id": r["question_id"],
                    "original_answer": r["answer"], "language": r["language"],
                    "is_direct_quote": bool(r["quote_permission"]) and participant["quote_permission"],
                    "redaction_status": redaction_status, "sensitive_data_flags": flags,
                    "normalized_answer_hash": responses.normalized_hash(r["answer"]),
                })

            processing_status = consent_module.compute_processing_status(
                participant, {"processing_status": "received"},
                [{"redaction_status": a["redaction_status"], "content_purged": False} for a in answer_rows], now)
            if force_blocked:
                processing_status = "blocked_for_ai"

            conn.execute(
                "INSERT INTO responses (response_id, campaign_id, participant_id, guide_id, guide_version, "
                "method, ingestion_source, submitted_at, processing_status, duplicate_status, "
                "consent_snapshot_json, transcript_status, created_by, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (response_id, campaign_id, participant_id, guide_id, guide["version"], campaign_method,
                 "csv_import", submitted_at, processing_status, "duplicate" if any_duplicate else "unique",
                 dumps(consent_module.snapshot(participant)), "none", principal["label"], now, now))
            for ar in answer_rows:
                if not ANSWER_ID_RE.match(ar["answer_id"]):
                    raise ValidationError(f"invalid answer_id: {ar['answer_id']!r}")
                conn.execute(
                    "INSERT INTO raw_answers (answer_id, response_id, question_id, original_answer, "
                    "language, transcript_location, is_direct_quote, redaction_status, "
                    "sensitive_data_flags_json, content_purged, created_at, normalized_answer_hash) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ar["answer_id"], response_id, ar["question_id"], ar["original_answer"], ar["language"],
                     None, int(ar["is_direct_quote"]), ar["redaction_status"], dumps(ar["sensitive_data_flags"]),
                     0, now, ar["normalized_answer_hash"]))
                created_answers += 1
            audit.record(conn, principal["label"], principal["role"], "create", "response", response_id, now,
                        safe_diff={"campaign_id": campaign_id, "participant_id": participant_id,
                                  "answer_count": len(answer_rows), "ingestion_source": "csv_import",
                                  "processing_status": processing_status})
            participants.mark_enrolled_if_invited(conn, participant_id, now)

            for r in rows:
                if r["segment_id"] and not participant["segment_id"]:
                    conn.execute("UPDATE participants SET segment_id=?, updated_at=? WHERE participant_id=?",
                                (r["segment_id"], now, participant_id))
                if r["respondent_role"] and not participant["respondent_role"]:
                    conn.execute("UPDATE participants SET respondent_role=?, updated_at=? WHERE participant_id=?",
                                (r["respondent_role"], now, participant_id))

            created_response_ids.append(response_id)

        conn.execute("UPDATE csv_import_tokens SET consumed_at=? WHERE token_id=?", (now, token_id))
        audit.record(conn, principal["label"], principal["role"], "csv_import_commit", "csv_import", token_id, now,
                    safe_diff={"created_responses": len(created_response_ids), "created_answers": created_answers,
                              **_summary(row_results)})

    return {
        "committed": True, "created_response_ids": created_response_ids,
        "row_results": row_results, "summary": _summary(row_results),
    }
