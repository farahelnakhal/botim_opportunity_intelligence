"""Append-only audit events.

Stores: actor_id, actor_role, action, object_type, object_id, timestamp,
reason, before/after hashes, a safe structured diff, and a self_approval flag.

Never stores: tokens, secrets, provider payloads, raw sensitive content, or
full request bodies. `safe_diff` must be built from already-safe field-level
values only (callers are responsible for not passing raw transcript/PII
content into it — Phase 1 objects, campaigns and guides, contain no such
content by construction; Phase 2 callers pass summary counts/ids only, never
answer/transcript text).

`record()` deliberately does NOT open its own `with conn:` transaction: it
is always called from within a caller-owned `with conn:` block (every call
site in this service does this). sqlite3's `with conn:` context manager is
not re-entrant — an inner `with conn:` commits the connection's entire
pending transaction on normal exit, which would prematurely commit the
caller's earlier, still-in-progress writes before the caller's own block
finishes. Nesting it here would silently break atomicity for every
multi-statement operation that calls audit.record() partway through.
"""

import hashlib
import json
import uuid


def _hash(value):
    if value is None:
        return None
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def record(conn, actor_id, actor_role, action, object_type, object_id, timestamp,
          reason=None, before=None, after=None, safe_diff=None, self_approval=False):
    audit_id = "AUD-" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO audit_events (audit_id, actor_id, actor_role, action, object_type, "
        "object_id, timestamp, reason, before_hash, after_hash, safe_diff_json, self_approval) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (audit_id, actor_id, actor_role, action, object_type, object_id, timestamp,
         reason, _hash(before), _hash(after), json.dumps(safe_diff or {}, ensure_ascii=False),
         1 if self_approval else 0))
    return audit_id


def list_for_object(conn, object_type, object_id):
    rows = conn.execute(
        "SELECT audit_id, actor_id, actor_role, action, object_type, object_id, timestamp, "
        "reason, before_hash, after_hash, safe_diff_json, self_approval FROM audit_events "
        "WHERE object_type=? AND object_id=? ORDER BY timestamp, audit_id",
        (object_type, object_id)).fetchall()
    return [{
        "audit_id": r[0], "actor_id": r[1], "actor_role": r[2], "action": r[3],
        "object_type": r[4], "object_id": r[5], "timestamp": r[6], "reason": r[7],
        "before_hash": r[8], "after_hash": r[9],
        "safe_diff": json.loads(r[10]) if r[10] else {},
        "self_approval": bool(r[11]),
    } for r in rows]
