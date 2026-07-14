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

Phase 4 extends the cascade: every observation belonging to a response of
the suppressed participant is marked suppression_status='suppressed'
(regardless of its review workflow_status — a rejected or already-approved
observation is suppressed too, though only approved ones feed candidates/
findings). Any APPROVED evidence candidate referencing one of those
observations has its counts recalculated (app.candidates.
recalculate_for_observations), which cascades into its finding
(app.findings.recalculate) — numerator/denominator/strength_band/
publication_status update in place; publication_status becomes
needs_revalidation (if some valid support remains) or suppressed (if none
does), so a published finding is never left stale. Approved_statement/
approved_by/approved_at are historical facts and are never touched.

Phase 5 extends the cascade one step further: for every candidate whose
counts were just recalculated, if it has an approved finding
(app.findings.get_for_candidate), any non-terminal Part A proposal for that
finding is invalidated (app.part_a_proposal.invalidate_for_finding) —
marked needs_revalidation or suppressed, blocking approval/export, with an
already-exported synthetic candidate flagged as based on a superseded
version. A proposal preview is never left stale.
"""

from . import audit, candidates, findings, part_a_proposal
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
    suppressed_observation_ids = []

    with conn:
        consent_status = "withdrawn" if cause == "withdrawn" else None
        quote_permission = 0 if cause == "withdrawn" else None
        conn.execute(
            "UPDATE participants SET suppression_status='suppressed', suppression_cause=?, "
            "consent_status=COALESCE(?, consent_status), "
            "quote_permission=COALESCE(?, quote_permission), updated_at=? WHERE participant_id=?",
            (cause, consent_status, quote_permission, now, participant_id))

        suppressed_observation_ids = [r[0] for r in conn.execute(
            "SELECT observation_id FROM observations WHERE participant_id=? AND suppression_status != 'suppressed'",
            (participant_id,)).fetchall()]
        if suppressed_observation_ids:
            conn.execute("UPDATE observations SET suppression_status='suppressed', updated_at=? "
                        "WHERE participant_id=? AND suppression_status != 'suppressed'", (now, participant_id))

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
                              "suppressed_observations": len(suppressed_observation_ids),
                              "scheduled_transcript_deletions": len(scheduled_transcript_deletions)})

    deletion_results = {}
    if transcript_dir is not None:
        for response_id in scheduled_transcript_deletions:
            deletion_results[response_id] = attempt_transcript_deletion(
                conn, principal, response_id, transcript_dir, now)

    recalculated_candidate_ids = candidates.recalculate_for_observations(
        conn, suppressed_observation_ids, now, actor_id=principal["label"], actor_role=principal["role"])

    invalidated_proposal_ids = []
    for candidate_id in recalculated_candidate_ids:
        finding = findings.get_for_candidate(conn, candidate_id)
        if finding is not None:
            invalidated_proposal_ids += part_a_proposal.invalidate_for_finding(
                conn, finding["finding_id"], now, actor_id=principal["label"], actor_role=principal["role"])

    return {
        "participant_id": participant_id, "cause": cause,
        "affected_responses": len(response_ids), "purged_answers": purged_answers,
        "suppressed_observations": len(suppressed_observation_ids),
        "recalculated_candidates": recalculated_candidate_ids,
        "invalidated_proposals": invalidated_proposal_ids,
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
