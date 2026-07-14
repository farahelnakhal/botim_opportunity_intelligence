"""Pseudonymous research participant service — operates on mv.db only.

A participant links to a merchant identity (identity.db, via
`merchant_identity_id`) but never carries or exposes identity.db's own
fields (see app/identity.py). Its own consent fields (consent_status,
permitted_use, quote_permission, ai_processing_permission) may only NARROW,
never WIDEN, the linked identity's grant — enforced in `_check_narrowing`.

Viewer role has no access to this module's data at all (enforced in
app/api.py); researcher/reviewer/admin may create/read/update participants.
Suppressed participants are excluded from `list_for_campaign` by default —
this is the "normal query" exclusion; a direct `get()` by id still returns
the record (with content-visibility rules applied by callers/serializers)
so privileged roles retain compliance-lookup capability.
"""

import uuid

from . import audit, identity as identity_service
from .auth import require_any_role
from .db import DbError
from .models import (PARTICIPANT_ID_RE, PARTICIPANT_WORKFLOW_STATUSES, ValidationError,
                     validate_participant_input)

EDITABLE_FIELDS = ("segment_id", "industry", "company_size", "geography", "respondent_role",
                   "consent_status", "permitted_use", "quote_permission", "ai_processing_permission",
                   "data_classification", "retention_expires_at", "workflow_status")


def _row_to_dict(row):
    (participant_id, merchant_identity_id, campaign_id, segment_id, industry, company_size,
     geography, respondent_role, consent_status, permitted_use, quote_permission,
     ai_processing_permission, data_classification, retention_expires_at, workflow_status,
     suppression_status, suppression_cause, created_by, created_at, updated_at) = row
    return {
        "participant_id": participant_id, "merchant_identity_id": merchant_identity_id,
        "campaign_id": campaign_id, "segment_id": segment_id, "industry": industry,
        "company_size": company_size, "geography": geography, "respondent_role": respondent_role,
        "consent_status": consent_status, "permitted_use": permitted_use,
        "quote_permission": bool(quote_permission),
        "ai_processing_permission": bool(ai_processing_permission),
        "data_classification": data_classification, "retention_expires_at": retention_expires_at,
        "workflow_status": workflow_status, "suppression_status": suppression_status,
        "suppression_cause": suppression_cause, "created_by": created_by,
        "created_at": created_at, "updated_at": updated_at,
    }


def _check_narrowing(participant_fields, identity_row):
    errors = []
    if participant_fields.get("consent_status") == "granted" and identity_row["consent_status"] != "granted":
        errors.append("participant consent_status cannot be 'granted' when the linked "
                      "merchant identity's consent_status is not 'granted'")
    if participant_fields.get("quote_permission") and not identity_row["quote_permission"]:
        errors.append("participant quote_permission cannot exceed the linked merchant identity's grant")
    if participant_fields.get("ai_processing_permission") and not identity_row["ai_processing_permission"]:
        errors.append("participant ai_processing_permission cannot exceed the linked merchant identity's grant")
    if errors:
        raise ValidationError("; ".join(errors))


def create(conn, identity_conn, config, principal, data, now):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    validate_participant_input(data, config.synthetic_only)

    campaign = conn.execute("SELECT 1 FROM campaigns WHERE campaign_id=?", (data["campaign_id"],)).fetchone()
    if campaign is None:
        raise DbError(f"campaign not found: {data['campaign_id']}")

    if isinstance(data.get("merchant_identity"), dict):
        identity_row = identity_service.create(identity_conn, config, principal, data["merchant_identity"], now)
    else:
        identity_row = identity_service.get(identity_conn, data["merchant_identity_id"])

    consent_status = data.get("consent_status", identity_row["consent_status"])
    permitted_use = data.get("permitted_use", identity_row["permitted_use"])
    quote_permission = bool(data.get("quote_permission", identity_row["quote_permission"]))
    ai_processing_permission = bool(data.get("ai_processing_permission", identity_row["ai_processing_permission"]))
    fields_for_check = {"consent_status": consent_status, "quote_permission": quote_permission,
                       "ai_processing_permission": ai_processing_permission}
    _check_narrowing(fields_for_check, identity_row)

    participant_id = data.get("participant_id") or ("MVP-" + uuid.uuid4().hex[:10])
    if not PARTICIPANT_ID_RE.match(participant_id):
        raise ValidationError(f"invalid participant_id: {participant_id!r}")
    existing = conn.execute("SELECT 1 FROM participants WHERE participant_id=?", (participant_id,)).fetchone()
    if existing:
        raise ValidationError(f"participant_id already exists: {participant_id}")

    row = {
        "participant_id": participant_id, "merchant_identity_id": identity_row["merchant_identity_id"],
        "campaign_id": data["campaign_id"], "segment_id": data.get("segment_id"),
        "industry": data.get("industry"), "company_size": data.get("company_size"),
        "geography": data.get("geography"), "respondent_role": data.get("respondent_role"),
        "consent_status": consent_status, "permitted_use": permitted_use,
        "quote_permission": quote_permission, "ai_processing_permission": ai_processing_permission,
        "data_classification": data.get("data_classification", "synthetic"),
        "retention_expires_at": data.get("retention_expires_at", identity_row["retention_expires_at"]),
        "workflow_status": "invited", "suppression_status": "none", "suppression_cause": None,
        "created_by": principal["label"], "created_at": now, "updated_at": now,
    }
    with conn:
        conn.execute(
            "INSERT INTO participants (participant_id, merchant_identity_id, campaign_id, segment_id, "
            "industry, company_size, geography, respondent_role, consent_status, permitted_use, "
            "quote_permission, ai_processing_permission, data_classification, retention_expires_at, "
            "workflow_status, suppression_status, suppression_cause, created_by, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (row["participant_id"], row["merchant_identity_id"], row["campaign_id"], row["segment_id"],
             row["industry"], row["company_size"], row["geography"], row["respondent_role"],
             row["consent_status"], row["permitted_use"], int(row["quote_permission"]),
             int(row["ai_processing_permission"]), row["data_classification"], row["retention_expires_at"],
             row["workflow_status"], row["suppression_status"], row["suppression_cause"],
             row["created_by"], row["created_at"], row["updated_at"]))
        audit.record(conn, principal["label"], principal["role"], "create", "participant",
                    participant_id, now, after=row,
                    safe_diff={"campaign_id": row["campaign_id"],
                              "merchant_identity_id": row["merchant_identity_id"]})
    return row


