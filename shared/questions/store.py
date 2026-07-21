"""Runtime persistence for draft merchant research-question sets (Phase R10, PR10b).

Mirrors shared/calculators/store.py and shared/research/store.py (the runtime-
store pattern):

- The committed Git knowledge base stays READ-ONLY. Draft question sets live in
  a separate runtime SQLite database, by default `runtime/question-sets.db`,
  overridable via QUESTION_SETS_DB_PATH. The runtime dir is gitignored.
- A question set is a **proposal**: `status` starts at `draft`; a human reviews
  it (PR10c) before any question is ever attached to a Merchant Voice guide.
  Nothing here validates the question taxonomy (that is the generator's job,
  against Merchant Voice's own validator) — this layer only persists what it is
  given, with structural bounds and ownership.
- Ownership (R8b pattern): new rows carry their creator's `USER-` id; pre-auth /
  no-auth rows keep a NULL owner and stay visible to every signed-in user
  (legacy shared). A foreign row answers an indistinguishable 404.
- ID namespace: RQSET-<12 hex> for the set; each question is `<RQSET-id>-Q<n>`.
  Cannot collide with any other namespace (OPP-/UOPP-/RRUN-/RSRC-/RCAND-/AWV-/
  WSUB-/MCFG-/MEVT-/DOC-/USER-/CALC-/MVC-/MVG-).

This store never generates, validates a taxonomy, calls a model, or writes the
knowledge base.
"""

import json
import os
import re
import sqlite3
import uuid
import datetime
from pathlib import Path

SCHEMA_VERSION = 2

REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO / "runtime" / "question-sets.db"

RQSET_RE = re.compile(r"^RQSET-[0-9a-f]{12}$")
OPP_RE = re.compile(r"^OPP-\d{3}$")

STATUSES = ("draft", "approved", "rejected")
TERMINAL_STATUSES = ("approved", "rejected")   # a reviewed set is immutable

# bounded sizes — oversize input is rejected, never silently truncated
TEXT_MAX = 4000
SHORT_MAX = 200
LIST_MAX = 20
QUESTIONS_MAX = 40


class QuestionStoreError(Exception):
    """Safe, structured store error — `status` maps to an HTTP status; the
    message never contains SQL, paths, or model output."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _validate_id(value, pattern, label):
    if not isinstance(value, str) or not pattern.match(value):
        raise QuestionStoreError(f"invalid {label}", status=400)
    return value


def _bounded_question(q, idx):
    """Structural bounds only — taxonomy conformance is enforced upstream by the
    generator against Merchant Voice's validator before it reaches the store."""
    if not isinstance(q, dict):
        raise QuestionStoreError(f"question[{idx}] must be an object")
    text = q.get("text")
    if not isinstance(text, str) or not text.strip():
        raise QuestionStoreError(f"question[{idx}].text is required")
    if len(text) > TEXT_MAX:
        raise QuestionStoreError(f"question[{idx}].text exceeds {TEXT_MAX} characters")
    follow_ups = q.get("follow_up_prompts") or []
    if not isinstance(follow_ups, list) or len(follow_ups) > LIST_MAX or \
            not all(isinstance(f, str) and len(f) <= SHORT_MAX for f in follow_ups):
        raise QuestionStoreError(f"question[{idx}].follow_up_prompts invalid")
    signals = q.get("signals") or []
    if not isinstance(signals, list) or not all(isinstance(s, str) for s in signals):
        raise QuestionStoreError(f"question[{idx}].signals must be a list of strings")
    return {
        "text": text.strip(),
        "purpose": q.get("purpose"),
        "question_type": q.get("question_type"),
        "follow_up_prompts": [f.strip() for f in follow_ups],
        "linked_assumption": q.get("linked_assumption"),
        "linked_hypothesis": q.get("linked_hypothesis"),
        "signals": list(signals),
        "source_weak_link_rank": q.get("source_weak_link_rank"),
    }


