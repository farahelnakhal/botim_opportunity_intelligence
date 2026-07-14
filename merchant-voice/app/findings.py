"""Approved Merchant Voice findings — created only as a side effect of
approving an evidence candidate (app/candidates.py). Still NOT authoritative
Part A evidence; nothing in this service writes there.

numerator = the candidate's included_participant_count (distinct supporting
participants); denominator = the campaign's own included_participant_count
(app/counting.py) at approval time — i.e. "3 of 8 included interviewed
merchants in MVC-TEST-001", never a bare percentage.

Findings are immutable in the sense that nobody can edit their approved
content through a normal action. The one narrow, explicitly-required
exception is `recalculate()`, called only from the Phase 2 suppression
cascade (app/suppression.py) when a participant is withdrawn/expires/is
deleted — it updates counts/strength_band/publication_status in place
(never the approved_statement, approved_by, or approved_at) and is always
audited with before/after counts.
"""

import uuid

from . import audit, campaigns, counting, participants
from .auth import require_any_role
from .db import DbError, dumps, loads
from .extraction import get_observation
from .models import FINDING_ID_RE, Phase4Error, ValidationError
from .strength import compute_strength_band

FINDING_COLUMNS = (
    "finding_id, candidate_id, campaign_id, approved_statement, segment_id, method, "
    "linked_opportunities_json, linked_assumptions_json, strength_band, limitations_json, numerator, "
    "denominator, denominator_definition, support_count, contradiction_count, workflow_status, "
    "publication_status, approved_by, approved_at, source_version_hash, superseded_by_finding_id, "
    "published_at, published_by, created_at, updated_at")


def _row_to_dict(row):
    (finding_id, candidate_id, campaign_id, approved_statement, segment_id, method, linked_opportunities,
     linked_assumptions, strength_band, limitations, numerator, denominator, denominator_definition,
     support_count, contradiction_count, workflow_status, publication_status, approved_by, approved_at,
     source_version_hash, superseded_by_finding_id, published_at, published_by, created_at, updated_at) = row
    return {
        "finding_id": finding_id, "candidate_id": candidate_id, "campaign_id": campaign_id,
        "approved_statement": approved_statement, "segment_id": segment_id, "method": method,
        "linked_opportunities": loads(linked_opportunities), "linked_assumptions": loads(linked_assumptions),
        "strength_band": strength_band, "limitations": loads(limitations), "numerator": numerator,
        "denominator": denominator, "denominator_definition": denominator_definition,
        "support_count": support_count, "contradiction_count": contradiction_count,
        "workflow_status": workflow_status, "publication_status": publication_status,
        "approved_by": approved_by, "approved_at": approved_at, "source_version_hash": source_version_hash,
        "superseded_by_finding_id": superseded_by_finding_id, "published_at": published_at,
        "published_by": published_by, "created_at": created_at, "updated_at": updated_at,
    }


def get(conn, finding_id):
    row = conn.execute(f"SELECT {FINDING_COLUMNS} FROM merchant_findings WHERE finding_id=?",
                       (finding_id,)).fetchone()
    if row is None:
        raise DbError(f"finding not found: {finding_id}")
    return _row_to_dict(row)


def list_for_campaign(conn, campaign_id, published_only=False):
    query = f"SELECT {FINDING_COLUMNS} FROM merchant_findings WHERE campaign_id=?"
    if published_only:
        query += " AND workflow_status='approved' AND publication_status='published'"
    query += " ORDER BY created_at"
    return [_row_to_dict(r) for r in conn.execute(query, (campaign_id,)).fetchall()]


def list_all(conn, published_only=False):
    query = f"SELECT {FINDING_COLUMNS} FROM merchant_findings"
    if published_only:
        query += " WHERE workflow_status='approved' AND publication_status='published'"
    query += " ORDER BY created_at"
    return [_row_to_dict(r) for r in conn.execute(query).fetchall()]


