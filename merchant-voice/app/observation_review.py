"""Human review of AI-proposed observations: queue, edit, approve, reject,
merge/supersede. The model (app/extraction.py) never touches any of this —
every transition here is a human (or human-configured-override) action,
validated and audited.

Source fields (response_id, participant_id, campaign_id, source_answer_id,
source_excerpt, source_hash, extraction_run_id) are immutable — attempting
to edit one raises Phase4Error(code="source_immutable"). Only a
pending_review observation may be edited or transitioned to
approved/rejected/superseded; approved/rejected observations are never
silently edited (models.OBSERVATION_TRANSITIONS enforces this).
"""

from . import audit, campaigns, guides, participants
from .auth import require_any_role
from .db import dumps
from .extraction import OBSERVATION_COLUMNS, OBSERVATION_SOURCE_FIELDS, _observation_row_to_dict, get_observation
from .extraction_validate import validate_observation
from .models import (OBSERVATION_EDITABLE_FIELDS, REJECTION_REASONS, Phase4Error, ValidationError,
                     validate_observation_edit)


def _require_pending(observation):
    if observation["workflow_status"] != "pending_review":
        raise Phase4Error(
            f"observation is '{observation['workflow_status']}'; only pending_review observations "
            "may be edited or reviewed directly (create a superseding observation instead)",
            code="invalid_transition")


def _require_not_suppressed(observation):
    if observation["suppression_status"] == "suppressed":
        raise Phase4Error("this observation's participant has been suppressed", code="source_suppressed")


def list_review_queue(conn, campaign_id=None, workflow_status="pending_review", include_suppressed=False):
    query = f"SELECT {OBSERVATION_COLUMNS} FROM observations WHERE 1=1"
    params = []
    if workflow_status is not None:
        query += " AND workflow_status=?"
        params.append(workflow_status)
    if campaign_id is not None:
        query += " AND campaign_id=?"
        params.append(campaign_id)
    if not include_suppressed:
        query += " AND suppression_status != 'suppressed'"
    query += " ORDER BY created_at"
    rows = conn.execute(query, params).fetchall()
    return [_observation_row_to_dict(r) for r in rows]


def get_review_context(conn, observation_id):
    """Safe review context: the observation itself, the guide question it
    answers, the (already-redacted) full source answer text, and transcript
    metadata if one exists — never identity fields, never raw transcript
    content (which no endpoint in this service ever returns)."""
    observation = get_observation(conn, observation_id)
    answer_row = conn.execute(
        "SELECT question_id, original_answer, content_purged FROM raw_answers WHERE answer_id=?",
        (observation["source_answer_id"],)).fetchone()
    question_id, redacted_answer, content_purged = answer_row
    guide_row = conn.execute("SELECT guide_id FROM responses WHERE response_id=?",
                             (observation["response_id"],)).fetchone()
    guide = guides.get(conn, guide_row[0])
    question_text = next((q["text"] for q in guide["questions"] if q["question_id"] == question_id), None)
    transcript = conn.execute(
        "SELECT extension, language, storage_status FROM transcripts WHERE response_id=?",
        (observation["response_id"],)).fetchone()
    campaign = campaigns.get(conn, observation["campaign_id"])
    return {
        "observation": observation,
        "question_text": question_text,
        "redacted_source_answer": None if content_purged or observation["suppression_status"] == "suppressed"
        else redacted_answer,
        "transcript_context": None if transcript is None else {
            "extension": transcript[0], "language": transcript[1], "storage_status": transcript[2]},
        "campaign_method": campaign["method"],
    }


