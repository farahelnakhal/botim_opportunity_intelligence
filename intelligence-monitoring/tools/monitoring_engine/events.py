"""Event schema, fingerprinting, dedup/threading, JSONL store.

Events live in knowledge-base/monitoring/events/YYYY-Wnn.jsonl (one JSON
object per line, batched per ISO week like Workstream A's records). Ids
follow the repo's collision rules: EVT-YYYY-Wnn-nnn, sequential per week,
never reused.
"""

import hashlib
import json
import re
from pathlib import Path

from .significance import AXES, TIERS, MonitorError, tier, validate_scores

EVENT_ID_RE = re.compile(r"^EVT-\d{4}-W\d{2}-\d{3}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STATUSES = ("new", "analyzed", "alerted", "digested", "archived")

REQUIRED_FIELDS = ("id", "entity", "detected_at", "adapter", "signal_type",
                   "fingerprint", "title", "scores", "tier", "status")
OPTIONAL_FIELDS = ("facts", "kb_links", "thread_id", "dedup_of", "details",
                   "score_note", "summary_ref", "evidence_candidate")


def fingerprint(entity, signal_type, content):
    """Stable identity of an observation: same fact from two routes → same print."""
    normalized = " ".join(str(content).lower().split())
    raw = f"{entity}|{signal_type}|{normalized}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def validate_event(e):
    if not isinstance(e, dict):
        raise MonitorError("event must be an object")
    for f in REQUIRED_FIELDS:
        if f not in e:
            raise MonitorError(f"event missing field '{f}'")
    unknown = [k for k in e if k not in REQUIRED_FIELDS + OPTIONAL_FIELDS]
    if unknown:
        raise MonitorError(f"event {e.get('id')}: unknown fields {unknown}")
    if not EVENT_ID_RE.match(e["id"]):
        raise MonitorError(f"event id {e['id']!r} must match EVT-YYYY-Wnn-nnn")
    if not DATE_RE.match(str(e["detected_at"])):
        raise MonitorError(f"{e['id']}: detected_at must be YYYY-MM-DD")
    if e["status"] not in STATUSES:
        raise MonitorError(f"{e['id']}: status {e['status']!r} not in {STATUSES}")
    validate_scores(e["scores"])
    if e["tier"] not in TIERS:
        raise MonitorError(f"{e['id']}: tier {e['tier']!r} not in {TIERS}")
    if e["tier"] != tier(e["scores"]):
        raise MonitorError(
            f"{e['id']}: stored tier '{e['tier']}' does not match computed "
            f"'{tier(e['scores'])}' — tiers are computed, never chosen"
        )
    if not str(e["title"]).strip():
        raise MonitorError(f"{e['id']}: empty title")


def load_events(events_dir):
    """Load all events from *.jsonl, validated. Returns list in file order."""
    out, seen = [], {}
    events_dir = Path(events_dir)
    if not events_dir.is_dir():
        return out
    for path in sorted(events_dir.glob("*.jsonl")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MonitorError(f"{path.name}:{n}: invalid JSON: {exc}")
            validate_event(e)
            if e["id"] in seen:
                raise MonitorError(f"duplicate event id {e['id']} ({path.name}:{n} and {seen[e['id']]})")
            seen[e["id"]] = f"{path.name}:{n}"
            out.append(e)
    return out


def next_id(existing_events, week):
    """Next sequential id for the given ISO week ('2026-W28')."""
    year, wk = week.split("-W")
    prefix = f"EVT-{year}-W{wk}-"
    ns = [int(e["id"].rsplit("-", 1)[1]) for e in existing_events if e["id"].startswith(prefix)]
    return f"{prefix}{max(ns, default=0) + 1:03d}"


def find_duplicate(existing_events, fp):
    """First existing event with the same fingerprint (dedup rule), else None."""
    for e in existing_events:
        if e["fingerprint"] == fp:
            return e
    return None


def make_event(existing_events, *, entity, detected_at, adapter, signal_type,
               title, scores, week, details=None, kb_links=None, score_note=""):
    """Build a validated event; if the fingerprint already exists, return the
    existing event (dedup — the caller decides whether to thread)."""
    fp = fingerprint(entity, signal_type, title)
    dup = find_duplicate(existing_events, fp)
    if dup is not None:
        return dup, False
    e = {
        "id": next_id(existing_events, week),
        "entity": entity,
        "detected_at": detected_at,
        "adapter": adapter,
        "signal_type": signal_type,
        "fingerprint": fp,
        "title": title,
        "scores": scores,
        "tier": tier(scores),
        "status": "new",
        "kb_links": kb_links or [],
        "details": details or {},
    }
    if score_note:
        e["score_note"] = score_note
    validate_event(e)
    return e, True


def append_events(events_dir, week, new_events):
    path = Path(events_dir) / f"{week}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for e in new_events:
            f.write(json.dumps(e, sort_keys=True) + "\n")
    return path
