"""Runtime persistence for saved calculations (Phase C1).

Mirrors shared/research/store.py (the established runtime-store pattern):

- The committed Git knowledge base stays READ-ONLY. Saved calculations live in a
  separate runtime SQLite database, by default `runtime/calculators.db` under the
  repo root, overridable via CALCULATORS_DB_PATH. The runtime directory is
  gitignored — never committed.
- Schema is versioned (meta table); foreign keys on; statements parameterized;
  timestamps UTC ISO-8601.
- A saved row stores the FULL result envelope PLUS `calculator_version` and the
  normalized inputs, so any saved result is re-derivable/verifiable against the
  formula that produced it — a stored number can never quietly drift from code.
- Ownership (R8b pattern): new rows carry their creator's `USER-` id; pre-auth /
  no-auth rows keep a NULL owner and stay visible to every signed-in user (legacy
  shared). A foreign row answers an indistinguishable 404.
- ID namespace: CALC-<12 hex> (cannot collide with OPP-/UOPP-/RRUN-/RQRY-/RSRC-/
  RCAND-/RREV-/AWV-/WSUB-/MCFG-/MEVT-/DOC-/USER- ids).

This store never computes: it persists an envelope produced by the pure engine.
"""

import json
import os
import re
import sqlite3
import uuid
import datetime
from pathlib import Path

from .base import CalculatorError

SCHEMA_VERSION = 1

REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO / "runtime" / "calculators.db"

CALC_RE = re.compile(r"^CALC-[0-9a-f]{12}$")
OPP_REF_RE = re.compile(r"^(OPP-\d{3}|UOPP-[0-9a-f]{12})$")

LABEL_MAX = 200
LIST_LIMIT_MAX = 500


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _validate_id(value, pattern, label):
    if not isinstance(value, str) or not pattern.match(value):
        raise CalculatorError(f"invalid {label}", status=400)
    return value


class CalculatorStore:
    """SQLite-backed store of saved calculations. One short-lived connection per
    op (safe under a threading HTTP server); every write is a transaction."""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path
                            or os.environ.get("CALCULATORS_DB_PATH")
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
                raise CalculatorError("calculators database is newer than this code", status=500)
            if version < 1:
                self._migrate_to_v1(conn)
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                         (str(SCHEMA_VERSION),))

    @staticmethod
    def _migrate_to_v1(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS saved_calculations (
            id TEXT PRIMARY KEY,
            calculator TEXT NOT NULL,
            calculator_version INTEGER NOT NULL,
            title TEXT,
            label TEXT,
            opportunity_ref TEXT,
            owner_user_id TEXT,
            envelope TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_calc_owner ON saved_calculations(owner_user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_calc_opp ON saved_calculations(opportunity_ref)")

    # -- serialization ----------------------------------------------------- #

    @staticmethod
    def _row_dict(row):
        d = dict(row)
        d["envelope"] = json.loads(d["envelope"])
        return d

    # -- writes ------------------------------------------------------------ #

    def save(self, envelope, opportunity_ref=None, label=None, owner_user_id=None):
        """Persist a pure-engine envelope. `envelope` must carry calculator_id +
        calculator_version (the store never computes)."""
        if not isinstance(envelope, dict):
            raise CalculatorError("envelope must be an object")
        calc_id = envelope.get("calculator_id")
        version = envelope.get("calculator_version")
        if not isinstance(calc_id, str) or not calc_id:
            raise CalculatorError("envelope missing calculator_id")
        if not isinstance(version, int):
            raise CalculatorError("envelope missing calculator_version")
        if opportunity_ref is not None:
            if not isinstance(opportunity_ref, str) or not OPP_REF_RE.match(opportunity_ref):
                raise CalculatorError("'opportunity_ref' must be an OPP-nnn or UOPP- id")
        if label is not None:
            if not isinstance(label, str):
                raise CalculatorError("'label' must be a string")
            label = label.strip()[:LABEL_MAX] or None
        calc_row_id = _new_id("CALC")
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO saved_calculations
                   (id, calculator, calculator_version, title, label,
                    opportunity_ref, owner_user_id, envelope, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (calc_row_id, calc_id, version, envelope.get("title"), label,
                 opportunity_ref, owner_user_id, json.dumps(envelope), now))
        return self.get(calc_row_id, visible_to=owner_user_id)

    def delete(self, calc_id, owner_user_id=None):
        _validate_id(calc_id, CALC_RE, "calculation id")
        with self._connect() as conn:
            # owner-guard: fetch first so a foreign row is an indistinguishable 404
            row = conn.execute("SELECT owner_user_id FROM saved_calculations WHERE id=?",
                               (calc_id,)).fetchone()
            if row is None or not _owner_visible(row["owner_user_id"], owner_user_id):
                raise CalculatorError("calculation not found", status=404)
            conn.execute("DELETE FROM saved_calculations WHERE id=?", (calc_id,))
        return {"deleted": calc_id}

    # -- reads ------------------------------------------------------------- #

    def get(self, calc_id, visible_to=None):
        _validate_id(calc_id, CALC_RE, "calculation id")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM saved_calculations WHERE id=?", (calc_id,)).fetchone()
        if row is None or not _owner_visible(row["owner_user_id"], visible_to):
            raise CalculatorError("calculation not found", status=404)
        return self._row_dict(row)

    def list(self, opportunity_ref=None, visible_to=None, limit=100):
        if opportunity_ref is not None and not OPP_REF_RE.match(str(opportunity_ref)):
            raise CalculatorError("invalid opportunity_ref filter")
        limit = max(1, min(int(limit), LIST_LIMIT_MAX))
        clauses, params = [], []
        if opportunity_ref:
            clauses.append("opportunity_ref=?")
            params.append(opportunity_ref)
        if visible_to is not None:
            clauses.append("(owner_user_id IS NULL OR owner_user_id=?)")
            params.append(visible_to)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM saved_calculations {where} ORDER BY created_at DESC, id LIMIT ?",
                (*params, limit)).fetchall()
        return [self._row_dict(r) for r in rows]


def _owner_visible(row_owner, viewer):
    """A row is visible if it is legacy-shared (NULL owner) or owned by the
    viewer. When viewer is None (auth off), everything is visible."""
    if viewer is None:
        return True
    return row_owner is None or row_owner == viewer