def _validation_context(conn, observation):
    campaign = campaigns.get(conn, observation["campaign_id"])
    participant = participants.get(conn, observation["participant_id"])
    answer_row = conn.execute("SELECT question_id, original_answer FROM raw_answers WHERE answer_id=?",
                              (observation["source_answer_id"],)).fetchone()
    # Scoped to the whole CAMPAIGN, not just this observation's own response:
    # unlike the Phase 3 extraction model (which only ever sees one
    # response's data and so can only self-reference within it), a human
    # reviewer editing a contradiction_target has visibility across the
    # whole campaign and may legitimately link two different merchants'
    # observations as contradicting one another.
    existing_ids = {r[0] for r in conn.execute(
        "SELECT observation_id FROM observations WHERE campaign_id=?", (observation["campaign_id"],)).fetchall()}
    return {
        "answers_by_id": {observation["source_answer_id"]: {
            "question_id": answer_row[0], "original_answer": answer_row[1]}},
        "valid_seg_ids": set(campaign.get("target_segments", [])),
        "valid_opp_ids": set(campaign.get("linked_opportunities", [])),
        "valid_asm_ids": set(campaign.get("linked_assumptions", [])),
        "existing_observation_ids": existing_ids,
        "identity_strings": [participant["participant_id"], participant["merchant_identity_id"]],
        "quote_permission": bool(participant["quote_permission"]),
    }


def edit(conn, principal, observation_id, data, now):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    observation = get_observation(conn, observation_id)
    _require_pending(observation)
    _require_not_suppressed(observation)

    immutable_touched = [f for f in data if f in OBSERVATION_SOURCE_FIELDS]
    if immutable_touched:
        raise Phase4Error(f"source fields are immutable: {immutable_touched}", code="source_immutable")
    unknown = [f for f in data if f not in OBSERVATION_EDITABLE_FIELDS]
    if unknown:
        raise ValidationError(f"unknown or non-editable field(s): {unknown}")

    validate_observation_edit(data)
    merged = {**observation, **data}

    # re-run the same deterministic safeguards Phase 3 applies at creation —
    # source_excerpt/source_answer_id/extraction_confidence are immutable so
    # only the human-editable fields can actually change here
    raw_obs = {
        "observation_type": merged["observation_type"], "source_answer_id": observation["source_answer_id"],
        "source_excerpt": observation["source_excerpt"], "normalized_statement": merged["normalized_statement"],
        "is_direct_quote": merged["is_direct_quote"], "extraction_confidence": observation["extraction_confidence"],
        "frequency": merged["frequency"], "severity": merged["severity"],
        "current_workaround": merged["current_workaround"], "payment_rail": merged["payment_rail"],
        "linked_segments": merged["linked_segments"], "linked_opportunities": merged["linked_opportunities"],
        "linked_assumptions": merged["linked_assumptions"], "contradiction_target": merged["contradiction_target"],
        "follow_up_question": merged["follow_up_question"], "sensitivity_flags": [],
    }
    context = _validation_context(conn, observation)
    outcome = validate_observation(raw_obs, context)
    if not outcome.accepted:
        raise ValidationError(f"edit failed deterministic safeguards: {outcome.reason}")

    cleaned = outcome.observation
    reviewer_notes = merged.get("reviewer_notes")
    changed_fields = set(data.keys())
    if outcome.flags:
        changed_fields.add("sensitivity_flags")
    changed_fields = sorted(changed_fields)
    with conn:
        conn.execute(
            "UPDATE observations SET observation_type=?, normalized_statement=?, is_direct_quote=?, "
            "linked_segments_json=?, linked_opportunities_json=?, linked_assumptions_json=?, "
            "contradiction_target=?, frequency=?, severity=?, current_workaround=?, payment_rail=?, "
            "follow_up_question=?, sensitivity_flags_json=?, reviewer_notes=?, updated_at=? "
            "WHERE observation_id=?",
            (cleaned["observation_type"], cleaned["normalized_statement"], int(cleaned["is_direct_quote"]),
             dumps(cleaned["linked_segments"]), dumps(cleaned["linked_opportunities"]),
             dumps(cleaned["linked_assumptions"]), cleaned["contradiction_target"], cleaned["frequency"],
             cleaned["severity"], cleaned["current_workaround"], cleaned["payment_rail"],
             cleaned["follow_up_question"], dumps(cleaned["sensitivity_flags"]), reviewer_notes, now,
             observation_id))
        audit.record(conn, principal["label"], principal["role"], "edit", "observation", observation_id, now,
                    before=observation, after=cleaned, safe_diff={"fields_changed": changed_fields})
    return get_observation(conn, observation_id)


