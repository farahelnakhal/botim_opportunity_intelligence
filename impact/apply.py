"""Approval + transactional application of an impact proposal.

Order (correction 2): manifest during prepare/apply; the append-only applied
history entry is written ONLY after every target — scorecard, segment,
assumption register, monitoring summary and email preview — has been replaced
and passed post-apply hash validation.
"""

import copy
import datetime
import json
import re
from pathlib import Path

from . import (assumptions, email, history, monitoring, paths, proposal,
               transaction)
from .errors import ImpactError

CONF_LINE = re.compile(r"(\*\*Confidence:\*\*\s*)(High|Medium|Low)")


def _today():
    return datetime.date.today().isoformat()


def _load_proposal(ref):
    p = Path(ref)
    if not p.exists():
        p = paths.PROPOSALS_DIR / f"{ref}.json"
    if not p.exists():
        raise ImpactError(f"proposal not found: {ref}")
    return json.loads(p.read_text(encoding="utf-8")), p


def _slug(opp_id):
    return opp_id.lower()


def _resolve(prop, segment_applied):
    opp = prop["payload"]["score_summary"]["opportunity_id"]
    slug = _slug(opp)
    targets = {
        "scorecard": paths.KB / "opportunity-scores" / f"{slug}-scorecard.json",
        "assumptions": paths.ASSUMPTIONS_DIR / f"{slug}.json",
        "monitoring": paths.MONITORING_DIR / f"{slug}-summary.md",
        "email": paths.EMAIL_DIR / f"{prop['proposal_id']}.md",
    }
    if segment_applied and prop["payload"]["segment_changes"]:
        seg_id = prop["payload"]["segment_changes"][0]["segment_id"]
        targets["segment"] = paths.KB / "segments" / f"{seg_id}.md"
    return targets


def _validate_scorecard(content):
    scoring, _ = paths.load_engine()
    card = json.loads(content)
    ev = scoring.evaluate(card)
    if ev["violations"]:
        raise ImpactError("scorecard validation failed: " + "; ".join(ev["violations"]))


def _validate_segment(content):
    if not CONF_LINE.search(content):
        raise ImpactError("segment file missing a valid **Confidence:** High|Medium|Low line")


