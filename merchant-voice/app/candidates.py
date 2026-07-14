"""Evidence candidates: reviewer-composed summaries built from approved,
active observations. A candidate is never itself Part A evidence — only
approving one creates an immutable Merchant Voice finding (app/findings.py),
which is still not authoritative Part A evidence either.

Design choices worth knowing:
  - Every candidate is scoped to exactly ONE campaign. Every linked
    observation must share that campaign_id. Since a campaign has exactly
    one `method`, this makes "do not silently combine surveys and
    interviews" true by construction rather than by a separate runtime
    check — cross-campaign evidence synthesis is out of Phase 4 scope.
  - support_count / contradiction_count / included_participant_count are
    ALWAYS computed from the linked observations, never accepted from the
    caller — this makes "counts do not match the linked observations"
    structurally impossible rather than merely validated.
  - source_version_hash captures the (observation_id, workflow_status,
    suppression_status) tuple for every linked observation at the moment
    counts were last computed. submit()/approve() recompute it fresh and
    refuse (stale_source_version) if anything drifted — the candidate must
    be refreshed via update_draft() before it can proceed.
  - Known contradictions: any OTHER approved, active observation whose
    contradiction_target points at one of this candidate's supporting
    observations, and that isn't already linked to the candidate, must be
    either included or explicitly excluded with a reason.
"""

import hashlib
import json
import uuid

from . import audit, campaigns, findings, participants
from .auth import require_any_role
from .consent import consent_is_valid, is_retention_expired
from .db import DbError, dumps, loads
from .extraction import get_observation
from .models import (CANDIDATE_ID_RE, CANDIDATE_OBSERVATION_ROLES, CANDIDATE_TRANSITIONS,
                     CONCEPT_TEST_ALLOWED_FINDING_TYPES, REJECTION_REASONS, Phase4Error, ValidationError,
                     validate_candidate_input)

CANDIDATE_COLUMNS = (
    "candidate_id, campaign_id, finding_type, statement, segment_id, linked_opportunities_json, "
    "linked_assumptions_json, proposed_evidence_role, workflow_status, strength_band, limitations_json, "
    "denominator_definition, included_participant_count, support_count, contradiction_count, created_by, "
    "created_at, updated_at, reviewed_by, reviewed_at, rejection_reason, superseded_by_candidate_id, "
    "supersedes_candidate_id, source_version_hash, self_approval")


def _row_to_dict(row):
    (candidate_id, campaign_id, finding_type, statement, segment_id, linked_opportunities, linked_assumptions,
     proposed_evidence_role, workflow_status, strength_band, limitations, denominator_definition,
     included_participant_count, support_count, contradiction_count, created_by, created_at, updated_at,
     reviewed_by, reviewed_at, rejection_reason, superseded_by_candidate_id, supersedes_candidate_id,
     source_version_hash, self_approval) = row
    return {
        "candidate_id": candidate_id, "campaign_id": campaign_id, "finding_type": finding_type,
        "statement": statement, "segment_id": segment_id,
        "linked_opportunities": loads(linked_opportunities), "linked_assumptions": loads(linked_assumptions),
        "proposed_evidence_role": proposed_evidence_role, "workflow_status": workflow_status,
        "strength_band": strength_band, "limitations": loads(limitations),
        "denominator_definition": denominator_definition,
        "included_participant_count": included_participant_count, "support_count": support_count,
        "contradiction_count": contradiction_count, "created_by": created_by, "created_at": created_at,
        "updated_at": updated_at, "reviewed_by": reviewed_by, "reviewed_at": reviewed_at,
        "rejection_reason": rejection_reason, "superseded_by_candidate_id": superseded_by_candidate_id,
        "supersedes_candidate_id": supersedes_candidate_id, "source_version_hash": source_version_hash,
        "self_approval": bool(self_approval),
    }


def _observations_for(conn, candidate_id):
    rows = conn.execute("SELECT observation_id, role FROM candidate_observations WHERE candidate_id=?",
                        (candidate_id,)).fetchall()
    return [{"observation_id": r[0], "role": r[1]} for r in rows]


