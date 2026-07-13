"""Denominator foundation — reliable, unambiguous counts for a campaign.

This is deliberately NOT a "sample_size" number: campaign analysis (Phase
3/4) needs several distinct denominators depending on the claim being made,
and conflating them produces exactly the kind of unsupported "n of m"
claim this project's evidence-strength rules forbid elsewhere. Each count
below has one fixed, unambiguous definition:

  invited_count              — every participant record ever created for
                                this campaign, regardless of current status
  enrolled_count              — participants who have submitted at least one
                                response (workflow_status in
                                {enrolled, completed}), regardless of
                                current suppression
  submitted_response_count    — total response rows for the campaign, all
                                processing/duplicate statuses included
  valid_participant_count     — participants currently not suppressed and
                                with consent_status == "granted"
  included_participant_count  — valid participants who have also enrolled
                                (submitted >=1 response) — the set later
                                phases may draw findings from
  excluded_or_suppressed_count — invited_count - included_participant_count
"""


def compute(conn, campaign_id):
    invited_count = conn.execute(
        "SELECT COUNT(*) FROM participants WHERE campaign_id=?", (campaign_id,)).fetchone()[0]

    enrolled_count = conn.execute(
        "SELECT COUNT(*) FROM participants WHERE campaign_id=? AND workflow_status IN ('enrolled', 'completed')",
        (campaign_id,)).fetchone()[0]

    submitted_response_count = conn.execute(
        "SELECT COUNT(*) FROM responses WHERE campaign_id=?", (campaign_id,)).fetchone()[0]

    valid_participant_count = conn.execute(
        "SELECT COUNT(*) FROM participants WHERE campaign_id=? AND suppression_status != 'suppressed' "
        "AND consent_status = 'granted'", (campaign_id,)).fetchone()[0]

    included_participant_count = conn.execute(
        "SELECT COUNT(*) FROM participants WHERE campaign_id=? AND suppression_status != 'suppressed' "
        "AND consent_status = 'granted' AND workflow_status IN ('enrolled', 'completed')",
        (campaign_id,)).fetchone()[0]

    excluded_or_suppressed_count = invited_count - included_participant_count

    return {
        "campaign_id": campaign_id,
        "invited_count": invited_count,
        "enrolled_count": enrolled_count,
        "submitted_response_count": submitted_response_count,
        "valid_participant_count": valid_participant_count,
        "included_participant_count": included_participant_count,
        "excluded_or_suppressed_count": excluded_or_suppressed_count,
    }
