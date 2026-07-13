"""Stable UI JSON envelope assembled from the normalized brief view.

Shape matches shared/contracts/executive-brief.schema.md. All values come from
the same view object the Markdown brief uses (guaranteed parity).
"""


def envelope(view):
    return {
        "meta": view["meta"],
        "opportunity": {
            "opportunity_id": view["opportunity_id"],
            "name": view["name"],
            "customer": view["customer"],
        },
        "score": view["score"],
        "confidence": view["confidence"],
        "assumptions": view["assumptions"],
        "evidence": {
            "supporting_primary": view["supporting_primary"],
            "supporting_leads": view["supporting_leads"],
            "contradicting": view["contradicting"],
            "detail": view["supporting_detail"],
        },
        "recent_changes": view["recent_changes"],
        "recommended_action": view["recommended_action"],
        "decision_requested": view["decision_requested"],
    }
