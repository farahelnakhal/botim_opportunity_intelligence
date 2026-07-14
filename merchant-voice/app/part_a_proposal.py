"""Part A evidence PROPOSALS — human-reviewed, NON-AUTHORITATIVE drafts that
map an approved+published Merchant Voice finding into the shape Workstream
A's Part A evidence-candidate intake expects.

This module never:
  - mints an EV ID,
  - writes into knowledge-base/customer-evidence/records/ (authoritative
    Part A evidence),
  - promotes a candidate/finding/proposal into Part A,
  - alters evidence confidence, scores, assumptions, impact state, or
    monitoring history.

A proposal may only be generated from a finding that is currently approved,
published, consent-valid, retention-valid, not suppressed, and not
needs_revalidation (`_eligible_finding`). Its `suggested_strength` is
explicitly non-authoritative — "Workstream A decides final strength" is
carried in the payload itself, and the Merchant Voice strength band is never
silently relabelled as final Part A evidence strength.

workflow_status (draft/pending_review/approved/rejected/superseded) and
publication_status (unpublished/export_approved/needs_revalidation/
suppressed/exported_synthetic) are separate concepts — see app/db.py's
Phase 5 docstring. Approved proposals are immutable; any later source
change requires a new proposal version (create() again) or a superseding
proposal (supersedes_proposal_id), never an edit of the approved one.
"""

import hashlib
import json
import uuid
from pathlib import Path

from . import audit, campaigns, candidates, findings, participants
from .auth import require_any_role
from .consent import consent_is_valid, is_retention_expired
from .db import DbError, dumps, loads
from .extraction import get_observation
from .models import PROPOSAL_EDITABLE_FIELDS, PROPOSAL_ID_RE, REJECTION_REASONS, Phase5Error, ValidationError

PROPOSAL_COLUMNS = (
    "proposal_id, finding_id, campaign_id, source_finding_version_hash, payload_json, rendered_markdown, "
    "workflow_status, publication_status, reviewer, reviewed_at, rejection_reason, created_by, created_at, "
    "updated_at, export_status, export_path, exported_at, superseded_by_proposal_id, synthetic_only, "
    "needs_revalidation_reason")


def _row_to_dict(row):
    (proposal_id, finding_id, campaign_id, source_finding_version_hash, payload, rendered_markdown,
     workflow_status, publication_status, reviewer, reviewed_at, rejection_reason, created_by, created_at,
     updated_at, export_status, export_path, exported_at, superseded_by_proposal_id, synthetic_only,
     needs_revalidation_reason) = row
    return {
        "proposal_id": proposal_id, "finding_id": finding_id, "campaign_id": campaign_id,
        "source_finding_version_hash": source_finding_version_hash, "payload": loads(payload),
        "rendered_markdown": rendered_markdown, "workflow_status": workflow_status,
        "publication_status": publication_status, "reviewer": reviewer, "reviewed_at": reviewed_at,
        "rejection_reason": rejection_reason, "created_by": created_by, "created_at": created_at,
        "updated_at": updated_at, "export_status": export_status, "export_path": export_path,
        "exported_at": exported_at, "superseded_by_proposal_id": superseded_by_proposal_id,
        "synthetic_only": bool(synthetic_only), "needs_revalidation_reason": needs_revalidation_reason,
    }


def get(conn, proposal_id):
    row = conn.execute(f"SELECT {PROPOSAL_COLUMNS} FROM part_a_proposals WHERE proposal_id=?",
                       (proposal_id,)).fetchone()
    if row is None:
        raise DbError(f"proposal not found: {proposal_id}")
    return _row_to_dict(row)


def list_all(conn):
    rows = conn.execute(f"SELECT {PROPOSAL_COLUMNS} FROM part_a_proposals ORDER BY created_at").fetchall()
    return [_row_to_dict(r) for r in rows]


def list_for_finding(conn, finding_id):
    rows = conn.execute(f"SELECT {PROPOSAL_COLUMNS} FROM part_a_proposals WHERE finding_id=? "
                        "ORDER BY created_at", (finding_id,)).fetchall()
    return [_row_to_dict(r) for r in rows]


# --- eligibility / freshness -------------------------------------------------