def get(conn, candidate_id):
    row = conn.execute(f"SELECT {CANDIDATE_COLUMNS} FROM evidence_candidates WHERE candidate_id=?",
                       (candidate_id,)).fetchone()
    if row is None:
        raise DbError(f"evidence candidate not found: {candidate_id}")
    candidate = _row_to_dict(row)
    candidate["observations"] = _observations_for(conn, candidate_id)
    return candidate


def list_for_campaign(conn, campaign_id):
    rows = conn.execute(f"SELECT {CANDIDATE_COLUMNS} FROM evidence_candidates WHERE campaign_id=? "
                        "ORDER BY created_at", (campaign_id,)).fetchall()
    out = []
    for r in rows:
        c = _row_to_dict(r)
        c["observations"] = _observations_for(conn, c["candidate_id"])
        out.append(c)
    return out


def list_all(conn):
    rows = conn.execute(f"SELECT {CANDIDATE_COLUMNS} FROM evidence_candidates ORDER BY created_at").fetchall()
    out = []
    for r in rows:
        c = _row_to_dict(r)
        c["observations"] = _observations_for(conn, c["candidate_id"])
        out.append(c)
    return out


def _source_version_hash(observations):
    payload = sorted((o["observation_id"], o["workflow_status"], o["suppression_status"]) for o in observations)
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _resolve_and_validate_observations(conn, campaign_id, observation_refs, contradiction_exclusion_reason):
    """Returns (resolved_observations (dict keyed by role list), segment_id,
    excluded_contradiction_count). Raises Phase4Error/ValidationError for
    any of the documented candidate-creation failure conditions."""
    resolved = {"supporting": [], "contradicting": [], "contextual": []}
    all_observations = []
    for ref in observation_refs:
        obs = get_observation(conn, ref["observation_id"])
        if obs["campaign_id"] != campaign_id:
            raise ValidationError(
                f"observation {obs['observation_id']} belongs to a different campaign; "
                "Phase 4 candidates may only reference observations from their own campaign")
        if obs["workflow_status"] != "approved":
            raise Phase4Error(f"observation {obs['observation_id']} is not approved", code="observation_not_approved")
        if obs["suppression_status"] == "suppressed":
            raise Phase4Error(f"observation {obs['observation_id']} has been suppressed", code="source_suppressed")
        resolved[ref["role"]].append(obs)
        all_observations.append(obs)

    if not resolved["supporting"]:
        raise Phase4Error("a candidate requires at least one supporting approved observation", code="missing_support")

    segment_ids = {participants.get(conn, o["participant_id"])["segment_id"] for o in resolved["supporting"]}
    segment_ids.discard(None)
    if len(segment_ids) > 1:
        raise Phase4Error("supporting observations span more than one segment; split into separate candidates "
                          "or set an explicit segment_id", code="incompatible_segment")
    inferred_segment_id = next(iter(segment_ids), None)

    # known-contradiction discovery: any OTHER approved+active observation
    # whose contradiction_target points at one of our supporting observations
    included_ids = {o["observation_id"] for o in all_observations}
    supporting_ids = [o["observation_id"] for o in resolved["supporting"]]
    known_contradictions = []
    if supporting_ids:
        placeholders = ",".join("?" for _ in supporting_ids)
        rows = conn.execute(
            f"SELECT observation_id FROM observations WHERE contradiction_target IN ({placeholders}) "
            "AND workflow_status='approved' AND suppression_status='active'", supporting_ids).fetchall()
        known_contradictions = [r[0] for r in rows if r[0] not in included_ids]
    if known_contradictions and not contradiction_exclusion_reason:
        raise Phase4Error(
            f"known approved contradictory observation(s) {known_contradictions} are not included in this "
            "candidate — provide contradiction_exclusion_reason to exclude them explicitly",
            code="contradiction_exclusion_requires_reason")

    return resolved, inferred_segment_id, len(known_contradictions)


