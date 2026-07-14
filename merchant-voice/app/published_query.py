"""Read-only Merchant Voice query layer — the single seam the Product
Discovery Copilot is allowed to call into.

Every function here takes only the mv.db connection — this module NEVER
opens identity.db and never imports app.identity. It exposes only content
behind APPROVED, PUBLISHED, non-superseded findings; it never returns
external merchant references, contact information, raw transcripts,
unredacted answers, unreviewed/rejected/suppressed observations,
needs_revalidation findings, draft proposals, or review notes intended only
for researchers. It performs no writes.
"""

from . import campaigns, candidates as candidates_mod, counting, findings
from .consent import consent_is_valid, is_retention_expired
from .db import DbError
from .extraction import get_observation
from .participants import get as get_participant


def _finding_type(conn, finding):
    candidate = candidates_mod.get(conn, finding["candidate_id"])
    return candidate["finding_type"]


def _finding_summary(conn, finding, finding_type=None):
    return {
        "finding_id": finding["finding_id"], "approved_statement": finding["approved_statement"],
        "finding_type": finding_type or _finding_type(conn, finding),
        "campaign_id": finding["campaign_id"], "method": finding["method"],
        "segment_id": finding["segment_id"], "strength_band": finding["strength_band"],
        "support_count": finding["support_count"], "contradiction_count": finding["contradiction_count"],
        "numerator": finding["numerator"], "denominator": finding["denominator"],
        "denominator_definition": finding["denominator_definition"],
        "limitations": finding["limitations"], "linked_opportunities": finding["linked_opportunities"],
        "linked_assumptions": finding["linked_assumptions"],
    }


def list_campaigns(conn):
    """Only campaigns that currently have at least one published finding."""
    out = []
    for campaign in campaigns.list_all(conn):
        published = findings.list_for_campaign(conn, campaign["campaign_id"], published_only=True)
        if not published:
            continue
        out.append({"campaign_id": campaign["campaign_id"], "title": campaign["title"],
                    "method": campaign["method"], "published_finding_count": len(published)})
    return out


def get_campaign(conn, campaign_id):
    campaign = campaigns.get(conn, campaign_id)
    published = findings.list_for_campaign(conn, campaign_id, published_only=True)
    if not published:
        raise DbError(f"campaign not found: {campaign_id}")
    return {"campaign_id": campaign["campaign_id"], "title": campaign["title"], "method": campaign["method"],
           "objective": campaign["objective"], "published_finding_count": len(published)}


def get_campaign_summary(conn, campaign_id):
    campaign = campaigns.get(conn, campaign_id)
    denom = counting.compute(conn, campaign_id)
    published = findings.list_for_campaign(conn, campaign_id, published_only=True)
    by_type = {}
    for f in published:
        finding_type = _finding_type(conn, f)
        by_type.setdefault(finding_type, []).append(_finding_summary(conn, f, finding_type))
    return {
        "campaign_id": campaign_id, "method": campaign["method"],
        "included_participant_count": denom["included_participant_count"],
        "published_finding_count": len(published),
        "findings_by_type": by_type,
        "limitations": sorted({l for f in published for l in f["limitations"]}),
        "grouping_note": "Findings are grouped by segment and method; never pooled across them.",
    }


def list_findings(conn, campaign_id=None, segment_id=None, opportunity_id=None, assumption_id=None,
                  finding_type=None):
    if campaign_id is not None:
        published = findings.list_for_campaign(conn, campaign_id, published_only=True)
    elif segment_id is not None:
        published = findings.list_for_segment(conn, segment_id, published_only=True)
    elif opportunity_id is not None:
        published = findings.list_for_opportunity(conn, opportunity_id, published_only=True)
    elif assumption_id is not None:
        published = findings.list_for_assumption(conn, assumption_id, published_only=True)
    else:
        published = findings.list_all(conn, published_only=True)
    out = [_finding_summary(conn, f) for f in published]
    if finding_type is not None:
        out = [s for s in out if s["finding_type"] == finding_type]
    return out


def get_finding(conn, finding_id):
    finding = findings.get_published(conn, finding_id)  # raises DbError unless approved+published
    return _finding_summary(conn, finding)


def compare_segment_feedback(conn, campaign_id, segment_a, segment_b):
    a = [_finding_summary(conn, f) for f in findings.list_for_campaign(conn, campaign_id, published_only=True)
        if f["segment_id"] == segment_a]
    b = [_finding_summary(conn, f) for f in findings.list_for_campaign(conn, campaign_id, published_only=True)
        if f["segment_id"] == segment_b]
    return {"campaign_id": campaign_id, "segment_a": {"segment_id": segment_a, "findings": a},
           "segment_b": {"segment_id": segment_b, "findings": b},
           "grouping_note": "Segments are compared side by side; never pooled into one combined count."}


def get_campaign_limitations(conn, campaign_id):
    published = findings.list_for_campaign(conn, campaign_id, published_only=True)
    return {"campaign_id": campaign_id,
           "limitations": sorted({l for f in published for l in f["limitations"]})}


def _quote_eligible(conn, obs, now):
    if not obs["is_direct_quote"]:
        return False
    if obs["workflow_status"] != "approved" or obs["suppression_status"] != "active":
        return False
    participant = get_participant(conn, obs["participant_id"])
    if not participant["quote_permission"]:
        return False
    if not consent_is_valid(participant, now):
        return False
    if is_retention_expired(participant, now):
        return False
    return True


def get_merchant_quotes(conn, now, campaign_id=None, finding_id=None):
    """Direct-quote observations still eligible at query time, linked only
    to a currently approved+published, non-superseded finding."""
    if finding_id is not None:
        published = [findings.get_published(conn, finding_id)]
    elif campaign_id is not None:
        published = findings.list_for_campaign(conn, campaign_id, published_only=True)
    else:
        published = findings.list_all(conn, published_only=True)

    out = []
    for f in published:
        candidate = candidates_mod.get(conn, f["candidate_id"])
        for ref in candidate["observations"]:
            obs = get_observation(conn, ref["observation_id"])
            if _quote_eligible(conn, obs, now):
                out.append({"finding_id": f["finding_id"], "campaign_id": f["campaign_id"],
                           "observation_id": obs["observation_id"], "text": obs["normalized_statement"],
                           "role": ref["role"]})
    return out