def _eligible_finding(conn, finding_id):
    finding = findings.get(conn, finding_id)
    if finding["workflow_status"] != "approved":
        raise Phase5Error("a proposal may only be generated from an approved finding",
                          code="finding_not_publishable")
    if finding["publication_status"] == "needs_revalidation":
        raise Phase5Error("finding needs revalidation before a proposal can be generated",
                          code="finding_needs_revalidation")
    if finding["publication_status"] != "published":
        raise Phase5Error("a proposal may only be generated from a published finding",
                          code="finding_not_publishable")
    return finding


def _finding_version_fingerprint(finding):
    """A fresh fingerprint of the finding's CURRENT state — distinct from
    merchant_findings.source_version_hash (which is fixed at finding-
    creation time and never bumped by findings.recalculate()). Recomputed
    on every proposal freshness check so drift from a recalculate() is
    always detected, even though the finding's own stored hash didn't
    change."""
    payload = (finding["finding_id"], finding["workflow_status"], finding["publication_status"],
              finding["numerator"], finding["denominator"], finding["support_count"],
              finding["contradiction_count"], finding["strength_band"])
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _refresh_and_check_freshness(conn, proposal):
    """Raises proposal_stale if the underlying finding has drifted since
    this proposal was generated/last saved, or source_version_changed if
    the cascade has already flagged this proposal needs_revalidation/
    suppressed (a more specific, already-recorded reason)."""
    if proposal["publication_status"] in ("needs_revalidation", "suppressed"):
        raise Phase5Error(
            proposal["needs_revalidation_reason"] or "this proposal's source finding has changed",
            code="source_version_changed")
    finding = findings.get(conn, proposal["finding_id"])
    live_hash = _finding_version_fingerprint(finding)
    if live_hash != proposal["source_finding_version_hash"]:
        raise Phase5Error(
            "the underlying finding has changed since this proposal was generated — "
            "regenerate the proposal to continue", code="proposal_stale")
    return finding


# --- quote handling / provenance ---------------------------------------------

def _quote_eligible(conn, obs, now):
    if not obs["is_direct_quote"]:
        return False
    if obs["workflow_status"] != "approved" or obs["suppression_status"] != "active":
        return False
    participant = participants.get(conn, obs["participant_id"])
    if not participant["quote_permission"]:
        return False
    if not consent_is_valid(participant, now):
        return False
    if is_retention_expired(participant, now):
        return False
    return True


def _check_live_quotes_still_eligible(conn, proposal, now):
    """Export-time-only check: re-verifies every quote baked into this
    proposal's payload at generate() time is STILL eligible right now —
    quote_permission, consent, retention, and active/non-suppressed status
    can all change without touching the finding's counts/strength_band, so
    this must never be inferred from _refresh_and_check_freshness's
    fingerprint (numerator/denominator/support_count/contradiction_count/
    strength_band/workflow_status/publication_status). A revoked quote is
    never silently exported — export is blocked outright rather than
    silently re-rendered without the quote."""
    for quote in proposal["payload"].get("quotes", []):
        obs = get_observation(conn, quote["observation_id"])
        if not _quote_eligible(conn, obs, now):
            raise Phase5Error(
                f"quote permission is no longer valid for observation {quote['observation_id']} — "
                "export refused rather than silently dropping the quote", code="quote_permission_denied")


def _observation_provenance(conn, ref):
    obs = get_observation(conn, ref["observation_id"])
    answer_row = conn.execute("SELECT question_id FROM raw_answers WHERE answer_id=?",
                              (obs["source_answer_id"],)).fetchone()
    return {
        "observation_id": obs["observation_id"], "role": ref["role"],
        "observation_type": obs["observation_type"], "response_id": obs["response_id"],
        "participant_id": obs["participant_id"],  # pseudonymous — never an identity.db value
        "source_answer_id": obs["source_answer_id"], "question_id": answer_row[0] if answer_row else None,
        "extraction_run_id": obs["extraction_run_id"],
    }, obs