def _validate_participants_consent(conn, observations, now):
    for obs in observations:
        participant = participants.get(conn, obs["participant_id"])
        if is_retention_expired(participant, now):
            raise Phase4Error(f"participant for observation {obs['observation_id']} has expired retention",
                              code="retention_expired")
        if not consent_is_valid(participant, now):
            raise Phase4Error(f"participant for observation {obs['observation_id']} does not have valid consent",
                              code="consent_invalid")


def _compute_counts_and_hash(resolved):
    all_observations = resolved["supporting"] + resolved["contradicting"] + resolved["contextual"]
    included_participant_count = len({o["participant_id"] for o in resolved["supporting"]})
    support_count = len(resolved["supporting"])
    contradiction_count = len(resolved["contradicting"])
    return included_participant_count, support_count, contradiction_count, _source_version_hash(all_observations)


def create(conn, principal, config, data, now):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    validate_candidate_input(data)

    campaign = campaigns.get(conn, data["campaign_id"])
    if campaign["method"] == "concept_test" and data["finding_type"] not in CONCEPT_TEST_ALLOWED_FINDING_TYPES:
        raise Phase4Error(
            f"concept_test campaigns may only produce candidates of type {CONCEPT_TEST_ALLOWED_FINDING_TYPES}",
            code="incompatible_method")

    resolved, inferred_segment_id, excluded_count = _resolve_and_validate_observations(
        conn, data["campaign_id"], data["observations"], data.get("contradiction_exclusion_reason"))
    all_observations = resolved["supporting"] + resolved["contradicting"] + resolved["contextual"]
    _validate_participants_consent(conn, all_observations, now)

    segment_id = data.get("segment_id", inferred_segment_id)
    if segment_id is not None and inferred_segment_id is not None and segment_id != inferred_segment_id:
        raise Phase4Error("segment_id does not match the supporting observations' segment", code="incompatible_segment")

    included_participant_count, support_count, contradiction_count, source_version_hash = \
        _compute_counts_and_hash(resolved)

    candidate_id = data.get("candidate_id") or ("MEC-" + uuid.uuid4().hex[:10])
    if not CANDIDATE_ID_RE.match(candidate_id):
        raise ValidationError(f"invalid candidate_id: {candidate_id!r}")
    existing = conn.execute("SELECT 1 FROM evidence_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
    if existing:
        raise ValidationError(f"candidate_id already exists: {candidate_id}")

    limitations = list(data.get("limitations", []))
    if excluded_count:
        limitations.append(f"{excluded_count} known approved contradictory observation(s) explicitly excluded")

    with conn:
        conn.execute(
            "INSERT INTO evidence_candidates (candidate_id, campaign_id, finding_type, statement, segment_id, "
            "linked_opportunities_json, linked_assumptions_json, proposed_evidence_role, workflow_status, "
            "strength_band, limitations_json, denominator_definition, included_participant_count, support_count, "
            "contradiction_count, created_by, created_at, updated_at, reviewed_by, reviewed_at, rejection_reason, "
            "superseded_by_candidate_id, supersedes_candidate_id, source_version_hash, self_approval) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (candidate_id, data["campaign_id"], data["finding_type"], data["statement"].strip(), segment_id,
             dumps(data.get("linked_opportunities", [])), dumps(data.get("linked_assumptions", [])),
             data["proposed_evidence_role"], "draft", None, dumps(limitations),
             data.get("denominator_definition"), included_participant_count, support_count, contradiction_count,
             principal["label"], now, now, None, None, None, None, data.get("supersedes_candidate_id"),
             source_version_hash, 0))
        for ref in data["observations"]:
            conn.execute("INSERT INTO candidate_observations (candidate_id, observation_id, role) VALUES (?,?,?)",
                        (candidate_id, ref["observation_id"], ref["role"]))
        audit.record(conn, principal["label"], principal["role"], "create", "evidence_candidate", candidate_id, now,
                    safe_diff={"campaign_id": data["campaign_id"], "support_count": support_count,
                              "contradiction_count": contradiction_count,
                              "included_participant_count": included_participant_count,
                              "excluded_known_contradictions": excluded_count})
    return get(conn, candidate_id)


