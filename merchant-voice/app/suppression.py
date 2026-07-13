"""Shared suppression routine: withdrawal, retention expiry, and deletion
requests all funnel through `suppress_participant()`, plus the recoverable
transcript-deletion workflow described in the Phase 2 plan.

Design notes (do not violate these without re-reading the approved plan):
  - `withdrawn`: the participant/responses/answers are NOT purged from
    storage — quote_permission is removed immediately and all normal read
    paths must stop returing raw content (enforced by the serializers in
    responses.py / participants.py, not here), but nothing is deleted.
  - `retention_expired` / `deletion_request`: raw answer content IS purged
    (original_answer set to NULL, content_purged=True) and any attached
    transcript is scheduled for deletion.
  - SQLite commit and filesystem deletion are never treated as one atomic
    operation. The DB transaction (suppress + mark pending_deletion + purge)
    commits first; only then is filesystem deletion attempted. If deletion
    fails, the transcript stays `pending_deletion` (never claims success)
    and a maintenance retry (`retry_pending_transcript_deletions`) can try
    again later. No transcript content or file path ever appears in an
    audit event, error message, or log line.

Later phases (findings/candidates/proposals) will need to recompute their
own state when a participant is suppressed — this module is the seam they
will hook into; no findings/candidates tables exist yet (out of Phase 2
scope), so there is nothing to recompute here yet.
"""

from . import audit
from .db import DbError
from .models import SUPPRESSION_CAUSES, ValidationError

CAUSE_REASONS = {
    "withdrawn": "participant withdrew consent",
    "retention_expired": "retention period expired",
    "deletion_request": "participant requested deletion",
}


def _responses_for_participant(conn, participant_id):
    return [r[0] for r in conn.execute(
        "SELECT response_id FROM responses WHERE participant_id=?", (participant_id,)).fetchall()]


def _answers_for_response(conn, response_id):
    return conn.execute(
        "SELECT answer_id, content_purged FROM raw_answers WHERE response_id=?", (response_id,)).fetchall()


def suppress_participant(conn, principal, participant_id, cause, now, transcript_dir=None, reason=None):
    if cause not in SUPPRESSION_CAUSES:
        raise ValidationError(f"cause must be one of {SUPPRESSION_CAUSES}")
    participant = conn.execute(
        "SELECT suppression_status FROM participants WHERE participant_id=?", (participant_id,)).fetchone()
    if participant is None:
        raise DbError(f"participant not found: {participant_id}")

    purge = cause in ("retention_expired", "deletion_request")
    response_ids = _responses_for_participant(conn, participant_id)
    purged_answers = 0
    scheduled_transcript_deletions = []

    with conn:
        consent_status = "withdrawn" if cause == "withdrawn" else None
        quote_permission = 0 if cause == "withdrawn" else None
        conn.execute(
            "UPDATE participants SET suppression_status='suppressed', suppression_cause=?, "
            "consent_status=COALESCE(?, consent_status), "
            "quote_permission=COALESCE(?, quote_permission), updated_at=? WHERE participant_id=?",
            (cause, consent_status, quote_permission, now, participant_id))

        for response_id in response_ids:
            conn.execute("UPDATE responses SET processing_status='suppressed', updated_at=? "
                        "WHERE response_id=?", (now, response_id))
            if purge:
                for answer_id, content_purged in _answers_for_response(conn, response_id):
                    if not content_purged:
                        conn.execute(
                            "UPDATE raw_answers SET original_answer=NULL, content_purged=1 "
                            "WHERE answer_id=?", (answer_id,))
                        purged_answers += 1
                transcript = conn.execute(
                    "SELECT storage_status FROM transcripts WHERE response_id=?", (response_id,)).fetchone()
                if transcript is not None and transcript[0] not in ("deleted", "pending_deletion"):
                    conn.execute(
                        "UPDATE transcripts SET storage_status='pending_deletion', updated_at=? "
                        "WHERE response_id=?", (now, response_id))
                    conn.execute(
                        "UPDATE responses SET transcript_status='pending_deletion', updated_at=? "
                        "WHERE response_id=?", (now, response_id))
                    scheduled_transcript_deletions.append(response_id)

        audit.record(conn, principal["label"], principal["role"], "suppress", "participant",
                    participant_id, now, reason=reason or CAUSE_REASONS[cause],
                    safe_diff={"cause": cause, "affected_responses": len(response_ids),
                              "purged_answers": purged_answers,
                              "scheduled_transcript_deletions": len(scheduled_transcript_deletions)})

    deletion_results = {}
    if transcript_dir is not None:
        for response_id in scheduled_transcript_deletions:
            deletion_results[response_id] = attempt_transcript_deletion(
                conn, principal, response_id, transcript_dir, now)

    return {
        "participant_id": participant_id, "cause": cause,
        "affected_responses": len(response_ids), "purged_answers": purged_answers,
        "scheduled_transcript_deletions": scheduled_transcript_deletions,
        "deletion_results": deletion_results,
    }


