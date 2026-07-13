"""Rollback of one applied impact.

Restores the previous segment and opportunity values from the applied history
entry's rollback metadata, transactionally. Preserves the original history
(never deleted) and appends a new rollback entry; regenerates nothing beyond
the restored files (the monitoring summary is one of those restored files).
"""

import datetime
import json
from pathlib import Path

from . import apply as apply_mod
from . import history, transaction
from .errors import ImpactError


def _already_rolled_back(history_id):
    for e in history.read_all():
        if e.get("kind") == "rollback" and e.get("target_history_id") == history_id:
            return True
    return False


def rollback_impact(history_id, approver):
    if not approver:
        raise ImpactError("--approver is required for rollback")

    recovered = transaction.preflight()
    if recovered:
        raise ImpactError(
            f"recovered interrupted transaction(s) {recovered}; state restored — please re-run")

    entry = history.find(history_id)
    if entry is None:
        raise ImpactError(f"no history entry {history_id}")
    if entry.get("kind") != "applied":
        raise ImpactError(f"{history_id} is kind '{entry.get('kind')}', only 'applied' entries roll back")
    if _already_rolled_back(history_id):
        raise ImpactError(f"{history_id} was already rolled back")

    files = entry["rollback"]["files"]
    target_specs = [(f["path"], f["prior_content"]) for f in files]  # None -> delete

    validators = {}
    for path, content in target_specs:
        if content is not None and path.endswith("-scorecard.json"):
            validators[path] = apply_mod._validate_scorecard

    txn = transaction.Transaction("rollback", entry["proposal_id"], entry.get("proposal_id", ""))
    with txn:
        txn.prepare(target_specs)
        try:
            txn.validate_staged(validators)
        except ImpactError:
            txn.abort()
            raise
        txn.commit()

    rb = {
        "history_id": history.next_history_id(),
        "kind": "rollback",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "target_history_id": history_id,
        "proposal_id": entry["proposal_id"],
        "transaction_id": txn.transaction_id,
        "opportunity_id": entry.get("opportunity_id"),
        "restored_paths": [p for p, _ in target_specs],
        "restored_factor_values": entry.get("prev_factor_values", {}),
        "approved_by": approver,
        "explanation": f"Rolled back {history_id} (proposal {entry['proposal_id']}).",
    }
    history.append(rb)
    return {"history_id": rb["history_id"], "target_history_id": history_id,
            "transaction_id": txn.transaction_id, "restored": rb["restored_paths"]}