def apply_impact(ref, approver, confirm_segment_upgrade=False):
    if not approver:
        raise ImpactError("--approver is required for apply (a real apply must record who approved)")

    recovered = transaction.preflight()
    if recovered:
        raise ImpactError(
            f"recovered interrupted transaction(s) {recovered}; state restored — please re-run")

    prop, prop_path = _load_proposal(ref)
    if prop["lifecycle"]["status"] != "pending":
        raise ImpactError(f"proposal {prop['proposal_id']} is '{prop['lifecycle']['status']}', not pending")
    proposal.verify_integrity(prop)

    payload = prop["payload"]
    scoring, _ = paths.load_engine()
    segment_applied = bool(payload["segment_changes"]) and confirm_segment_upgrade
    targets = _resolve(prop, segment_applied)

    # --- preconditions: live state must still match proposal old values ---
    card = json.loads(targets["scorecard"].read_text(encoding="utf-8"))
    for fc in payload["factor_changes"]:
        cur = card["scores"][fc["factor"]]
        if cur["score"] != fc["old_score"] or bool(cur.get("assumption", True)) != fc["old_assumption"]:
            raise ImpactError(
                f"stale proposal: {fc['factor']} is now score={cur['score']} "
                f"assumption={cur.get('assumption', True)}, expected {fc['old_score']}/{fc['old_assumption']}")

    seg_old_content = None
    if segment_applied:
        seg_old_content = targets["segment"].read_text(encoding="utf-8")
        m = CONF_LINE.search(seg_old_content)
        sc = payload["segment_changes"][0]
        if not m or m.group(2) != sc["old"]:
            raise ImpactError(
                f"stale proposal: segment confidence is '{m.group(2) if m else '?'}', expected '{sc['old']}'")

    if not payload["factor_changes"] and not segment_applied:
        raise ImpactError("proposal has no applicable changes to apply")

    # --- build new contents in memory ---
    new_card = copy.deepcopy(card)
    for fc in payload["factor_changes"]:
        e = new_card["scores"][fc["factor"]]
        e["score"] = fc["proposed_score"]
        e["assumption"] = fc["proposed_assumption"]
        e["basis"] = f"{fc['ev_id']}: {fc['justification']}"
    new_card_content = json.dumps(new_card, indent=2, ensure_ascii=False) + "\n"

    old_reg = None
    if targets["assumptions"].exists():
        old_reg = json.loads(targets["assumptions"].read_text(encoding="utf-8"))
    new_reg = assumptions.compute_new(card, old_reg, payload["assumption_changes"])
    new_reg_content = assumptions.dumps(new_reg)

    new_mon = monitoring.render_markdown(prop, segment_applied)
    new_email = email.render(prop, segment_applied)  # raises on overclaim

    target_specs = [
        (str(targets["scorecard"]), new_card_content),
        (str(targets["assumptions"]), new_reg_content),
        (str(targets["monitoring"]), new_mon),
        (str(targets["email"]), new_email),
    ]
    if segment_applied:
        new_seg = CONF_LINE.sub(
            lambda mm: mm.group(1) + payload["segment_changes"][0]["proposed"], seg_old_content, count=1)
        target_specs.append((str(targets["segment"]), new_seg))

    validators = {
        str(targets["scorecard"]): _validate_scorecard,
        str(targets["email"]): lambda c: email._guard(c, require_bounded=True),
    }
    if segment_applied:
        validators[str(targets["segment"])] = _validate_segment

    # capture prior contents for rollback metadata (None = file did not exist)
    prior_contents = {}
    for path, _ in target_specs:
        pp = Path(path)
        prior_contents[path] = pp.read_text(encoding="utf-8") if pp.exists() else None

    txn = transaction.Transaction("apply", prop["proposal_id"], prop["proposal_hash"])
    with txn:
        txn.prepare(target_specs)
        try:
            txn.validate_staged(validators)
        except ImpactError:
            txn.abort()
            raise
        txn.commit()  # replaces all; post-apply hash validation inside

    # --- only now: append the applied history entry (append-only) ---
    s = payload["score_summary"]
    hist = {
        "history_id": history.next_history_id(),
        "kind": "applied",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "proposal_id": prop["proposal_id"],
        "transaction_id": txn.transaction_id,
        "ev_ids": payload["trigger"]["ev_ids"],
        "opportunity_id": s["opportunity_id"],
        "prev_factor_values": {fc["factor"]: {"score": fc["old_score"], "assumption": fc["old_assumption"]}
                               for fc in payload["factor_changes"]},
        "updated_factor_values": {fc["factor"]: {"score": fc["proposed_score"], "assumption": fc["proposed_assumption"]}
                                  for fc in payload["factor_changes"]},
        "raw_score_prev": s["raw_score_prev"], "raw_score_new": s["raw_score_new"],
        "composite_prev": s["composite_prev"], "composite_new": s["composite_new"],
        "assumption_count_prev": s["assumption_count_prev"], "assumption_count_new": s["assumption_count_new"],
        "confidence_change": ({"segment": f"{payload['segment_changes'][0]['old']}->{payload['segment_changes'][0]['proposed']}"}
                              if segment_applied else None),
        "approved_by": approver,
        "explanation": f"Applied {prop['proposal_id']} from evidence {', '.join(payload['trigger']['ev_ids'])}.",
        "rollback": {"files": [{"path": p, "prior_content": prior_contents[p]} for p, _ in target_specs]},
    }
    history.append(hist)

    # lifecycle update only (payload untouched -> proposal_hash unchanged)
    prop["lifecycle"].update({"status": "applied", "applied_at": _today(),
                              "approved_by": approver, "transaction_id": txn.transaction_id})
    proposal.verify_integrity(prop)
    prop_path.write_text(json.dumps(prop, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {"proposal_id": prop["proposal_id"], "history_id": hist["history_id"],
            "transaction_id": txn.transaction_id, "segment_applied": segment_applied,
            "targets": [p for p, _ in target_specs]}


def reject_impact(ref, rejected_by="cli:local"):
    prop, prop_path = _load_proposal(ref)
    if prop["lifecycle"]["status"] != "pending":
        raise ImpactError(f"proposal {prop['proposal_id']} is '{prop['lifecycle']['status']}', not pending")
    prop["lifecycle"].update({"status": "rejected", "rejected_at": _today(), "rejected_by": rejected_by})
    proposal.verify_integrity(prop)  # payload still intact
    prop_path.write_text(json.dumps(prop, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"proposal_id": prop["proposal_id"], "status": "rejected"}