def update_draft(conn, principal, candidate_id, data, now):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    current = get(conn, candidate_id)
    if current["workflow_status"] != "draft":
        raise Phase4Error("only a draft candidate may be edited", code="invalid_transition")

    merged = {
        "campaign_id": current["campaign_id"], "finding_type": data.get("finding_type", current["finding_type"]),
        "statement": data.get("statement", current["statement"]),
        "segment_id": data.get("segment_id", current["segment_id"]),
        "linked_opportunities": data.get("linked_opportunities", current["linked_opportunities"]),
        "linked_assumptions": data.get("linked_assumptions", current["linked_assumptions"]),
        "proposed_evidence_role": data.get("proposed_evidence_role", current["proposed_evidence_role"]),
        "observations": data.get("observations", current["observations"]),
        "candidate_id": candidate_id,
        "contradiction_exclusion_reason": data.get("contradiction_exclusion_reason"),
        "limitations": data.get("limitations", current["limitations"]),
        "denominator_definition": data.get("denominator_definition", current["denominator_definition"]),
    }
    validate_candidate_input(merged)

    campaign = campaigns.get(conn, current["campaign_id"])
    if campaign["method"] == "concept_test" and merged["finding_type"] not in CONCEPT_TEST_ALLOWED_FINDING_TYPES:
        raise Phase4Error(
            f"concept_test campaigns may only produce candidates of type {CONCEPT_TEST_ALLOWED_FINDING_TYPES}",
            code="incompatible_method")

    resolved, inferred_segment_id, excluded_count = _resolve_and_validate_observations(
        conn, current["campaign_id"], merged["observations"], merged["contradiction_exclusion_reason"])
    all_observations = resolved["supporting"] + resolved["contradicting"] + resolved["contextual"]
    _validate_participants_consent(conn, all_observations, now)

    segment_id = merged["segment_id"] if merged["segment_id"] is not None else inferred_segment_id
    if segment_id is not None and inferred_segment_id is not None and segment_id != inferred_segment_id:
        raise Phase4Error("segment_id does not match the supporting observations' segment", code="incompatible_segment")

    included_participant_count, support_count, contradiction_count, source_version_hash = \
        _compute_counts_and_hash(resolved)

    limitations = list(merged["limitations"])
    if excluded_count and not any("excluded" in l for l in limitations):
        limitations.append(f"{excluded_count} known approved contradictory observation(s) explicitly excluded")

    with conn:
        conn.execute(
            "UPDATE evidence_candidates SET finding_type=?, statement=?, segment_id=?, "
            "linked_opportunities_json=?, linked_assumptions_json=?, proposed_evidence_role=?, "
            "limitations_json=?, denominator_definition=?, included_participant_count=?, support_count=?, "
            "contradiction_count=?, source_version_hash=?, updated_at=? WHERE candidate_id=?",
            (merged["finding_type"], merged["statement"].strip(), segment_id,
             dumps(merged["linked_opportunities"]), dumps(merged["linked_assumptions"]),
             merged["proposed_evidence_role"], dumps(limitations), merged["denominator_definition"],
             included_participant_count, support_count, contradiction_count, source_version_hash, now,
             candidate_id))
        conn.execute("DELETE FROM candidate_observations WHERE candidate_id=?", (candidate_id,))
        for ref in merged["observations"]:
            conn.execute("INSERT INTO candidate_observations (candidate_id, observation_id, role) VALUES (?,?,?)",
                        (candidate_id, ref["observation_id"], ref["role"]))
        audit.record(conn, principal["label"], principal["role"], "update", "evidence_candidate", candidate_id,
                    now, safe_diff={"support_count": support_count, "contradiction_count": contradiction_count})
    return get(conn, candidate_id)