def _build_payload(conn, finding, candidate, campaign, now):
    obs_refs = candidate["observations"]
    provenance_observations = []
    quotes = []
    omitted_quote_count = 0
    contradictory_evidence = []
    guide_ids = set()

    for ref in obs_refs:
        entry, obs = _observation_provenance(conn, ref)
        response_row = conn.execute("SELECT guide_id FROM responses WHERE response_id=?",
                                    (obs["response_id"],)).fetchone()
        if response_row:
            guide_ids.add(response_row[0])
        provenance_observations.append(entry)

        if ref["role"] == "contradicting":
            contradictory_evidence.append({
                "observation_id": obs["observation_id"], "observation_type": obs["observation_type"],
            })

        if obs["is_direct_quote"]:
            if _quote_eligible(conn, obs, now):
                quotes.append({"observation_id": obs["observation_id"], "text": obs["normalized_statement"],
                              "role": ref["role"]})
            else:
                omitted_quote_count += 1

    limitations = list(finding["limitations"])
    if omitted_quote_count:
        limitations.append(
            f"{omitted_quote_count} supporting quote(s) withheld — quote permission, consent, or "
            "retention is not currently valid for the participant(s) involved")

    review_history = [
        {"action": e["action"], "actor_role": e["actor_role"], "timestamp": e["timestamp"]}
        for e in audit.list_for_object(conn, "finding", finding["finding_id"])
    ]

    payload = {
        "proposed_title": f"{finding['method'].replace('_', ' ').title()} finding — {finding['campaign_id']}",
        "proposed_evidence_statement": finding["approved_statement"],
        "editor_notes": None,
        "source_type": "merchant_voice_research",
        "campaign_method": finding["method"],
        "segment_id": finding["segment_id"],
        "linked_opportunities": finding["linked_opportunities"],
        "linked_assumptions": finding["linked_assumptions"],
        "suggested_strength": finding["strength_band"],
        "reviewer_required": True,
        "strength_decision_note": (
            "This is a non-authoritative suggestion derived from the Merchant Voice strength band. "
            "Workstream A decides final Part A evidence strength."),
        "support_count": finding["support_count"],
        "contradiction_count": finding["contradiction_count"],
        "numerator": finding["numerator"],
        "denominator": finding["denominator"],
        "denominator_definition": finding["denominator_definition"],
        "limitations": limitations,
        "provenance": {
            "finding_id": finding["finding_id"], "candidate_id": candidate["candidate_id"],
            "campaign_id": finding["campaign_id"], "guide_ids": sorted(guide_ids),
            "observations": provenance_observations,
        },
        "quotes": quotes,
        "contradictory_evidence": contradictory_evidence,
        "review_history": review_history,
        "classification": "synthetic" if campaign["data_classification"] == "synthetic" else "live",
        "authoritative_ev_id": None,
    }
    return payload


def _render_markdown(finding, payload):
    lines = [
        "**SYNTHETIC DATA — DEMO ONLY. NOT AUTHORITATIVE PART A EVIDENCE. REQUIRES WORKSTREAM A REVIEW.**"
        if payload["classification"] == "synthetic" else
        "**NOT AUTHORITATIVE PART A EVIDENCE — REQUIRES WORKSTREAM A REVIEW.**",
        "",
        f"### Proposed Part A evidence — {payload['proposed_title']}",
        "",
        payload["proposed_evidence_statement"],
        "",
        f"- Method: {payload['campaign_method']}",
        f"- Segment: {payload['segment_id'] or 'unspecified'}",
        f"- {payload['numerator']} of {payload['denominator']} {payload['denominator_definition']}",
        f"- Support: {payload['support_count']}, Contradiction: {payload['contradiction_count']}",
        f"- Suggested strength (non-authoritative): {payload['suggested_strength']}",
        "  Workstream A decides final evidence strength.",
    ]
    if payload["limitations"]:
        lines.append("- Limitations: " + "; ".join(payload["limitations"]))
    if payload["contradictory_evidence"]:
        lines.append(f"- {len(payload['contradictory_evidence'])} contradicting observation(s) preserved")
    if payload["quotes"]:
        lines.append("")
        lines.append("Quotes (permission-verified):")
        for q in payload["quotes"]:
            lines.append(f'> "{q["text"]}"')
    lines.append("")
    lines.append(f"No authoritative EV ID has been assigned (authoritative_ev_id: "
                 f"{payload['authoritative_ev_id']}).")
    return "\n".join(lines)


# --- creation / editing -------------------------------------------------------

