"""Text-only transcript ingestion and storage.

Supports only .txt / .md / .vtt, max 1MB, UTF-8. The transcript directory
is never web-served (this service has no static file handler at all — see
server.py) and the stored filename is generated ONLY from the already
validated `response_id` — the caller's original filename, if any, is never
read or retained. Transcript text is stored on disk only; the database
holds metadata (extension, content type, language, size, storage status,
speaker map) and never the transcript content itself, so transcript text
can never appear in a normal API response, a log line, or an audit event.

Ingestion is written so a failure partway through cannot leave the
database referencing a file that doesn't exist, or a file on disk with no
database record: the file is written first (atomically, via a temp file +
os.replace), and only then is the database updated inside a transaction;
if that transaction fails, the just-written file is removed again
(best-effort) before the error propagates.
"""

import os
import uuid

from . import audit
from .auth import require_any_role
from .db import DbError, dumps, loads
from .models import MAX_TRANSCRIPT_BYTES, TRANSCRIPT_EXTENSIONS, SUPPORTED_LANGUAGES, ValidationError


def _validate_text(text):
    if not isinstance(text, str):
        raise ValidationError("transcript_text must be a string")
    if any(ord(ch) < 32 and ch not in ("\n", "\r", "\t") for ch in text):
        raise ValidationError("transcript_text contains non-text control bytes; only plain text is accepted")
    size = len(text.encode("utf-8"))
    if size > MAX_TRANSCRIPT_BYTES:
        raise ValidationError(f"transcript exceeds the {MAX_TRANSCRIPT_BYTES} byte limit")
    return size


def _row_to_dict(row):
    (response_id, extension, content_type, language, size_bytes, storage_status,
     speaker_map, storage_filename, created_at, updated_at) = row
    return {
        "response_id": response_id, "extension": extension, "content_type": content_type,
        "language": language, "size_bytes": size_bytes, "storage_status": storage_status,
        "speaker_map": loads(speaker_map), "created_at": created_at, "updated_at": updated_at,
    }


def ingest(conn, config, principal, response_id, data, now):
    require_any_role(principal, ("researcher", "reviewer", "admin"))

    response = conn.execute("SELECT participant_id FROM responses WHERE response_id=?",
                            (response_id,)).fetchone()
    if response is None:
        raise DbError(f"response not found: {response_id}")
    participant = conn.execute("SELECT suppression_status FROM participants WHERE participant_id=?",
                               (response[0],)).fetchone()
    if participant is not None and participant[0] == "suppressed":
        raise ValidationError("cannot attach a transcript to a suppressed participant's response")

    extension = data.get("extension")
    if extension not in TRANSCRIPT_EXTENSIONS:
        raise ValidationError(f"extension must be one of {sorted(TRANSCRIPT_EXTENSIONS)}")
    content_type = data.get("content_type")
    if content_type is not None and content_type != TRANSCRIPT_EXTENSIONS[extension]:
        raise ValidationError(
            f"content_type {content_type!r} does not match extension {extension!r} "
            f"(expected {TRANSCRIPT_EXTENSIONS[extension]!r})")
    language = data.get("language")
    if language is not None and language not in SUPPORTED_LANGUAGES:
        raise ValidationError(f"language must be one of {SUPPORTED_LANGUAGES}")
    speaker_map = data.get("speaker_map", {})
    if not isinstance(speaker_map, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in speaker_map.items()):
        raise ValidationError("speaker_map must be an object of string -> string")

    size_bytes = _validate_text(data.get("transcript_text"))
    storage_filename = f"{response_id}.{extension}"

    transcript_dir = config.transcript_dir
    transcript_dir.mkdir(parents=True, exist_ok=True)
    final_path = (transcript_dir / storage_filename).resolve()
    if transcript_dir.resolve() not in final_path.parents:
        raise ValidationError("invalid transcript storage path")
    tmp_path = transcript_dir / f".{uuid.uuid4().hex}.tmp"
    tmp_path.write_text(data["transcript_text"], encoding="utf-8")
    os.replace(tmp_path, final_path)

    try:
        with conn:
            conn.execute(
                "INSERT INTO transcripts (response_id, extension, content_type, language, size_bytes, "
                "storage_status, speaker_map_json, storage_filename, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(response_id) DO UPDATE SET extension=excluded.extension, "
                "content_type=excluded.content_type, language=excluded.language, "
                "size_bytes=excluded.size_bytes, storage_status=excluded.storage_status, "
                "speaker_map_json=excluded.speaker_map_json, storage_filename=excluded.storage_filename, "
                "updated_at=excluded.updated_at",
                (response_id, extension, content_type, language, size_bytes, "stored",
                 dumps(speaker_map), storage_filename, now, now))
            conn.execute("UPDATE responses SET transcript_status='stored', updated_at=? WHERE response_id=?",
                        (now, response_id))
            audit.record(conn, principal["label"], principal["role"], "transcript_ingest", "transcript",
                        response_id, now, safe_diff={"extension": extension, "size_bytes": size_bytes,
                                                     "language": language})
    except Exception:
        final_path.unlink(missing_ok=True)
        raise

    return get_metadata(conn, response_id)


def get_metadata(conn, response_id):
    row = conn.execute(
        "SELECT response_id, extension, content_type, language, size_bytes, storage_status, "
        "speaker_map_json, storage_filename, created_at, updated_at FROM transcripts WHERE response_id=?",
        (response_id,)).fetchone()
    if row is None:
        raise DbError(f"no transcript stored for response: {response_id}")
    return _row_to_dict(row)