def list_for_segment(conn, segment_id, published_only=True):
    query = f"SELECT {FINDING_COLUMNS} FROM merchant_findings WHERE segment_id=?"
    if published_only:
        query += " AND workflow_status='approved' AND publication_status='published'"
    return [_row_to_dict(r) for r in conn.execute(query, (segment_id,)).fetchall()]


def list_for_opportunity(conn, opportunity_id, published_only=True):
    query = f"SELECT {FINDING_COLUMNS} FROM merchant_findings"
    if published_only:
        query += " WHERE workflow_status='approved' AND publication_status='published'"
    rows = conn.execute(query).fetchall()
    return [_row_to_dict(r) for r in rows if opportunity_id in loads(r[6])]


def list_for_assumption(conn, assumption_id, published_only=True):
    query = f"SELECT {FINDING_COLUMNS} FROM merchant_findings"
    if published_only:
        query += " WHERE workflow_status='approved' AND publication_status='published'"
    rows = conn.execute(query).fetchall()
    return [_row_to_dict(r) for r in rows if assumption_id in loads(r[7])]


def create_from_candidate(conn, principal, candidate, now):
    """Called only from candidates.approve() inside its own transaction —
    never a standalone API action."""
    campaign = campaigns.get(conn, candidate["campaign_id"])
    denom = counting.compute(conn, candidate["campaign_id"])
    strength_band, _factors = compute_strength_band(
        candidate["included_participant_count"], candidate["support_count"], candidate["contradiction_count"])

    finding_id = "MEF-" + uuid.uuid4().hex[:10]
    if not FINDING_ID_RE.match(finding_id):
        raise ValidationError(f"invalid finding_id: {finding_id!r}")

    conn.execute(
        "INSERT INTO merchant_findings (finding_id, candidate_id, campaign_id, approved_statement, segment_id, "
        "method, linked_opportunities_json, linked_assumptions_json, strength_band, limitations_json, "
        "numerator, denominator, denominator_definition, support_count, contradiction_count, workflow_status, "
        "publication_status, approved_by, approved_at, source_version_hash, superseded_by_finding_id, "
        "published_at, published_by, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (finding_id, candidate["candidate_id"], candidate["campaign_id"], candidate["statement"],
         candidate["segment_id"], campaign["method"], dumps(candidate["linked_opportunities"]),
         dumps(candidate["linked_assumptions"]), strength_band, dumps(candidate["limitations"]),
         candidate["included_participant_count"], denom["included_participant_count"],
         candidate.get("denominator_definition") or f"included participants in campaign {candidate['campaign_id']}",
         candidate["support_count"], candidate["contradiction_count"], "approved", "unpublished",
         principal["label"], now, candidate["source_version_hash"], None, None, None, now, now))
    audit.record(conn, principal["label"], principal["role"], "create", "finding", finding_id, now,
                safe_diff={"candidate_id": candidate["candidate_id"], "strength_band": strength_band,
                          "numerator": candidate["included_participant_count"],
                          "denominator": denom["included_participant_count"]})
    return get(conn, finding_id)


def _linked_direct_quote_observations(conn, candidate_id):
    rows = conn.execute(
        "SELECT observation_id FROM candidate_observations WHERE candidate_id=?", (candidate_id,)).fetchall()
    return [get_observation(conn, r[0]) for r in rows]


def publish(conn, principal, finding_id, now):
    require_any_role(principal, ("reviewer", "admin"))
    finding = get(conn, finding_id)
    if finding["workflow_status"] != "approved":
        raise Phase4Error("only an approved finding may be published", code="finding_not_publishable")
    if finding["publication_status"] == "needs_revalidation":
        raise Phase4Error("finding needs revalidation before it can be published",
                          code="finding_needs_revalidation")
    if finding["publication_status"] == "suppressed":
        raise Phase4Error("a suppressed finding may not be published", code="finding_not_publishable")

    linked_observations = _linked_direct_quote_observations(conn, finding["candidate_id"])
    for obs in linked_observations:
        if obs["workflow_status"] != "approved" or obs["suppression_status"] != "active":
            raise Phase4Error("a supporting observation is no longer approved and active — "
                              "this finding needs revalidation", code="finding_needs_revalidation")
        participant = participants.get(conn, obs["participant_id"])
        if obs["is_direct_quote"] and not participant["quote_permission"]:
            raise Phase4Error(f"quote permission is no longer valid for observation {obs['observation_id']}",
                              code="quote_permission_denied")

    with conn:
        conn.execute("UPDATE merchant_findings SET publication_status='published', published_by=?, "
                    "published_at=?, updated_at=? WHERE finding_id=?", (principal["label"], now, now, finding_id))
        audit.record(conn, principal["label"], principal["role"], "publish", "finding", finding_id, now,
                    before={"publication_status": finding["publication_status"]},
                    after={"publication_status": "published"})
    return get(conn, finding_id)