def generate(conn, principal, finding_id, now, reason=None):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    finding = _eligible_finding(conn, finding_id)
    candidate = candidates.get(conn, finding["candidate_id"])
    campaign = campaigns.get(conn, finding["campaign_id"])

    payload = _build_payload(conn, finding, candidate, campaign, now)
    rendered_markdown = _render_markdown(finding, payload)
    source_hash = _finding_version_fingerprint(finding)

    proposal_id = "MEP-" + uuid.uuid4().hex[:10]
    if not PROPOSAL_ID_RE.match(proposal_id):
        raise ValidationError(f"invalid proposal_id: {proposal_id!r}")

    with conn:
        conn.execute(
            "INSERT INTO part_a_proposals (proposal_id, finding_id, campaign_id, "
            "source_finding_version_hash, payload_json, rendered_markdown, workflow_status, "
            "publication_status, reviewer, reviewed_at, rejection_reason, created_by, created_at, "
            "updated_at, export_status, export_path, exported_at, superseded_by_proposal_id, "
            "synthetic_only, needs_revalidation_reason) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (proposal_id, finding_id, finding["campaign_id"], source_hash, dumps(payload), rendered_markdown,
             "draft", "unpublished", None, None, None, principal["label"], now, now, "not_exported",
             None, None, None, int(payload["classification"] == "synthetic"), None))
        audit.record(conn, principal["label"], principal["role"], "generate", "part_a_proposal", proposal_id,
                    now, reason=reason,
                    safe_diff={"finding_id": finding_id, "suggested_strength": payload["suggested_strength"]})
    return get(conn, proposal_id)


def update_draft(conn, principal, proposal_id, data, now):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    current = get(conn, proposal_id)
    if current["workflow_status"] != "draft":
        raise Phase5Error("only a draft proposal may be edited", code="proposal_not_reviewable")
    unknown = [f for f in data if f not in PROPOSAL_EDITABLE_FIELDS]
    if unknown:
        raise ValidationError(f"unknown or non-editable field(s): {unknown}")

    payload = dict(current["payload"])
    payload.update({k: v for k, v in data.items() if k in PROPOSAL_EDITABLE_FIELDS})
    finding = findings.get(conn, current["finding_id"])
    rendered_markdown = _render_markdown(finding, payload)

    with conn:
        conn.execute("UPDATE part_a_proposals SET payload_json=?, rendered_markdown=?, updated_at=? "
                    "WHERE proposal_id=?", (dumps(payload), rendered_markdown, now, proposal_id))
        audit.record(conn, principal["label"], principal["role"], "edit", "part_a_proposal", proposal_id, now,
                    safe_diff={"fields_changed": sorted(data.keys())})
    return get(conn, proposal_id)


# --- workflow ------------------------------------------------------------------

def submit(conn, principal, proposal_id, now):
    require_any_role(principal, ("researcher", "reviewer", "admin"))
    current = get(conn, proposal_id)
    if current["workflow_status"] != "draft":
        raise Phase5Error(f"cannot submit from '{current['workflow_status']}'", code="proposal_not_reviewable")
    _refresh_and_check_freshness(conn, current)

    with conn:
        conn.execute("UPDATE part_a_proposals SET workflow_status='pending_review', updated_at=? "
                    "WHERE proposal_id=?", (now, proposal_id))
        audit.record(conn, principal["label"], principal["role"], "submit", "part_a_proposal", proposal_id, now,
                    before={"workflow_status": "draft"}, after={"workflow_status": "pending_review"})
    return get(conn, proposal_id)


def approve(conn, config, principal, proposal_id, now, reason=None):
    require_any_role(principal, ("reviewer", "admin"))
    current = get(conn, proposal_id)
    if current["workflow_status"] != "pending_review":
        raise Phase5Error(f"cannot approve from '{current['workflow_status']}'",
                          code="proposal_not_reviewable")

    self_approval = current["created_by"] == principal["label"]
    if self_approval:
        if not config.allow_self_approval:
            raise Phase5Error("self-approval is not permitted (set MV_ALLOW_SELF_APPROVAL=1 to allow, audited)",
                              code="self_approval_forbidden")
        if not config.synthetic_only:
            raise Phase5Error("self-approval is only permitted in synthetic-only mode",
                              code="self_approval_forbidden")
        if not reason:
            raise Phase5Error("a reason is required to override self-approval",
                              code="self_approval_forbidden")

    _refresh_and_check_freshness(conn, current)

    with conn:
        conn.execute("UPDATE part_a_proposals SET workflow_status='approved', reviewer=?, reviewed_at=?, "
                    "updated_at=? WHERE proposal_id=?", (principal["label"], now, now, proposal_id))
        audit.record(conn, principal["label"], principal["role"], "approve", "part_a_proposal", proposal_id,
                    now, reason=reason, before={"workflow_status": "pending_review"},
                    after={"workflow_status": "approved"}, self_approval=self_approval)
    return get(conn, proposal_id)