def get(conn, participant_id):
    row = conn.execute(
        "SELECT participant_id, merchant_identity_id, campaign_id, segment_id, industry, company_size, "
        "geography, respondent_role, consent_status, permitted_use, quote_permission, "
        "ai_processing_permission, data_classification, retention_expires_at, workflow_status, "
        "suppression_status, suppression_cause, created_by, created_at, updated_at "
        "FROM participants WHERE participant_id=?", (participant_id,)).fetchone()
    if row is None:
        raise DbError(f"participant not found: {participant_id}")
    return _row_to_dict(row)


def list_for_campaign(conn, campaign_id, include_suppressed=False):
    query = ("SELECT participant_id, merchant_identity_id, campaign_id, segment_id, industry, "
            "company_size, geography, respondent_role, consent_status, permitted_use, "
            "quote_permission, ai_processing_permission, data_classification, retention_expires_at, "
            "workflow_status, suppression_status, suppression_cause, created_by, created_at, updated_at "
            "FROM participants WHERE campaign_id=?")
    params = [campaign_id]
    if not include_suppressed:
        query += " AND suppression_status != 'suppressed'"
    query += " ORDER BY created_at"
    rows = conn.execute(query, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def update(conn, identity_conn, config, principal, participant_id, data, now):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    current = get(conn, participant_id)
    if current["suppression_status"] == "suppressed":
        raise ValidationError("cannot edit a suppressed participant")
    merged = {**current, **{k: v for k, v in data.items() if k in EDITABLE_FIELDS}}
    if merged["workflow_status"] not in PARTICIPANT_WORKFLOW_STATUSES:
        raise ValidationError(f"workflow_status must be one of {PARTICIPANT_WORKFLOW_STATUSES}")
    validate_participant_input({**merged, "merchant_identity_id": current["merchant_identity_id"]},
                               config.synthetic_only)
    identity_row = identity_service.get(identity_conn, current["merchant_identity_id"])
    _check_narrowing(merged, identity_row)
    with conn:
        conn.execute(
            "UPDATE participants SET segment_id=?, industry=?, company_size=?, geography=?, "
            "respondent_role=?, consent_status=?, permitted_use=?, quote_permission=?, "
            "ai_processing_permission=?, data_classification=?, retention_expires_at=?, "
            "workflow_status=?, updated_at=? WHERE participant_id=?",
            (merged["segment_id"], merged["industry"], merged["company_size"], merged["geography"],
             merged["respondent_role"], merged["consent_status"], merged["permitted_use"],
             int(merged["quote_permission"]), int(merged["ai_processing_permission"]),
             merged["data_classification"], merged["retention_expires_at"], merged["workflow_status"],
             now, participant_id))
        audit.record(conn, principal["label"], principal["role"], "update", "participant",
                    participant_id, now, before=current, after=merged)
    return get(conn, participant_id)


def mark_enrolled_if_invited(conn, participant_id, now):
    """Called by response ingestion: a participant's first accepted response
    advances them from 'invited' to 'enrolled'. Idempotent."""
    current = get(conn, participant_id)
    if current["workflow_status"] == "invited":
        with conn:
            conn.execute("UPDATE participants SET workflow_status='enrolled', updated_at=? "
                        "WHERE participant_id=?", (now, participant_id))