def _refresh_and_check_freshness(conn, candidate, now):
    """Recomputes counts/hash from the CURRENT state of linked observations;
    raises stale_source_version if anything drifted since the candidate was
    last saved (an observation got suppressed, superseded, or rejected)."""
    refs = candidate["observations"]
    resolved = {"supporting": [], "contradicting": [], "contextual": []}
    for ref in refs:
        obs = get_observation(conn, ref["observation_id"])
        resolved[ref["role"]].append(obs)
    all_observations = resolved["supporting"] + resolved["contradicting"] + resolved["contextual"]
    live_hash = _source_version_hash(all_observations)
    if live_hash != candidate["source_version_hash"]:
        raise Phase4Error(
            "one or more linked observations changed since this candidate was last saved "
            "(suppressed, superseded, or rejected) — refresh it with update_draft first",
            code="stale_source_version")
    if any(o["workflow_status"] != "approved" or o["suppression_status"] != "active" for o in all_observations):
        raise Phase4Error("a linked observation is no longer approved and active", code="observation_not_approved")
    return resolved


def submit(conn, principal, candidate_id, now):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    current = get(conn, candidate_id)
    if current["workflow_status"] not in CANDIDATE_TRANSITIONS or \
            "pending_review" not in CANDIDATE_TRANSITIONS.get(current["workflow_status"], set()):
        raise Phase4Error(f"cannot submit from '{current['workflow_status']}'", code="invalid_transition")
    _refresh_and_check_freshness(conn, current, now)

    with conn:
        conn.execute("UPDATE evidence_candidates SET workflow_status='pending_review', updated_at=? "
                    "WHERE candidate_id=?", (now, candidate_id))
        audit.record(conn, principal["label"], principal["role"], "submit", "evidence_candidate", candidate_id, now,
                    before={"workflow_status": "draft"}, after={"workflow_status": "pending_review"})
    return get(conn, candidate_id)


def approve(conn, config, principal, candidate_id, now, reason=None):
    """Approving a pending_review candidate creates an immutable Merchant
    Voice finding (app.findings.create_from_candidate) in the same
    transaction. If this candidate was created with supersedes_candidate_id
    set, the prior candidate (and its finding, if any) are superseded too —
    never edited, never deleted."""
    require_any_role(principal, ("reviewer", "admin"))
    current = get(conn, candidate_id)
    if current["workflow_status"] != "pending_review":
        raise Phase4Error(f"cannot approve from '{current['workflow_status']}'", code="candidate_not_reviewable")

    self_approval = current["created_by"] == principal["label"]
    if self_approval:
        if not config.allow_self_approval:
            raise Phase4Error("self-approval is not permitted (set MV_ALLOW_SELF_APPROVAL=1 to allow, audited)",
                              code="self_approval_forbidden")
        if not config.synthetic_only:
            raise Phase4Error("self-approval is only permitted in synthetic-only mode",
                              code="self_approval_forbidden")

    _refresh_and_check_freshness(conn, current, now)

    with conn:
        conn.execute("UPDATE evidence_candidates SET workflow_status='approved', reviewed_by=?, reviewed_at=?, "
                    "self_approval=?, updated_at=? WHERE candidate_id=?",
                    (principal["label"], now, int(self_approval), now, candidate_id))
        audit.record(conn, principal["label"], principal["role"], "approve", "evidence_candidate", candidate_id,
                    now, reason=reason, before={"workflow_status": "pending_review"},
                    after={"workflow_status": "approved"}, self_approval=self_approval)
        approved_candidate = get(conn, candidate_id)
        finding = findings.create_from_candidate(conn, principal, approved_candidate, now)

        if current.get("supersedes_candidate_id"):
            prior_id = current["supersedes_candidate_id"]
            prior = get(conn, prior_id)
            conn.execute("UPDATE evidence_candidates SET workflow_status='superseded', "
                        "superseded_by_candidate_id=?, updated_at=? WHERE candidate_id=?",
                        (candidate_id, now, prior_id))
            audit.record(conn, principal["label"], principal["role"], "supersede", "evidence_candidate", prior_id,
                        now, before={"workflow_status": prior["workflow_status"]},
                        after={"workflow_status": "superseded", "superseded_by_candidate_id": candidate_id})
            prior_finding = conn.execute("SELECT finding_id FROM merchant_findings WHERE candidate_id=?",
                                        (prior_id,)).fetchone()
            if prior_finding:
                conn.execute("UPDATE merchant_findings SET workflow_status='superseded', "
                            "superseded_by_finding_id=?, publication_status='unpublished', updated_at=? "
                            "WHERE finding_id=?", (finding["finding_id"], now, prior_finding[0]))
                audit.record(conn, principal["label"], principal["role"], "supersede", "finding", prior_finding[0],
                            now, before={"workflow_status": "approved"},
                            after={"workflow_status": "superseded", "superseded_by_finding_id": finding["finding_id"]})

    return get(conn, candidate_id), finding


