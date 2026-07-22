"""Runtime persistence for candidate market-sizing results (Phase C2, PR2).

Mirrors shared/questions/store.py and shared/research/store.py:

- Committed KB stays READ-ONLY. Candidate sizings live in a runtime SQLite DB,
  default `runtime/market-sizing.db`, overridable via MARKET_SIZING_DB_PATH.
- A sizing is a **candidate**: `status` starts `pending_review`; a human
  approves or rejects it EXACTLY once (409 if already reviewed). Approval never
  writes committed scores or the KB — that stays the `impact` CLI (`--approver`).
- Ownership (R8b): new rows carry their creator's `USER-` id; pre-auth / no-auth
  rows keep a NULL owner and stay visible to every signed-in user; a foreign row
  answers an indistinguishable 404.
- ID namespace: MSZ-<12 hex>. Cannot collide with any other namespace.

This store persists a sizing envelope composed elsewhere
(executive-ui/api/market_sizing_builder.py); it never computes, corroborates,
or calls a model.
"""

import json
import os
import re
import sqlite3
import uuid
import datetime
from pathlib import Path

SCHEMA_VERSION = 1

REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO / "runtime" / "market-sizing.db"

MSZ_RE = re.compile(r"^MSZ-[0-9a-f]{12}$")
OPP_RE = re.compile(r"^OPP-\d{3}$")

STATUSES = ("pending_review", "approved", "rejected")
TERMINAL_STATUSES = ("approved", "rejected")

TEXT_MAX = 4000
SHORT_MAX = 200


class MarketSizingStoreError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _validate_id(value, pattern, label):
    if not isinstance(value, str) or not pattern.match(value):
        raise MarketSizingStoreError(f"invalid {label}", status=400)
    return value


class MarketSizingStore:
    def __init__(self, db_path=None):
        self.db_path = Path(db_path or os.environ.get("MARKET_SIZING_DB_PATH") or DEFAULT_DB_PATH)
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
                raise MarketSizingStoreError("market-sizing database is newer than this code", status=500)
            if version < 1:
                self._migrate_to_v1(conn)
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                         (str(SCHEMA_VERSION),))

    @staticmethod
    def _migrate_to_v1(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS market_sizings (
            id TEXT PRIMARY KEY,
            opportunity_id TEXT NOT NULL,
            status TEXT NOT NULL,
            calculator TEXT NOT NULL,
            run_id TEXT,
            confidence TEXT NOT NULL,
            sizing TEXT NOT NULL,
            reviewed_at TEXT,
            reviewer TEXT,
            review_note TEXT,
            owner_user_id TEXT,
            created_at TEXT NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_msz_owner ON market_sizings(owner_user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_msz_opp ON market_sizings(opportunity_id)")

    @staticmethod
    def _row_dict(row):
        d = dict(row)
        d["sizing"] = json.loads(d["sizing"])
        return d

    def create(self, opportunity_id, *, calculator, confidence, sizing, run_id=None,
               owner_user_id=None):
        _validate_id(opportunity_id, OPP_RE, "opportunity id")
        if not isinstance(calculator, str) or not calculator:
            raise MarketSizingStoreError("'calculator' is required")
        if confidence not in ("verified", "low_confidence"):
            raise MarketSizingStoreError("'confidence' must be 'verified' or 'low_confidence'")
        if not isinstance(sizing, dict):
            raise MarketSizingStoreError("'sizing' must be an object")
        msz_id = _new_id("MSZ")
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO market_sizings
                   (id, opportunity_id, status, calculator, run_id, confidence,
                    sizing, owner_user_id, created_at)
                   VALUES (?,?,'pending_review',?,?,?,?,?,?)""",
                (msz_id, opportunity_id, calculator, run_id, confidence,
                 json.dumps(sizing), owner_user_id, now))
        return self.get(msz_id, visible_to=owner_user_id)

    def review(self, msz_id, action, *, reviewer=None, note=None, owner_user_id=None):
        """draft-equivalent `pending_review` -> approved | rejected, EXACTLY once
        (409 if already reviewed). Approval does NOT write the KB or a score."""
        _validate_id(msz_id, MSZ_RE, "market-sizing id")
        if action not in ("approve", "reject"):
            raise MarketSizingStoreError("action must be 'approve' or 'reject'")
        if note is not None and (not isinstance(note, str) or len(note) > TEXT_MAX):
            raise MarketSizingStoreError("'note' must be a bounded string")
        if reviewer is not None and (not isinstance(reviewer, str) or len(reviewer) > SHORT_MAX):
            raise MarketSizingStoreError("'reviewer' must be a bounded string")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM market_sizings WHERE id=?", (msz_id,)).fetchone()
            if row is None or not _owner_visible(row["owner_user_id"], owner_user_id):
                raise MarketSizingStoreError("market sizing not found", status=404)
            if row["status"] in TERMINAL_STATUSES:
                raise MarketSizingStoreError(
                    f"market sizing already reviewed ('{row['status']}')", status=409)
            status = "approved" if action == "approve" else "rejected"
            conn.execute(
                "UPDATE market_sizings SET status=?, reviewed_at=?, reviewer=?, review_note=? WHERE id=?",
                (status, _now(), reviewer, note, msz_id))
        return self.get(msz_id, visible_to=owner_user_id)

    def get(self, msz_id, visible_to=None):
        _validate_id(msz_id, MSZ_RE, "market-sizing id")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM market_sizings WHERE id=?", (msz_id,)).fetchone()
        if row is None or not _owner_visible(row["owner_user_id"], visible_to):
            raise MarketSizingStoreError("market sizing not found", status=404)
        return self._row_dict(row)

    def list(self, opportunity_id=None, visible_to=None, limit=100):
        if opportunity_id is not None and not OPP_RE.match(str(opportunity_id)):
            raise MarketSizingStoreError("invalid opportunity_id filter")
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
                f"SELECT * FROM market_sizings {where} ORDER BY created_at DESC, id LIMIT ?",
                (*params, limit)).fetchall()
        return [self._row_dict(r) for r in rows]


def _owner_visible(row_owner, viewer):
    if viewer is None:
        return True
    return row_owner is None or row_owner == viewer
