"""Research guide service: versioned, immutable once approved.

Rules:
- guide questions validate against the approved taxonomy;
- approved versions are immutable — editing an approved guide requires a new version;
- self-approval is rejected unless MV_ALLOW_SELF_APPROVAL=1, and when enabled the
  audit event records self_approval=true;
- creating/editing requires researcher+; approving requires reviewer+.
"""

import uuid

from . import audit
from .auth import AuthError, require_any_role
from .db import DbError, dumps, loads
from .models import GUIDE_ID_RE, ValidationError, validate_questions_input


def _question_row(guide_id, position, q):
    qid = q.get("question_id") or (f"{guide_id}-Q{position + 1}")
    return {
        "question_id": qid, "guide_id": guide_id, "text": q["text"].strip(),
        "purpose": q["purpose"], "question_type": q.get("question_type", "open_text"),
        "follow_up_prompts": q.get("follow_up_prompts", []),
        "linked_assumption": q.get("linked_assumption"),
        "linked_hypothesis": q.get("linked_hypothesis"), "position": position,
    }


def _insert_questions(conn, guide_id, questions):
    rows = [_question_row(guide_id, i, q) for i, q in enumerate(questions)]
    for r in rows:
        conn.execute(
            "INSERT INTO guide_questions (question_id, guide_id, text, purpose, question_type, "
            "follow_up_prompts_json, linked_assumption, linked_hypothesis, position) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (r["question_id"], r["guide_id"], r["text"], r["purpose"], r["question_type"],
             dumps(r["follow_up_prompts"]), r["linked_assumption"], r["linked_hypothesis"], r["position"]))
    return rows


def _questions_for(conn, guide_id):
    rows = conn.execute(
        "SELECT question_id, text, purpose, question_type, follow_up_prompts_json, "
        "linked_assumption, linked_hypothesis, position FROM guide_questions "
        "WHERE guide_id=? ORDER BY position", (guide_id,)).fetchall()
    return [{"question_id": r[0], "text": r[1], "purpose": r[2], "question_type": r[3],
            "follow_up_prompts": loads(r[4]), "linked_assumption": r[5],
            "linked_hypothesis": r[6], "position": r[7]} for r in rows]


def _guide_row_to_dict(conn, row):
    guide_id, campaign_id, version, status, approved_by, approved_at, created_by, created_at = row
    return {"guide_id": guide_id, "campaign_id": campaign_id, "version": version,
            "workflow_status": status, "approved_by": approved_by, "approved_at": approved_at,
            "created_by": created_by, "created_at": created_at,
            "questions": _questions_for(conn, guide_id)}


def create(conn, principal, campaign_id, questions, now, guide_id=None):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    validate_questions_input(questions)
    campaign = conn.execute("SELECT 1 FROM campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
    if campaign is None:
        raise DbError(f"campaign not found: {campaign_id}")
    max_version = conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM guides WHERE campaign_id=?", (campaign_id,)).fetchone()[0]
    version = max_version + 1
    guide_id = guide_id or f"MVG-{campaign_id[4:]}-v{version}"
    if not GUIDE_ID_RE.match(guide_id):
        raise ValidationError(f"invalid guide_id: {guide_id!r}")
    with conn:
        conn.execute(
            "INSERT INTO guides (guide_id, campaign_id, version, workflow_status, created_by, created_at) "
            "VALUES (?,?,?,?,?,?)", (guide_id, campaign_id, version, "draft", principal["label"], now))
        rows = _insert_questions(conn, guide_id, questions)
        audit.record(conn, principal["label"], principal["role"], "create", "guide", guide_id, now,
                    after={"campaign_id": campaign_id, "version": version, "question_count": len(rows)})
    return get(conn, guide_id)


def get(conn, guide_id):
    row = conn.execute(
        "SELECT guide_id, campaign_id, version, workflow_status, approved_by, approved_at, "
        "created_by, created_at FROM guides WHERE guide_id=?", (guide_id,)).fetchone()
    if row is None:
        raise DbError(f"guide not found: {guide_id}")
    return _guide_row_to_dict(conn, row)


def list_versions(conn, campaign_id):
    rows = conn.execute(
        "SELECT guide_id, campaign_id, version, workflow_status, approved_by, approved_at, "
        "created_by, created_at FROM guides WHERE campaign_id=? ORDER BY version",
        (campaign_id,)).fetchall()
    return [_guide_row_to_dict(conn, r) for r in rows]


def update_draft(conn, principal, guide_id, questions, now):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    current = get(conn, guide_id)
    if current["workflow_status"] != "draft":
        raise ValidationError("approved guide versions are immutable; create a new version instead")
    validate_questions_input(questions)
    with conn:
        conn.execute("DELETE FROM guide_questions WHERE guide_id=?", (guide_id,))
        rows = _insert_questions(conn, guide_id, questions)
        audit.record(conn, principal["label"], principal["role"], "update", "guide", guide_id, now,
                    before={"question_count": len(current["questions"])},
                    after={"question_count": len(rows)})
    return get(conn, guide_id)


def approve(conn, config, principal, guide_id, now):
    require_any_role(principal, ("reviewer", "admin"))
    current = get(conn, guide_id)
    if current["workflow_status"] == "approved":
        raise ValidationError("guide version is already approved")
    self_approval = current["created_by"] == principal["label"]
    if self_approval and not config.allow_self_approval:
        raise AuthError("self-approval is not permitted (set MV_ALLOW_SELF_APPROVAL=1 to allow, audited)",
                        code="forbidden")
    with conn:
        conn.execute("UPDATE guides SET workflow_status='approved', approved_by=?, approved_at=? "
                     "WHERE guide_id=?", (principal["label"], now, guide_id))
        audit.record(conn, principal["label"], principal["role"], "approve", "guide", guide_id, now,
                    before={"workflow_status": "draft"}, after={"workflow_status": "approved"},
                    self_approval=self_approval)
    return get(conn, guide_id)


def new_version_from_approved(conn, principal, guide_id, now, questions=None):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    current = get(conn, guide_id)
    if current["workflow_status"] != "approved":
        raise ValidationError("new-version may only be created from an approved guide")
    new_questions = questions if questions is not None else [
        {k: q[k] for k in ("text", "purpose", "question_type", "follow_up_prompts",
                           "linked_assumption", "linked_hypothesis")}
        for q in current["questions"]]
    return create(conn, principal, current["campaign_id"], new_questions, now)