def suppress(conn, principal, finding_id, now, reason=None):
    require_any_role(principal, ("reviewer", "admin"))
    finding = get(conn, finding_id)
    with conn:
        conn.execute("UPDATE merchant_findings SET publication_status='suppressed', updated_at=? "
                    "WHERE finding_id=?", (now, finding_id))
        audit.record(conn, principal["label"], principal["role"], "suppress", "finding", finding_id, now,
                    reason=reason, before={"publication_status": finding["publication_status"]},
                    after={"publication_status": "suppressed"})
    return get(conn, finding_id)


def get_published(conn, finding_id):
    finding = get(conn, finding_id)
    if finding["workflow_status"] != "approved" or finding["publication_status"] != "published":
        raise DbError(f"finding not found: {finding_id}")
    return finding


def recalculate(conn, finding_id, now, actor_id="system", actor_role="admin"):
    """Recomputes numerator/support_count/contradiction_count/strength_band
    from the CURRENT (post-suppression) state of linked observations, and
    sets publication_status to needs_revalidation (some valid support
    remains) or suppressed (none does). Called only from the Phase 2
    suppression cascade. Never touches approved_statement/approved_by/
    approved_at — those are historical facts about what was approved and
    by whom, and stay untouched."""
    finding = get(conn, finding_id)
    rows = conn.execute("SELECT observation_id, role FROM candidate_observations WHERE candidate_id=?",
                        (finding["candidate_id"],)).fetchall()
    supporting, contradicting = [], []
    for observation_id, role in rows:
        obs = get_observation(conn, observation_id)
        if obs["workflow_status"] != "approved" or obs["suppression_status"] != "active":
            continue
        if role == "supporting":
            supporting.append(obs)
        elif role == "contradicting":
            contradicting.append(obs)

    new_numerator = len({o["participant_id"] for o in supporting})
    new_support_count = len(supporting)
    new_contradiction_count = len(contradicting)
    denom = counting.compute(conn, finding["campaign_id"])
    new_strength_band, _ = compute_strength_band(new_numerator, new_support_count, new_contradiction_count)

    new_publication_status = finding["publication_status"]
    if new_support_count == 0:
        new_publication_status = "suppressed"
    elif finding["publication_status"] == "published":
        new_publication_status = "needs_revalidation"

    before = {"numerator": finding["numerator"], "denominator": finding["denominator"],
             "support_count": finding["support_count"], "contradiction_count": finding["contradiction_count"],
             "strength_band": finding["strength_band"], "publication_status": finding["publication_status"]}
    after = {"numerator": new_numerator, "denominator": denom["included_participant_count"],
            "support_count": new_support_count, "contradiction_count": new_contradiction_count,
            "strength_band": new_strength_band, "publication_status": new_publication_status}

    with conn:
        conn.execute(
            "UPDATE merchant_findings SET numerator=?, denominator=?, support_count=?, contradiction_count=?, "
            "strength_band=?, publication_status=?, updated_at=? WHERE finding_id=?",
            (new_numerator, denom["included_participant_count"], new_support_count, new_contradiction_count,
             new_strength_band, new_publication_status, now, finding_id))
        audit.record(conn, actor_id, actor_role, "recalculate", "finding", finding_id, now,
                    before=before, after=after, safe_diff={"reason": "participant suppression cascade"})
    return get(conn, finding_id)