class QuestionSetStore:
    """SQLite-backed store of draft question sets. One short-lived connection per
    op; every write is a transaction."""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path
                            or os.environ.get("QUESTION_SETS_DB_PATH")
                            or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self):
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            version = int(row["value"]) if row else 0
            if version > SCHEMA_VERSION:
                raise QuestionStoreError("question-sets database is newer than this code", status=500)
            if version < 1:
                self._migrate_to_v1(conn)
            if version < 2:
                self._migrate_to_v2(conn)
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                         (str(SCHEMA_VERSION),))

    @staticmethod
    def _migrate_to_v1(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS question_sets (
            id TEXT PRIMARY KEY,
            opportunity_id TEXT NOT NULL,
            status TEXT NOT NULL,
            questions TEXT NOT NULL,
            provenance TEXT,
            rejected_count INTEGER NOT NULL DEFAULT 0,
            note TEXT,
            owner_user_id TEXT,
            created_at TEXT NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qset_owner ON question_sets(owner_user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qset_opp ON question_sets(opportunity_id)")

    @staticmethod
    def _migrate_to_v2(conn):
        # PR10c — human review metadata. draft -> approved|rejected exactly once
        # (the transition/edits live in review(); taxonomy re-validation of any
        # human edits happens UPSTREAM in the route layer, never here — the store
        # never imports Merchant Voice). Idempotent (PRAGMA-guarded).
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(question_sets)")}
        for col in ("reviewed_at", "reviewer", "review_note"):
            if col not in existing:
                conn.execute(f"ALTER TABLE question_sets ADD COLUMN {col} TEXT")

    @staticmethod
    def _row_dict(row):
        d = dict(row)
        d["questions"] = json.loads(d["questions"])
        d["provenance"] = json.loads(d["provenance"]) if d.get("provenance") else None
        return d

    def create(self, opportunity_id, questions, *, provenance=None, rejected_count=0,
               note=None, owner_user_id=None):
        _validate_id(opportunity_id, OPP_RE, "opportunity id")
        if not isinstance(questions, list):
            raise QuestionStoreError("questions must be a list")
        if len(questions) > QUESTIONS_MAX:
            raise QuestionStoreError(f"too many questions (max {QUESTIONS_MAX})")
        set_id = _new_id("RQSET")
        bounded = []
        for i, q in enumerate(questions):
            item = _bounded_question(q, i)
            item["question_id"] = f"{set_id}-Q{i + 1}"
            bounded.append(item)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO question_sets
                   (id, opportunity_id, status, questions, provenance, rejected_count,
                    note, owner_user_id, created_at)
                   VALUES (?,?,'draft',?,?,?,?,?,?)""",
                (set_id, opportunity_id, json.dumps(bounded),
                 json.dumps(provenance) if provenance is not None else None,
                 int(rejected_count), note, owner_user_id, now))
        return self.get(set_id, visible_to=owner_user_id)

    def get(self, set_id, visible_to=None):
        _validate_id(set_id, RQSET_RE, "question-set id")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM question_sets WHERE id=?", (set_id,)).fetchone()
        if row is None or not _owner_visible(row["owner_user_id"], visible_to):
            raise QuestionStoreError("question set not found", status=404)
        return self._row_dict(row)

    def list(self, opportunity_id=None, visible_to=None, limit=100):
        if opportunity_id is not None and not OPP_RE.match(str(opportunity_id)):
            raise QuestionStoreError("invalid opportunity_id filter")
        limit = max(1, min(int(limit), 500))
        clauses, params = [], []
        if opportunity_id:
            clauses.append("opportunity_id=?")
            params.append(opportunity_id)
        if visible_to is not None:
            clauses.append("(owner_user_id IS NULL OR owner_user_id=?)")
            params.append(visible_to)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM question_sets {where} ORDER BY created_at DESC, id LIMIT ?",
                (*params, limit)).fetchall()
        return [self._row_dict(r) for r in rows]

    def review(self, set_id, action, *, questions=None, reviewer=None, note=None,
               visible_to=None):
        """Human review (PR10c): draft -> approved | rejected, EXACTLY once.

        On approve, `questions` may carry the reviewer's edited set, which
        REPLACES the draft's questions (re-bounded + re-ided here). Structural
        bounds only — taxonomy conformance of edits is enforced UPSTREAM by the
        route layer against Merchant Voice's validator before this is called
        (D1: the store never imports Merchant Voice). Approval is NOT a write to
        the KB or Merchant Voice and never mints an EV id — it only marks the
        set usable for a human to hand off into MV's own review flow (D3)."""
        _validate_id(set_id, RQSET_RE, "question-set id")
        if action not in ("approve", "reject"):
            raise QuestionStoreError("action must be 'approve' or 'reject'")
        if note is not None and (not isinstance(note, str) or len(note) > TEXT_MAX):
            raise QuestionStoreError("'note' must be a bounded string")
        if reviewer is not None and (not isinstance(reviewer, str) or len(reviewer) > SHORT_MAX):
            raise QuestionStoreError("'reviewer' must be a bounded string")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM question_sets WHERE id=?", (set_id,)).fetchone()
            if row is None or not _owner_visible(row["owner_user_id"], visible_to):
                raise QuestionStoreError("question set not found", status=404)
            if row["status"] in TERMINAL_STATUSES:
                raise QuestionStoreError(
                    f"question set already reviewed ('{row['status']}')", status=409)
            status = "approved" if action == "approve" else "rejected"
            questions_json = row["questions"]
            if questions is not None:
                if not isinstance(questions, list):
                    raise QuestionStoreError("questions must be a list")
                if len(questions) > QUESTIONS_MAX:
                    raise QuestionStoreError(f"too many questions (max {QUESTIONS_MAX})")
                bounded = []
                for i, q in enumerate(questions):
                    item = _bounded_question(q, i)
                    item["question_id"] = f"{set_id}-Q{i + 1}"
                    bounded.append(item)
                questions_json = json.dumps(bounded)
            conn.execute(
                """UPDATE question_sets
                   SET status=?, questions=?, reviewed_at=?, reviewer=?, review_note=?
                   WHERE id=?""",
                (status, questions_json, _now(), reviewer, note, set_id))
        return self.get(set_id, visible_to=visible_to)

    def delete(self, set_id, visible_to=None):
        """Owner-scoped hard delete of a draft/reviewed set (a proposal is
        disposable). A foreign or absent set answers an indistinguishable 404."""
        _validate_id(set_id, RQSET_RE, "question-set id")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT owner_user_id FROM question_sets WHERE id=?", (set_id,)).fetchone()
            if row is None or not _owner_visible(row["owner_user_id"], visible_to):
                raise QuestionStoreError("question set not found", status=404)
            conn.execute("DELETE FROM question_sets WHERE id=?", (set_id,))
        return {"id": set_id, "deleted": True}


def _owner_visible(row_owner, viewer):
    if viewer is None:
        return True
    return row_owner is None or row_owner == viewer
