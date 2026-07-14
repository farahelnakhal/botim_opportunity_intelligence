"""Campaign service: create, list, get, update (draft only), transition, archive.

Rules:
- campaigns start in 'draft';
- only valid lifecycle transitions are allowed (models.CAMPAIGN_TRANSITIONS);
- create/edit requires researcher+; approve requires reviewer+; archive requires admin;
- every operation is audited;
- synthetic-only mode blocks non-synthetic data_classification.
"""

import uuid

from . import audit
from .auth import AuthError, require_any_role
from .db import DbError, dumps, loads
from .models import (CAMPAIGN_ID_RE, ValidationError, validate_campaign_input,
                     validate_transition)


def _row_to_dict(row):
    (campaign_id, title, objective, rq, ts, lo, la, method, status, owner,
     consent_template_id, data_classification, sampling_notes, start_date, end_date,
     created_by, created_at, updated_at) = row
    return {
        "campaign_id": campaign_id, "title": title, "objective": objective,
        "research_questions": loads(rq), "target_segments": loads(ts),
        "linked_opportunities": loads(lo), "linked_assumptions": loads(la),
        "method": method, "workflow_status": status, "owner": owner,
        "consent_template_id": consent_template_id, "data_classification": data_classification,
        "sampling_notes": sampling_notes, "start_date": start_date, "end_date": end_date,
        "created_by": created_by, "created_at": created_at, "updated_at": updated_at,
    }


def create(conn, config, principal, data, now):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    validate_campaign_input(data, config.synthetic_only)
    campaign_id = data.get("campaign_id") or ("MVC-" + uuid.uuid4().hex[:10])
    if not CAMPAIGN_ID_RE.match(campaign_id):
        raise ValidationError(f"invalid campaign_id: {campaign_id!r}")
    existing = conn.execute("SELECT 1 FROM campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
    if existing:
        raise ValidationError(f"campaign_id already exists: {campaign_id}")

    row = {
        "campaign_id": campaign_id, "title": data["title"].strip(),
        "objective": data["objective"].strip(),
        "research_questions": data.get("research_questions", []),
        "target_segments": data.get("target_segments", []),
        "linked_opportunities": data.get("linked_opportunities", []),
        "linked_assumptions": data.get("linked_assumptions", []),
        "method": data["method"], "workflow_status": "draft",
        "owner": data.get("owner") or principal["label"],
        "consent_template_id": data.get("consent_template_id"),
        "data_classification": data.get("data_classification", "synthetic"),
        "sampling_notes": data.get("sampling_notes"),
        "start_date": data.get("start_date"), "end_date": data.get("end_date"),
        "created_by": principal["label"], "created_at": now, "updated_at": now,
    }
    with conn:
        conn.execute(
            "INSERT INTO campaigns (campaign_id, title, objective, research_questions_json, "
            "target_segments_json, linked_opportunities_json, linked_assumptions_json, method, "
            "workflow_status, owner, consent_template_id, data_classification, sampling_notes, "
            "start_date, end_date, created_by, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (row["campaign_id"], row["title"], row["objective"], dumps(row["research_questions"]),
             dumps(row["target_segments"]), dumps(row["linked_opportunities"]),
             dumps(row["linked_assumptions"]), row["method"], row["workflow_status"], row["owner"],
             row["consent_template_id"], row["data_classification"], row["sampling_notes"],
             row["start_date"], row["end_date"], row["created_by"], row["created_at"], row["updated_at"]))
        audit.record(conn, principal["label"], principal["role"], "create", "campaign",
                    campaign_id, now, after=row)
    return row


def get(conn, campaign_id):
    row = conn.execute(
        "SELECT campaign_id, title, objective, research_questions_json, target_segments_json, "
        "linked_opportunities_json, linked_assumptions_json, method, workflow_status, owner, "
        "consent_template_id, data_classification, sampling_notes, start_date, end_date, "
        "created_by, created_at, updated_at FROM campaigns WHERE campaign_id=?",
        (campaign_id,)).fetchone()
    if row is None:
        raise DbError(f"campaign not found: {campaign_id}")
    return _row_to_dict(row)


def list_all(conn):
    rows = conn.execute(
        "SELECT campaign_id, title, objective, research_questions_json, target_segments_json, "
        "linked_opportunities_json, linked_assumptions_json, method, workflow_status, owner, "
        "consent_template_id, data_classification, sampling_notes, start_date, end_date, "
        "created_by, created_at, updated_at FROM campaigns ORDER BY created_at").fetchall()
    return [_row_to_dict(r) for r in rows]


def update_draft(conn, principal, campaign_id, data, config, now):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    current = get(conn, campaign_id)
    if current["workflow_status"] != "draft":
        raise ValidationError("only draft campaigns may be edited directly; "
                              "use transition + a new guide version for approved campaigns")
    merged = {**current, **{k: v for k, v in data.items() if k in (
        "title", "objective", "research_questions", "target_segments", "linked_opportunities",
        "linked_assumptions", "method", "owner", "consent_template_id", "data_classification",
        "sampling_notes", "start_date", "end_date")}}
    validate_campaign_input(merged, config.synthetic_only)
    with conn:
        conn.execute(
            "UPDATE campaigns SET title=?, objective=?, research_questions_json=?, "
            "target_segments_json=?, linked_opportunities_json=?, linked_assumptions_json=?, "
            "method=?, owner=?, consent_template_id=?, data_classification=?, sampling_notes=?, "
            "start_date=?, end_date=?, updated_at=? WHERE campaign_id=?",
            (merged["title"], merged["objective"], dumps(merged["research_questions"]),
             dumps(merged["target_segments"]), dumps(merged["linked_opportunities"]),
             dumps(merged["linked_assumptions"]), merged["method"], merged["owner"],
             merged["consent_template_id"], merged["data_classification"], merged["sampling_notes"],
             merged["start_date"], merged["end_date"], now, campaign_id))
        audit.record(conn, principal["label"], principal["role"], "update", "campaign",
                    campaign_id, now, before=current, after=merged)
    return get(conn, campaign_id)


def transition(conn, principal, campaign_id, new_status, now, reason=None):
    current = get(conn, campaign_id)
    validate_transition(current["workflow_status"], new_status)
    if new_status == "archived":
        require_any_role(principal, ("admin",))
    elif new_status == "approved":
        require_any_role(principal, ("reviewer", "admin"))
    else:
        require_any_role(principal, ("researcher", "reviewer", "admin"))
    with conn:
        conn.execute("UPDATE campaigns SET workflow_status=?, updated_at=? WHERE campaign_id=?",
                     (new_status, now, campaign_id))
        audit.record(conn, principal["label"], principal["role"], "transition", "campaign",
                    campaign_id, now, reason=reason,
                    before={"workflow_status": current["workflow_status"]},
                    after={"workflow_status": new_status})
    return get(conn, campaign_id)


def archive(conn, principal, campaign_id, now, reason=None):
    return transition(conn, principal, campaign_id, "archived", now, reason=reason)