def attempt_transcript_deletion(conn, principal, response_id, transcript_dir, now):
    """Attempts to delete the transcript file for `response_id`. Returns True
    on success (including "file already gone"), False if deletion failed —
    in which case the transcript stays `pending_deletion` for a later retry.
    Never includes file paths or transcript content in the audit event."""
    row = conn.execute(
        "SELECT storage_filename, storage_status FROM transcripts WHERE response_id=?",
        (response_id,)).fetchone()
    if row is None or row[1] != "pending_deletion":
        return False
    storage_filename = row[0]
    path = transcript_dir / storage_filename
    try:
        path.unlink(missing_ok=True)
        succeeded = True
    except OSError:
        succeeded = False

    with conn:
        if succeeded:
            conn.execute("UPDATE transcripts SET storage_status='deleted', updated_at=? "
                        "WHERE response_id=?", (now, response_id))
            conn.execute("UPDATE responses SET transcript_status='deleted', updated_at=? "
                        "WHERE response_id=?", (now, response_id))
            audit.record(conn, principal["label"], principal["role"], "transcript_delete", "transcript",
                        response_id, now, safe_diff={"result": "success"})
        else:
            conn.execute("UPDATE transcripts SET storage_status='deletion_failed', updated_at=? "
                        "WHERE response_id=?", (now, response_id))
            conn.execute("UPDATE responses SET transcript_status='deletion_failed', updated_at=? "
                        "WHERE response_id=?", (now, response_id))
            audit.record(conn, principal["label"], principal["role"], "transcript_delete", "transcript",
                        response_id, now, safe_diff={"result": "failed"})
    return succeeded


def retry_pending_transcript_deletions(conn, principal, transcript_dir, now):
    pending = [r[0] for r in conn.execute(
        "SELECT response_id FROM transcripts WHERE storage_status IN ('pending_deletion', 'deletion_failed')"
    ).fetchall()]
    # a failed attempt is re-marked pending_deletion so retries are attempted again
    with conn:
        for response_id in pending:
            conn.execute("UPDATE transcripts SET storage_status='pending_deletion' WHERE response_id=? "
                        "AND storage_status='deletion_failed'", (response_id,))
    succeeded, failed = [], []
    for response_id in pending:
        if attempt_transcript_deletion(conn, principal, response_id, transcript_dir, now):
            succeeded.append(response_id)
        else:
            failed.append(response_id)
    return {"attempted": len(pending), "succeeded": len(succeeded), "failed": len(failed)}


def expire_retention(conn, principal, transcript_dir, now):
    expired = [r[0] for r in conn.execute(
        "SELECT participant_id FROM participants WHERE retention_expires_at IS NOT NULL "
        "AND retention_expires_at <= ? AND suppression_status != 'suppressed'", (now,)).fetchall()]
    for participant_id in expired:
        suppress_participant(conn, principal, participant_id, "retention_expired", now,
                            transcript_dir=transcript_dir)
    return {"expired_count": len(expired), "participant_ids": expired}
