"""Merchant identity service — operates ONLY on identity.db.

Merchant identity is the durable, cross-campaign privacy record for a
merchant: consent status, permitted use, quote/AI-processing permissions,
data classification, and retention/deletion timestamps. It does not store
direct contact data (no phone/email columns) — `protected_external_reference`
is an opaque, researcher-assigned reference, not a contact channel.

This module is the ONLY code in the service allowed to read or write
identity.db content. `app/participants.py` calls `get()` here solely to
validate a referenced identity exists and to read the four permission
fields needed to enforce "a participant may only narrow, never widen, the
identity-level grant" — it never returns identity.db fields to an API
caller. No viewer-facing API route touches this module at all.
"""

import uuid

from . import audit
from .db import DbError
from .models import MERCHANT_IDENTITY_ID_RE, ValidationError, validate_merchant_identity_input


def _row_to_dict(row):
    (merchant_identity_id, ref, consent_status, permitted_use, quote_permission,
     ai_processing_permission, data_classification, retention_expires_at,
     deletion_requested_at, deleted_at, created_at, updated_at) = row
    return {
        "merchant_identity_id": merchant_identity_id,
        "protected_external_reference": ref,
        "consent_status": consent_status,
        "permitted_use": permitted_use,
        "quote_permission": bool(quote_permission),
        "ai_processing_permission": bool(ai_processing_permission),
        "data_classification": data_classification,
        "retention_expires_at": retention_expires_at,
        "deletion_requested_at": deletion_requested_at,
        "deleted_at": deleted_at,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def create(identity_conn, config, principal, data, now):
    validate_merchant_identity_input(data, config.synthetic_only)
    merchant_identity_id = data.get("merchant_identity_id") or ("MID-" + uuid.uuid4().hex[:10])
    if not MERCHANT_IDENTITY_ID_RE.match(merchant_identity_id):
        raise ValidationError(f"invalid merchant_identity_id: {merchant_identity_id!r}")
    existing = identity_conn.execute(
        "SELECT 1 FROM merchant_identity WHERE merchant_identity_id=?", (merchant_identity_id,)).fetchone()
    if existing:
        raise ValidationError(f"merchant_identity_id already exists: {merchant_identity_id}")
    row = {
        "merchant_identity_id": merchant_identity_id,
        "protected_external_reference": data.get("protected_external_reference"),
        "consent_status": data.get("consent_status", "pending"),
        "permitted_use": data["permitted_use"],
        "quote_permission": bool(data.get("quote_permission", False)),
        "ai_processing_permission": bool(data.get("ai_processing_permission", False)),
        "data_classification": data.get("data_classification", "synthetic"),
        "retention_expires_at": data.get("retention_expires_at"),
        "deletion_requested_at": None,
        "deleted_at": None,
        "created_at": now, "updated_at": now,
    }
    with identity_conn:
        identity_conn.execute(
            "INSERT INTO merchant_identity (merchant_identity_id, protected_external_reference, "
            "consent_status, permitted_use, quote_permission, ai_processing_permission, "
            "data_classification, retention_expires_at, deletion_requested_at, deleted_at, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (row["merchant_identity_id"], row["protected_external_reference"], row["consent_status"],
             row["permitted_use"], int(row["quote_permission"]), int(row["ai_processing_permission"]),
             row["data_classification"], row["retention_expires_at"], row["deletion_requested_at"],
             row["deleted_at"], row["created_at"], row["updated_at"]))
        audit.record(identity_conn, principal["label"], principal["role"], "create", "merchant_identity",
                    merchant_identity_id, now, after=row)
    return row


def get(identity_conn, merchant_identity_id):
    row = identity_conn.execute(
        "SELECT merchant_identity_id, protected_external_reference, consent_status, permitted_use, "
        "quote_permission, ai_processing_permission, data_classification, retention_expires_at, "
        "deletion_requested_at, deleted_at, created_at, updated_at FROM merchant_identity "
        "WHERE merchant_identity_id=?", (merchant_identity_id,)).fetchone()
    if row is None:
        raise DbError(f"merchant identity not found: {merchant_identity_id}")
    return _row_to_dict(row)


def suppress(identity_conn, principal, merchant_identity_id, cause, now, reason=None):
    """Mirrors the participant-level suppression at the identity level: sets
    consent_status accordingly and, for retention_expired/deletion_request,
    stamps deletion_requested_at/deleted_at. Never touches mv.db."""
    current = get(identity_conn, merchant_identity_id)
    updates = {"updated_at": now}
    if cause == "withdrawn":
        updates["consent_status"] = "withdrawn"
        updates["quote_permission"] = False
    elif cause == "retention_expired":
        updates["consent_status"] = "expired"
        updates["deleted_at"] = now
    elif cause == "deletion_request":
        updates["deletion_requested_at"] = current.get("deletion_requested_at") or now
        updates["deleted_at"] = now
    with identity_conn:
        identity_conn.execute(
            "UPDATE merchant_identity SET consent_status=COALESCE(?, consent_status), "
            "quote_permission=COALESCE(?, quote_permission), deletion_requested_at=COALESCE(?, deletion_requested_at), "
            "deleted_at=COALESCE(?, deleted_at), updated_at=? WHERE merchant_identity_id=?",
            (updates.get("consent_status"),
             int(updates["quote_permission"]) if "quote_permission" in updates else None,
             updates.get("deletion_requested_at"), updates.get("deleted_at"), now, merchant_identity_id))
        audit.record(identity_conn, principal["label"], principal["role"], "suppress", "merchant_identity",
                    merchant_identity_id, now, reason=reason or f"cause={cause}",
                    safe_diff={"cause": cause})
    return get(identity_conn, merchant_identity_id)