def approve(conn, config, principal, observation_id, now, reason=None):
    require_any_role(principal, ("reviewer", "admin"))
    observation = get_observation(conn, observation_id)
    _require_pending(observation)
    _require_not_suppressed(observation)

    self_approval = observation["created_by"] == principal["label"]
    if self_approval:
        if not config.allow_self_approval:
            raise Phase4Error("self-approval is not permitted (set MV_ALLOW_SELF_APPROVAL=1 to allow, audited)",
                              code="self_approval_forbidden")
        if not config.synthetic_only:
            raise Phase4Error("self-approval is only permitted in synthetic-only mode",
                              code="self_approval_forbidden")

    with conn:
        conn.execute(
            "UPDATE observations SET workflow_status='approved', reviewed_by=?, reviewed_at=?, "
            "self_approval=?, updated_at=? WHERE observation_id=?",
            (principal["label"], now, int(self_approval), now, observation_id))
        audit.record(conn, principal["label"], principal["role"], "approve", "observation", observation_id, now,
                    reason=reason, before={"workflow_status": "pending_review"},
                    after={"workflow_status": "approved"}, self_approval=self_approval)
    return get_observation(conn, observation_id)


def reject(conn, principal, observation_id, reason_code, now, reason_detail=None):
    require_any_role(principal, ("reviewer", "admin"))
    if reason_code not in REJECTION_REASONS:
        raise ValidationError(f"reason must be one of {REJECTION_REASONS}")
    observation = get_observation(conn, observation_id)
    _require_pending(observation)

    with conn:
        conn.execute(
            "UPDATE observations SET workflow_status='rejected', rejection_reason=?, reviewed_by=?, "
            "reviewed_at=?, reviewer_notes=COALESCE(?, reviewer_notes), updated_at=? WHERE observation_id=?",
            (reason_code, principal["label"], now, reason_detail, now, observation_id))
        audit.record(conn, principal["label"], principal["role"], "reject", "observation", observation_id, now,
                    reason=reason_code, before={"workflow_status": "pending_review"},
                    after={"workflow_status": "rejected", "rejection_reason": reason_code})
    return get_observation(conn, observation_id)


def merge(conn, principal, canonical_observation_id, duplicate_observation_ids, now, reason=None):
    """Merges duplicate_observation_ids into canonical_observation_id: the
    canonical observation is untouched; every duplicate is marked
    workflow_status='superseded', superseded_by_observation_id=canonical.
    Every source observation remains stored — provenance is never erased.
    Refuses to merge a contradiction into the very statement it contradicts."""
    require_any_role(principal, ("reviewer", "admin"))
    canonical = get_observation(conn, canonical_observation_id)
    if canonical["workflow_status"] not in ("pending_review", "approved"):
        raise Phase4Error("canonical observation must be pending_review or approved", code="invalid_transition")

    duplicates = [get_observation(conn, oid) for oid in duplicate_observation_ids]
    for dup in duplicates:
        if dup["observation_id"] == canonical_observation_id:
            raise ValidationError("an observation cannot be merged into itself")
        if dup["workflow_status"] not in ("pending_review", "approved"):
            raise Phase4Error(f"observation {dup['observation_id']} is '{dup['workflow_status']}' and cannot be merged",
                              code="invalid_transition")
        if dup["campaign_id"] != canonical["campaign_id"]:
            raise Phase4Error("merged observations must belong to the same campaign", code="incompatible_segment")
        if dup.get("contradiction_target") == canonical_observation_id or \
                canonical.get("contradiction_target") == dup["observation_id"]:
            raise ValidationError(
                f"observation {dup['observation_id']} contradicts the canonical observation and cannot be "
                "merged as a duplicate — contradictions must remain separately visible")

    with conn:
        for dup in duplicates:
            conn.execute(
                "UPDATE observations SET workflow_status='superseded', superseded_by_observation_id=?, "
                "updated_at=? WHERE observation_id=?", (canonical_observation_id, now, dup["observation_id"]))
            audit.record(conn, principal["label"], principal["role"], "merge", "observation", dup["observation_id"],
                        now, reason=reason, before={"workflow_status": dup["workflow_status"]},
                        after={"workflow_status": "superseded", "superseded_by_observation_id": canonical_observation_id})
    return get_observation(conn, canonical_observation_id), [get_observation(conn, d["observation_id"]) for d in duplicates]