def reject(conn, principal, proposal_id, reason_code, now, reason_detail=None):
    require_any_role(principal, ("reviewer", "admin"))
    if reason_code not in REJECTION_REASONS:
        raise ValidationError(f"reason must be one of {REJECTION_REASONS}")
    current = get(conn, proposal_id)
    if current["workflow_status"] != "pending_review":
        raise Phase5Error("only a pending_review proposal may be rejected", code="proposal_not_reviewable")

    with conn:
        conn.execute("UPDATE part_a_proposals SET workflow_status='rejected', rejection_reason=?, "
                    "reviewer=?, reviewed_at=?, updated_at=? WHERE proposal_id=?",
                    (reason_code, principal["label"], now, now, proposal_id))
        audit.record(conn, principal["label"], principal["role"], "reject", "part_a_proposal", proposal_id, now,
                    reason=reason_code, before={"workflow_status": "pending_review"},
                    after={"workflow_status": "rejected"})
    return get(conn, proposal_id)


def approve_export(conn, config, principal, proposal_id, now, reason=None):
    """Approves this proposal for SYNTHETIC-ONLY export — a distinct action
    from content approval. Never itself performs the export (see export())."""
    require_any_role(principal, ("reviewer", "admin"))
    current = get(conn, proposal_id)
    if current["workflow_status"] != "approved":
        raise Phase5Error("only an approved proposal may be approved for export",
                          code="proposal_not_exportable")

    self_approval = current["created_by"] == principal["label"]
    if self_approval:
        if not config.allow_self_approval:
            raise Phase5Error("self-approval is not permitted (set MV_ALLOW_SELF_APPROVAL=1 to allow, audited)",
                              code="self_approval_forbidden")
        if not config.synthetic_only:
            raise Phase5Error("self-approval is only permitted in synthetic-only mode",
                              code="self_approval_forbidden")
        if not reason:
            raise Phase5Error("a reason is required to override self-approval",
                              code="self_approval_forbidden")

    _refresh_and_check_freshness(conn, current)

    with conn:
        conn.execute("UPDATE part_a_proposals SET publication_status='export_approved', updated_at=? "
                    "WHERE proposal_id=?", (now, proposal_id))
        audit.record(conn, principal["label"], principal["role"], "approve_export", "part_a_proposal",
                    proposal_id, now, reason=reason, before={"publication_status": current["publication_status"]},
                    after={"publication_status": "export_approved"}, self_approval=self_approval)
    return get(conn, proposal_id)


# --- invalidation (withdrawal / retention / finding-revalidation cascade) -----

def invalidate_for_finding(conn, finding_id, now, actor_id="system", actor_role="admin"):
    """Called from the Phase 2 suppression cascade whenever the finding's
    counts have been recalculated (a supporting participant became
    withdrawn/expired/deleted). Never silently keeps a stale proposal
    preview active: marks every non-terminal proposal for this finding
    needs_revalidation (if the finding still has some support) or
    suppressed (if it doesn't), blocks approval/export, and flags any
    already-exported synthetic candidate as based on a superseded version.
    The old proposal is preserved — never edited beyond these two fields
    plus the reason — so audit history stays intact."""
    finding = findings.get(conn, finding_id)
    new_publication_status = "suppressed" if finding["support_count"] == 0 else "needs_revalidation"
    reason = (f"source finding {finding_id} was recalculated (support_count={finding['support_count']}, "
             f"publication_status={finding['publication_status']})")

    invalidated = []
    for proposal in list_for_finding(conn, finding_id):
        if proposal["workflow_status"] in ("rejected", "superseded"):
            continue
        if proposal["publication_status"] in ("needs_revalidation", "suppressed"):
            continue  # already flagged; do not re-audit repeatedly
        before = {"publication_status": proposal["publication_status"], "export_status": proposal["export_status"]}
        export_status = proposal["export_status"]
        if proposal["export_status"] == "exported":
            export_status = "exported"  # kept, but now understood to be based on a superseded version
        with conn:
            conn.execute(
                "UPDATE part_a_proposals SET publication_status=?, needs_revalidation_reason=?, updated_at=? "
                "WHERE proposal_id=?", (new_publication_status, reason, now, proposal["proposal_id"]))
            audit.record(conn, actor_id, actor_role, "invalidate", "part_a_proposal", proposal["proposal_id"],
                        now, before=before,
                        after={"publication_status": new_publication_status, "export_status": export_status},
                        safe_diff={"reason": "source finding recalculated", "finding_id": finding_id,
                                  "previously_exported": proposal["export_status"] == "exported"})
        invalidated.append(proposal["proposal_id"])
    return invalidated


