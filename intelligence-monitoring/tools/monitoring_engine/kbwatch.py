"""The knowledge-base watcher: state snapshots + diffing.

Customer-intelligence monitoring is a differ over the knowledge base the
agent already maintains (DESIGN.md §3.1). This module builds a compact state
snapshot of the KB, diffs two snapshots into raw observations, and converts
observations into scored events.

State can be built from the working tree or from any git ref (`--from-ref`),
so the watcher can replay history. Reads A's records via Workstream B's
parsers (reuse over reimplementation); writes nothing outside monitoring/.
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from . import events as ev_mod
from . import significance
from .significance import MonitorError

_B_TOOLS = None


def _b_engine(root):
    """Lazy import of Workstream B's parsers (read-only reuse)."""
    global _B_TOOLS
    tools = str(Path(root).resolve() / "opportunity-intelligence" / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import opportunity_engine.backlog as b_backlog
    import opportunity_engine.evidence as b_evidence
    import opportunity_engine.journal as b_journal
    import opportunity_engine.results as b_results
    return b_evidence, b_backlog, b_journal, b_results

CONFIDENCE_RE = re.compile(r"\*\*Confidence:\*\*\s*(High|Medium|Low)", re.IGNORECASE)
IP_STATUS_RE = re.compile(r"\*\*Status:\*\*\s*([a-z-]+)")


def build_state(root):
    """Snapshot the KB's monitorable surface into a plain dict."""
    root = Path(root)
    kb = root / "knowledge-base"
    b_evidence, b_backlog, b_journal, b_results = _b_engine(root)

    state = {"evidence": {}, "segments": {}, "inflection_points": {},
             "backlog": {}, "experiments": {}, "predictions": {}}

    for rid, rec in b_evidence.load_records(kb / "customer-evidence").items():
        state["evidence"][rid] = {
            "status": rec.get("status"),
            "confidence": (rec.get("evidence_confidence") or "").split(" ")[0],
            "scores": rec.get("scores", {}),
        }

    for path in sorted(kb.glob("segments/SEG-*.md")):
        m = CONFIDENCE_RE.search(path.read_text(encoding="utf-8"))
        state["segments"][path.stem] = {"confidence": m.group(1) if m else "?"}

    for path in sorted(kb.glob("inflection-points/IP-*.md")):
        m = IP_STATUS_RE.search(path.read_text(encoding="utf-8"))
        state["inflection_points"][path.stem] = {"status": m.group(1) if m else "?"}

    backlog_path = kb / "product-ideas" / "BACKLOG.md"
    if backlog_path.exists():
        data = b_backlog.parse(backlog_path)
        for row in data["backlog"]:
            state["backlog"][row["id"]] = {"enum": b_backlog.classification_enum(row["classification"]) or "?"}
        for row in data["archive"]:
            state["backlog"].setdefault(row["id"], {"enum": "reject"})

    for path in sorted(kb.glob("validation/*-result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        evaluated = b_results.evaluate(result)
        filled = sum(1 for m in result["metrics"] if m.get("observed") is not None)
        state["experiments"][result["experiment_id"]] = {
            "verdict": evaluated["verdict"], "observed_filled": filled,
            "n_metrics": len(result["metrics"]),
        }

    journal_path = kb / "product-ideas" / "decision-journal.json"
    if journal_path.exists():
        for p in b_journal.load(journal_path)["predictions"]:
            state["predictions"][p["id"]] = {"outcome": p.get("outcome")}

    return state


def build_state_at_ref(root, ref):
    """Snapshot the KB as of a git ref by materialising the needed files."""
    root = Path(root).resolve()
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref, "knowledge-base"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    wanted = [p for p in listing if
              p.startswith("knowledge-base/customer-evidence/records/") or
              p.startswith("knowledge-base/segments/SEG-") or
              p.startswith("knowledge-base/inflection-points/IP-") or
              p.endswith("product-ideas/BACKLOG.md") or
              p.endswith("product-ideas/decision-journal.json") or
              (p.startswith("knowledge-base/validation/") and p.endswith("-result.json"))]
    with tempfile.TemporaryDirectory(prefix="kbwatch-ref-") as tmp:
        tmp_root = Path(tmp)
        # parsers come from the CURRENT tree; only the KB is materialised at ref
        (tmp_root / "opportunity-intelligence").symlink_to(root / "opportunity-intelligence")
        for rel in wanted:
            blob = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=root,
                                  capture_output=True, text=True, check=True).stdout
            dest = tmp_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(blob, encoding="utf-8")
        return build_state(tmp_root)


def diff_states(old, new):
    """Diff two snapshots into raw observations: (signal_type, entity, title, details)."""
    obs = []

    def emit(signal_type, entity, title, details=None):
        obs.append({"signal_type": signal_type, "entity": entity,
                    "title": title, "details": details or {}})

    for rid, rec in new["evidence"].items():
        old_rec = old["evidence"].get(rid)
        if old_rec is None:
            emit("new_evidence_record", rid, f"New evidence record {rid}",
                 {"status": rec["status"], "confidence": rec["confidence"]})
            continue
        if rec["status"] != old_rec["status"]:
            emit("evidence_status_change", rid,
                 f"{rid} status {old_rec['status']} → {rec['status']}")
        deltas = {a: (old_rec["scores"].get(a), v) for a, v in rec["scores"].items()
                  if old_rec["scores"].get(a) not in (None, v)}
        if deltas:
            moved = ", ".join(f"{a} {o}→{n}" for a, (o, n) in sorted(deltas.items()))
            emit("evidence_score_change", rid, f"{rid} rescored: {moved}", {"deltas": moved})

    for sid, seg in new["segments"].items():
        old_seg = old["segments"].get(sid)
        if old_seg is None:
            emit("new_segment", sid, f"New segment profile {sid}")
        elif seg["confidence"] != old_seg["confidence"]:
            emit("segment_confidence_change", sid,
                 f"{sid} confidence {old_seg['confidence']} → {seg['confidence']}")

    for iid, ip in new["inflection_points"].items():
        old_ip = old["inflection_points"].get(iid)
        if old_ip is None:
            emit("new_inflection_point", iid, f"New inflection point {iid}")
        elif ip["status"] != old_ip["status"]:
            emit("ip_status_change", iid, f"{iid} status {old_ip['status']} → {ip['status']}")

    for oid, row in new["backlog"].items():
        old_row = old["backlog"].get(oid)
        if old_row is None:
            emit("new_opportunity", oid, f"New backlog proposition {oid} ({row['enum']})")
        elif row["enum"] != old_row["enum"]:
            emit("opportunity_reclassified", oid,
                 f"{oid} reclassified {old_row['enum']} → {row['enum']}")

    for vid, exp in new["experiments"].items():
        old_exp = old["experiments"].get(vid)
        if old_exp is None:
            emit("new_experiment", vid, f"New validation experiment {vid} (pre-committed)")
            continue
        if exp["verdict"] != old_exp["verdict"]:
            if exp["verdict"] in ("pass", "fail"):
                emit("ve_verdict_conclusive", vid,
                     f"{vid} verdict: {old_exp['verdict']} → {exp['verdict'].upper()}")
            else:
                emit("ve_observations_progress", vid,
                     f"{vid} verdict {old_exp['verdict']} → {exp['verdict']}")
        elif exp["observed_filled"] != old_exp["observed_filled"]:
            emit("ve_observations_progress", vid,
                 f"{vid} field data: {exp['observed_filled']}/{exp['n_metrics']} metrics observed")

    for pid, pred in new["predictions"].items():
        old_pred = old["predictions"].get(pid)
        if old_pred is not None and pred["outcome"] is not None and old_pred["outcome"] is None:
            emit("prediction_resolved", pid, f"{pid} resolved {pred['outcome']}")

    return obs


def observations_to_events(observations, existing_events, detected_at, week):
    """Score observations with signal-type defaults and build deduplicated events."""
    created = []
    pool = list(existing_events)
    for o in observations:
        scores = significance.default_scores(o["signal_type"])
        kb_links = [o["entity"]] if re.match(r"^(EV|IP|SEG|OPP|VE|PRED)-", o["entity"]) else []
        e, is_new = ev_mod.make_event(
            pool, entity=o["entity"], detected_at=detected_at, adapter="kb-watcher",
            signal_type=o["signal_type"], title=o["title"], scores=scores,
            week=week, details=o["details"], kb_links=kb_links,
        )
        if is_new:
            created.append(e)
            pool.append(e)
    return created
