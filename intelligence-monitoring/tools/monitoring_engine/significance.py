"""Significance scoring and mechanical tiering.

Implements frameworks/significance-scoring.md. The tier is COMPUTED from the
five axis scores — never chosen. `monitor.py check` recomputes stored tiers
and fails on mismatch, so an enthusiastic hand-edit cannot survive the gate.
"""


class MonitorError(ValueError):
    pass


AXES = ("impact", "urgency", "confidence", "relevance", "novelty")
TIERS = ("insignificant", "informative", "important", "critical")

# defaults per internal (KB-watcher) signal type — frameworks table
DEFAULT_SCORES = {
    "ve_verdict_conclusive":    {"impact": 5, "urgency": 4, "confidence": 5, "relevance": 5, "novelty": 5},
    "ve_observations_progress": {"impact": 2, "urgency": 2, "confidence": 5, "relevance": 4, "novelty": 3},
    "opportunity_reclassified": {"impact": 4, "urgency": 3, "confidence": 5, "relevance": 5, "novelty": 4},
    "new_opportunity":          {"impact": 3, "urgency": 3, "confidence": 4, "relevance": 5, "novelty": 4},
    "new_evidence_record":      {"impact": 2, "urgency": 2, "confidence": 3, "relevance": 4, "novelty": 3},
    "evidence_score_change":    {"impact": 3, "urgency": 2, "confidence": 3, "relevance": 4, "novelty": 3},
    "evidence_status_change":   {"impact": 2, "urgency": 2, "confidence": 4, "relevance": 4, "novelty": 3},
    "segment_confidence_change": {"impact": 3, "urgency": 2, "confidence": 4, "relevance": 5, "novelty": 4},
    "new_segment":              {"impact": 3, "urgency": 3, "confidence": 3, "relevance": 5, "novelty": 4},
    "new_inflection_point":     {"impact": 3, "urgency": 3, "confidence": 3, "relevance": 5, "novelty": 4},
    "ip_status_change":         {"impact": 4, "urgency": 4, "confidence": 4, "relevance": 5, "novelty": 4},
    "prediction_resolved":      {"impact": 3, "urgency": 2, "confidence": 5, "relevance": 4, "novelty": 4},
    "new_experiment":           {"impact": 2, "urgency": 2, "confidence": 5, "relevance": 4, "novelty": 3},
}


def validate_scores(scores):
    if not isinstance(scores, dict):
        raise MonitorError("scores must be an object")
    missing = [a for a in AXES if a not in scores]
    if missing:
        raise MonitorError(f"scores missing axes: {', '.join(missing)}")
    unknown = [a for a in scores if a not in AXES]
    if unknown:
        raise MonitorError(f"unknown score axes: {', '.join(unknown)}")
    for axis in AXES:
        v = scores[axis]
        if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 5:
            raise MonitorError(f"score '{axis}' must be an integer 1..5, got {v!r}")


def tier(scores):
    """The mechanical tier rule, in evaluation order (confidence gate first)."""
    validate_scores(scores)
    s = scores
    if s["confidence"] < 3:
        return "informative" if s["relevance"] >= 3 else "insignificant"
    if s["impact"] >= 4 and s["urgency"] >= 4:
        return "critical"
    if s["impact"] >= 3 and s["novelty"] >= 3:
        return "important"
    if s["relevance"] >= 3:
        return "informative"
    return "insignificant"


def default_scores(signal_type):
    if signal_type not in DEFAULT_SCORES:
        raise MonitorError(f"no default scores for signal type '{signal_type}'")
    return dict(DEFAULT_SCORES[signal_type])
