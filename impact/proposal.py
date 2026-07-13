"""Impact-proposal generation.

Produces a structured proposal from a detected evidence change plus the target
scorecard (and optional segment). Writes only proposal files; never touches any
target. The immutable decision payload is hashed separately from mutable
lifecycle metadata (proposal_hash covers `payload` only).
"""

import copy

from . import mapping
from .errors import ImpactError
from .paths import canonical_json, load_engine, sha256_text

RAW_MAX = 85  # 17 factors x 5


def _raw_score(scores):
    return sum(e["score"] for e in scores.values())


def _assumption_count(scores):
    return sum(1 for e in scores.values() if e.get("assumption", True))


def _validate_descriptor(d):
    for key in ("ev_id", "evidence_confidence", "evidence_strength", "evidence_class", "observations"):
        if key not in d:
            raise ImpactError(f"evidence descriptor missing '{key}'")
    if not isinstance(d["observations"], list) or not d["observations"]:
        raise ImpactError("evidence descriptor needs a non-empty 'observations' list")


def generate(scorecard, descriptor, segment=None, proposal_id="PROP-UNSET", today="1970-01-01"):
    """Build a proposal dict. Pure: no file writes, no target mutation."""
    scoring, _ = load_engine()
    _validate_descriptor(descriptor)

    old_card = scorecard
    old_scores = old_card["scores"]
    opp_id = old_card["opportunity_id"]

    conf = descriptor["evidence_confidence"]
    strength = descriptor["evidence_strength"]
    ev_class = descriptor["evidence_class"]
    ev_id = descriptor["ev_id"]

    factor_changes, assumption_changes, unchanged, warnings = [], [], [], []

    # gate the whole evidence item once
    gate = mapping.gate_reason(conf, strength, ev_class)

    used_fields = [o["evidence_field"] for o in descriptor["observations"]]
    mapping.assert_no_fanout(used_fields)

    new_scores = copy.deepcopy(old_scores)

    for obs in descriptor["observations"]:
        field = obs["evidence_field"]
        factor = mapping.resolve_factor(field)
        if factor not in old_scores:
            raise ImpactError(f"scorecard has no factor '{factor}' for field '{field}'")
        cur = old_scores[factor]
        justification = obs.get("justification", "").strip()
        if not justification:
            raise ImpactError(f"observation for '{field}' needs a justification")

        if gate is not None:
            unchanged.append({"factor": factor, "reason": gate})
            warnings.append(f"{field} -> {factor}: no change ({gate})")
            continue

        deassume_only = bool(obs.get("deassume_only"))
        if deassume_only:
            if not cur.get("assumption", True):
                unchanged.append({"factor": factor, "reason": "already evidenced (assumption already false)"})
                continue
            new_scores[factor] = {**cur, "assumption": False}
            factor_changes.append({
                "opportunity_id": opp_id, "factor": factor, "ev_id": ev_id,
                "evidence_field": field, "change_type": "deassume-only",
                "old_score": cur["score"], "proposed_score": cur["score"],
                "old_assumption": cur.get("assumption", True), "proposed_assumption": False,
                "anchor_ref": "score unchanged", "justification": justification,
            })
            unchanged.append({"factor": factor, "reason": "score unchanged (de-assume only)"})
        else:
            proposed = obs.get("proposed_score")
            if not isinstance(proposed, int) or isinstance(proposed, bool) or not 1 <= proposed <= 5:
                raise ImpactError(f"observation for '{field}': proposed_score must be int 1..5")
            change_type = "score"
            new_assumption = cur.get("assumption", True)
            if new_assumption:
                new_assumption = False
                change_type = "score+deassume"
            new_scores[factor] = {"score": proposed, "assumption": new_assumption,
                                  "basis": f"{ev_id}: {justification}"}
            factor_changes.append({
                "opportunity_id": opp_id, "factor": factor, "ev_id": ev_id,
                "evidence_field": field, "change_type": change_type,
                "old_score": cur["score"], "proposed_score": proposed,
                "old_assumption": cur.get("assumption", True), "proposed_assumption": new_assumption,
                "anchor_ref": f"evidence-scoring anchor {proposed}", "justification": justification,
            })

        assumption_changes.append({
            "opportunity_id": opp_id, "assumption": factor,
            "old_status": "untested",
            "proposed_status": mapping.assumption_status_for(conf),
            "supporting_ev": [ev_id],
            "next_validation": obs.get("next_validation", ""),
        })

    # score summary (raw sum /85 + engine composite, both before/after)
    old_eval = scoring.evaluate(old_card)
    new_card = {**old_card, "scores": new_scores}
    new_eval = scoring.evaluate(new_card)
    class_prev = old_card.get("proposed_classification")
    class_new = class_prev
    if class_prev == "strong" and new_eval["assumption_capped"]:
        class_new = "promising"

    changed = bool(factor_changes) or bool(assumption_changes)

    segment_changes = []
    if segment is not None:
        seg = segment
        segment_changes.append({
            "segment_id": seg["segment_id"],
            "field": "confidence",
            "old": seg.get("current_confidence"),
            "proposed": seg["proposed_confidence"],
            "upgrade_rule": seg.get("upgrade_rule", "see segment file upgrade condition"),
            "rule_satisfied": "requires_human_confirmation",
            "justification": seg.get("justification", ""),
        })
        warnings.append(
            f"segment {seg['segment_id']} confidence {seg.get('current_confidence')}"
            f"->{seg['proposed_confidence']} requires --confirm-segment-upgrade (rule not auto-satisfied)"
        )

    if class_new != class_prev:
        alert_tier = "urgent"
    elif changed or segment_changes:
        alert_tier = "review"
    else:
        alert_tier = "info"

    if not changed and not segment_changes:
        warnings.append("no rescore: evidence did not clear the safety gates")

    payload = {
        "requires_human_approval": True,
        "trigger": {
            "ev_ids": [ev_id],
            "ev_evidence_confidence": conf,
            "ev_evidence_strength": strength,
            "ev_evidence_class": ev_class,
        },
        "affected": {
            "segment_ids": [s["segment_id"] for s in segment_changes],
            "opportunity_ids": [opp_id],
        },
        "segment_changes": segment_changes,
        "factor_changes": factor_changes,
        "assumption_changes": assumption_changes,
        "score_summary": {
            "opportunity_id": opp_id,
            "raw_score_prev": _raw_score(old_scores), "raw_score_new": _raw_score(new_scores),
            "raw_max": RAW_MAX,
            "composite_prev": old_eval["composite_indicative"],
            "composite_new": new_eval["composite_indicative"],
            "assumption_count_prev": _assumption_count(old_scores),
            "assumption_count_new": _assumption_count(new_scores),
            "classification_prev": class_prev,
            "classification_new": class_new,
            "alert_tier": alert_tier,
        },
        "unchanged": unchanged,
        "warnings": warnings,
        "unresolved_questions": descriptor.get("unresolved_questions", []),
    }

    return {
        "proposal_id": proposal_id,
        "proposal_hash": sha256_text(canonical_json(payload)),
        "lifecycle": {
            "status": "pending", "created": today,
            "approved_by": None, "applied_at": None,
            "rejected_at": None, "rejected_by": None, "transaction_id": None,
        },
        "payload": payload,
    }


def verify_integrity(proposal):
    """Recompute the payload hash and confirm it matches the stored proposal_hash.
    Detects any edit to the immutable payload since generation."""
    expected = sha256_text(canonical_json(proposal["payload"]))
    if expected != proposal.get("proposal_hash"):
        raise ImpactError(
            "proposal integrity check failed: payload hash does not match proposal_hash "
            "(the immutable decision payload was edited after generation)"
        )
    return True