# --- synthetic-only export -----------------------------------------------------

NON_SYNTHETIC_EXPORT_PREREQUISITES = (
    "privacy approval", "redaction verification", "quote-permission verification",
    "human reviewer approval", "Workstream A approval", "approved production deployment",
)

EXPORT_DIR_RELATIVE = ("knowledge-base", "customer-evidence", "merchant-voice-candidates")

SYNTHETIC_BANNER = (
    "SYNTHETIC DATA — DEMO ONLY\n"
    "NOT AUTHORITATIVE PART A EVIDENCE\n"
    "REQUIRES WORKSTREAM A REVIEW\n"
)


def export(conn, config, principal, proposal_id, now, repo_root):
    """Writes a synthetic-only demo file into
    knowledge-base/customer-evidence/merchant-voice-candidates/. Never
    mints an EV ID, never writes to
    knowledge-base/customer-evidence/records/, never accepts a caller-
    supplied path or filename (always server-generated from proposal_id).
    Every quote baked into the payload is re-checked live immediately
    before the write (_check_live_quotes_still_eligible) — quote
    permission/consent/retention can change without touching the finding's
    counts or strength_band, so this is never inferred from the freshness
    fingerprint alone."""
    require_any_role(principal, ("reviewer", "admin"))
    current = get(conn, proposal_id)
    campaign = campaigns.get(conn, current["campaign_id"])

    if campaign["data_classification"] != "synthetic":
        raise Phase5Error(
            "export is not permitted for non-synthetic campaign data; prerequisites for a future "
            "production export: " + ", ".join(NON_SYNTHETIC_EXPORT_PREREQUISITES),
            code="non_synthetic_export_forbidden")
    if current["workflow_status"] != "approved":
        raise Phase5Error("only an approved proposal may be exported", code="proposal_not_exportable")
    if current["publication_status"] != "export_approved":
        raise Phase5Error("export requires publication_status='export_approved' "
                          "(call approve-export first)", code="proposal_not_exportable")

    _refresh_and_check_freshness(conn, current)
    _check_live_quotes_still_eligible(conn, current, now)

    export_dir = repo_root.joinpath(*EXPORT_DIR_RELATIVE)
    export_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{proposal_id}.md"  # server-generated from the proposal ID only
    export_path = export_dir / filename
    resolved = export_path.resolve()
    if resolved.parent != export_dir.resolve():
        # defense in depth: proposal_id is regex-validated at creation and
        # can never contain path separators, so this should be unreachable
        raise Phase5Error("computed export path escaped the approved intake folder",
                          code="export_path_invalid")

    content = SYNTHETIC_BANNER + "\n" + current["rendered_markdown"] + "\n"
    relative_path = str(Path(*EXPORT_DIR_RELATIVE) / filename)

    try:
        export_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        with conn:
            audit.record(conn, principal["label"], principal["role"], "export_blocked", "part_a_proposal",
                        proposal_id, now, safe_diff={"error": "write_failed"})
        raise Phase5Error(f"export failed: {exc}", code="proposal_not_exportable")

    with conn:
        conn.execute(
            "UPDATE part_a_proposals SET publication_status='exported_synthetic', export_status='exported', "
            "export_path=?, exported_at=?, updated_at=? WHERE proposal_id=?",
            (relative_path, now, now, proposal_id))
        audit.record(conn, principal["label"], principal["role"], "export_completed", "part_a_proposal",
                    proposal_id, now, before={"export_status": current["export_status"]},
                    after={"export_status": "exported"}, safe_diff={"export_path": relative_path})
    return get(conn, proposal_id)