def recalculate_for_observations(conn, observation_ids, now, actor_id="system", actor_role="admin"):
    """Called from the Phase 2 suppression cascade (app.suppression) when a
    participant becomes suppressed: recomputes counts for every APPROVED
    candidate that references any of the now-possibly-suppressed
    observations, then cascades into app.findings.recalculate for the
    candidate's finding, if it has one. Draft/pending_review candidates are
    left alone — they get fresh counts the next time they're edited or
    submitted (update_draft/submit always recompute from live state)."""
    if not observation_ids:
        return []
    placeholders = ",".join("?" for _ in observation_ids)
    candidate_ids = [r[0] for r in conn.execute(
        f"SELECT DISTINCT candidate_id FROM candidate_observations WHERE observation_id IN ({placeholders})",
        observation_ids).fetchall()]

    recalculated = []
    for candidate_id in candidate_ids:
        candidate = get(conn, candidate_id)
        if candidate["workflow_status"] != "approved":
            continue
        resolved = {"supporting": [], "contradicting": [], "contextual": []}
        for ref in candidate["observations"]:
            obs = get_observation(conn, ref["observation_id"])
            resolved[ref["role"]].append(obs)
        active = lambda o: o["workflow_status"] == "approved" and o["suppression_status"] == "active"  # noqa: E731
        supporting = [o for o in resolved["supporting"] if active(o)]
        contradicting = [o for o in resolved["contradicting"] if active(o)]
        new_included = len({o["participant_id"] for o in supporting})
        new_support = len(supporting)
        new_contradiction = len(contradicting)

        before = {"included_participant_count": candidate["included_participant_count"],
                 "support_count": candidate["support_count"], "contradiction_count": candidate["contradiction_count"]}
        after = {"included_participant_count": new_included, "support_count": new_support,
                "contradiction_count": new_contradiction}
        with conn:
            conn.execute(
                "UPDATE evidence_candidates SET included_participant_count=?, support_count=?, "
                "contradiction_count=?, updated_at=? WHERE candidate_id=?",
                (new_included, new_support, new_contradiction, now, candidate_id))
            audit.record(conn, actor_id, actor_role, "recalculate", "evidence_candidate", candidate_id, now,
                        before=before, after=after, safe_diff={"reason": "participant suppression cascade"})
        recalculated.append(candidate_id)

        finding_row = conn.execute("SELECT finding_id FROM merchant_findings WHERE candidate_id=?",
                                  (candidate_id,)).fetchone()
        if finding_row:
            findings.recalculate(conn, finding_row[0], now, actor_id=actor_id, actor_role=actor_role)

    return recalculated


def reject(conn, principal, candidate_id, reason_code, now, reason_detail=None):
    require_any_role(principal, ("reviewer", "admin"))
    if reason_code not in REJECTION_REASONS:
        raise ValidationError(f"reason must be one of {REJECTION_REASONS}")
    current = get(conn, candidate_id)
    if current["workflow_status"] != "pending_review":
        raise Phase4Error("only a pending_review candidate may be rejected", code="candidate_not_reviewable")

    with conn:
        conn.execute("UPDATE evidence_candidates SET workflow_status='rejected', rejection_reason=?, "
                    "reviewed_by=?, reviewed_at=?, updated_at=? WHERE candidate_id=?",
                    (reason_code, principal["label"], now, now, candidate_id))
        audit.record(conn, principal["label"], principal["role"], "reject", "evidence_candidate", candidate_id,
                    now, reason=reason_code, before={"workflow_status": "pending_review"},
                    after={"workflow_status": "rejected"})
    return get(conn, candidate_id)
