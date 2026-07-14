"""Deterministic, read-only campaign-level analysis over reviewed, active
data only (approved observations, not suppressed). Every aggregate carries
its own numerator/denominator/denominator_definition/campaign/method/
segment/limitations — never a bare percentage, never pooled across
segments.

Segment separation: results are always grouped by segment_id (never
silently pooled) — a campaign whose participants span multiple segments
returns one sub-result per segment with an explicit note that they were
not combined. Method separation is structural: analysis is scoped to one
campaign, and a campaign has exactly one method.

`include_detail=False` (used for the viewer role) strips sample statement
text, leaving only counts/denominators/labels — no reviewed-but-still
research content reaches viewer-level API responses.
"""

from collections import defaultdict

from . import campaigns, counting, findings, participants
from .extraction import list_observations_for_campaign

CATEGORY_TYPE_MAP = {
    "recurring_pains": "pain",
    "recurring_behaviors": "behaviour",
    "common_workarounds": "workaround",
    "objections": "objection",
    "switching_barriers": "switching_barrier",
    "wtp_signals": "willingness_to_pay_signal",
    "contradictions": "contradiction",
    "adoption_conditions": "adoption_condition",
    "rejection_conditions": "rejection_condition",
}

GROUPING_NOTE = "Results are grouped by segment; segments are never pooled together."


def compute_campaign_analysis(conn, campaign_id, include_detail=True):
    campaign = campaigns.get(conn, campaign_id)
    base = counting.compute(conn, campaign_id)
    denominator_definition = f"included participants in campaign {campaign_id}"

    all_observations = list_observations_for_campaign(conn, campaign_id)
    approved_observation_count = sum(1 for o in all_observations if o["workflow_status"] == "approved")
    rejected_observation_count = sum(1 for o in all_observations if o["workflow_status"] == "rejected")
    pending_observation_count = sum(1 for o in all_observations if o["workflow_status"] == "pending_review")

    active_approved = [o for o in all_observations
                      if o["workflow_status"] == "approved" and o["suppression_status"] == "active"]

    by_segment = defaultdict(lambda: defaultdict(list))
    for obs in active_approved:
        participant = participants.get(conn, obs["participant_id"])
        by_segment[participant["segment_id"]][obs["observation_type"]].append(obs)

    segment_results = {}
    for segment_id, by_type in by_segment.items():
        category_aggregates = {}
        for category_name, obs_type in CATEGORY_TYPE_MAP.items():
            items = by_type.get(obs_type, [])
            distinct_participants = {o["participant_id"] for o in items}
            entry = {
                "numerator": len(distinct_participants), "denominator": base["included_participant_count"],
                "denominator_definition": denominator_definition, "observation_count": len(items),
                "campaign_id": campaign_id, "method": campaign["method"], "segment_id": segment_id,
                "contradiction_count": len(by_type.get("contradiction", [])) if obs_type != "contradiction" else 0,
            }
            if include_detail:
                entry["sample_statements"] = [o["normalized_statement"] for o in items[:5]]
            category_aggregates[category_name] = entry
        segment_results[segment_id or "unspecified"] = category_aggregates

    unanswered = [o for o in active_approved if o["observation_type"] == "follow_up_question"]
    unanswered_block = {"count": len(unanswered), "campaign_id": campaign_id}
    if include_detail:
        unanswered_block["questions"] = [o["follow_up_question"] or o["normalized_statement"] for o in unanswered]

    findings_by_band = defaultdict(int)
    for f in findings.list_for_campaign(conn, campaign_id):
        if f["workflow_status"] == "approved":
            findings_by_band[f["strength_band"]] += 1

    return {
        "campaign_id": campaign_id, "method": campaign["method"],
        "invited_count": base["invited_count"], "enrolled_count": base["enrolled_count"],
        "submitted_response_count": base["submitted_response_count"],
        "valid_participant_count": base["valid_participant_count"],
        "included_participant_count": base["included_participant_count"],
        "excluded_or_suppressed_count": base["excluded_or_suppressed_count"],
        "approved_observation_count": approved_observation_count,
        "rejected_observation_count": rejected_observation_count,
        "pending_observation_count": pending_observation_count,
        "segments": segment_results,
        "grouping_note": GROUPING_NOTE,
        "unanswered_follow_up_questions": unanswered_block,
        "findings_by_strength_band": dict(findings_by_band),
        "denominator_definition": denominator_definition,
    }
