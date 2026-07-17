"""SQLite conversation store (stdlib). Convenience context, not evidence.

Stores only: conversation id, messages, selected opportunity/segment context,
cited internal IDs, timestamps. Never writes to the knowledge base. The DB
file lives in the gitignored copilot-backend/data/ directory.
"""

import datetime
import json
import sqlite3
import uuid


def _now():
    return datetime.datetime.utcnow().isoformat() + "Z"


class ConversationStore:
    def __init__(self, db_path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.execute("""CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY, created_at TEXT, updated_at TEXT, context_json TEXT)""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT,
            cited_json TEXT, created_at TEXT)""")
        # Phase R8b — per-user ownership. Pre-auth conversations keep a NULL
        # owner (legacy shared); new ones created with an authenticated
        # identity carry the USER- id. Idempotent PRAGMA-guarded migration.
        existing = {r[1] for r in self._db.execute("PRAGMA table_info(conversations)")}
        if "owner_user_id" not in existing:
            self._db.execute("ALTER TABLE conversations ADD COLUMN owner_user_id TEXT")
        self._db.commit()

    def create_conversation(self, context=None, owner_user_id=None):
        cid = "conv_" + uuid.uuid4().hex[:12]
        now = _now()
        self._db.execute("INSERT INTO conversations "
                         "(id, created_at, updated_at, context_json, owner_user_id) "
                         "VALUES (?,?,?,?,?)",
                         (cid, now, now, json.dumps(context or {}), owner_user_id))
        self._db.commit()
        return cid

    def get_conversation(self, cid):
        row = self._db.execute(
            "SELECT id, created_at, updated_at, context_json, owner_user_id "
            "FROM conversations WHERE id=?",
            (cid,)).fetchone()
        if row is None:
            return None
        count = self._db.execute("SELECT COUNT(*) FROM messages WHERE conversation_id=?",
                                 (cid,)).fetchone()[0]
        return {"conversation_id": row[0], "created_at": row[1], "updated_at": row[2],
                "context": json.loads(row[3] or "{}"), "message_count": count,
                "owner_user_id": row[4]}

    def update_context(self, cid, context):
        self._db.execute("UPDATE conversations SET context_json=?, updated_at=? WHERE id=?",
                         (json.dumps(context), _now(), cid))
        self._db.commit()

    def add_message(self, cid, role, content, cited_ids=None):
        mid = "msg_" + uuid.uuid4().hex[:12]
        self._db.execute("INSERT INTO messages VALUES (?,?,?,?,?,?)",
                         (mid, cid, role, content, json.dumps(cited_ids or []), _now()))
        self._db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (_now(), cid))
        self._db.commit()
        return mid

    def get_messages(self, cid, limit=None):
        rows = self._db.execute(
            "SELECT id, role, content, cited_json, created_at FROM messages "
            "WHERE conversation_id=? ORDER BY created_at, id", (cid,)).fetchall()
        msgs = [{"message_id": r[0], "role": r[1], "content": r[2],
                 "cited_ids": json.loads(r[3] or "[]"), "created_at": r[4]} for r in rows]
        return msgs[-limit:] if limit else msgs

    def delete_conversation(self, cid):
        """Complete deletion: conversation row AND all its messages."""
        cur = self._db.execute("DELETE FROM conversations WHERE id=?", (cid,))
        self._db.execute("DELETE FROM messages WHERE conversation_id=?", (cid,))
        self._db.commit()
        return cur.rowcount > 0
