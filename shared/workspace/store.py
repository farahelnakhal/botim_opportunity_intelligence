"""Runtime persistence for versioned analysis workspaces (Phase R5, PR4).

Design (see docs/decision-log.md, 2026-07-16 "Versioned preliminary analysis
workspace per saved chat"):

- Versions are APPEND-ONLY: a refresh creates a new version; existing
  versions are never mutated after they finish. Readers take the latest
  `complete` version, so a concurrent build can never corrupt what chat is
  reading.
- A version records WHAT the chain produced (kb_evidence, claim_ids,
  preliminary_score, gaps) and per-version provenance (question, trigger,
  research run id, models/providers involved). Claims themselves — and their
  human review state — live in the research store (`RCAND-`); approvals
  attach to claims, never to versions, so an approval survives a refresh.
- Lifecycle: running -> complete | failed. `failed` requires an honest
  reason; `complete` must not carry one. Terminal states are immutable.
- Everything here is machine-generated PRELIMINARY analysis: never
  authoritative knowledge, never written to knowledge-base/.
- Storage: runtime SQLite (gitignored) at WORKSPACE_DB_PATH, default
  `runtime/workspace.db`. IDs use the AWV- namespace (`AWV-<12 hex>`),
  which cannot collide with any other namespace in the system.
- Retention: prune keeps the newest N versions per opportunity (default
  10). Approved claims are unaffected by pruning — they live in the
  research store.
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
DEFAULT_DB_PATH = REPO / "runtime" / "workspace.db"

AWV_RE = re.compile(r"^AWV-[0-9a-f]{12}$")
# a workspace belongs to a user opportunity (UOPP-) or, in principle, a
# committed one (OPP-nnn) — nothing else
OPP_REF_RE = re.compile(r"^(OPP-\d{3}|UOPP-[0-9a-f]{12})$")

STATUSES = ("running", "complete", "failed")
# the concrete trigger set locked in the decision log — an ordinary chat
# message is deliberately NOT a trigger (follow-ups reuse the latest version)
TRIGGERS = ("first_analysis", "manual_refresh", "meaningful_change",
            "stale", "monitoring")

QUESTION_MAX = 4000
ERROR_MAX = 1000
DEFAULT_KEEP = 10
DEFAULT_STALE_HOURS = 24

_JSON_LIST_FIELDS = ("kb_evidence", "claim_ids", "gaps", "document_evidence")
_JSON_DICT_FIELDS = ("preliminary_score", "provenance")


class WorkspaceStoreError(Exception):
    """Safe, structured store error — `status` maps to the HTTP status; the
    message never contains SQL or paths."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id():
    return f"AWV-{uuid.uuid4().hex[:12]}"


def _validate_opp_ref(opportunity_id):
    if not isinstance(opportunity_id, str) or not OPP_REF_RE.match(opportunity_id):
        raise WorkspaceStoreError("invalid opportunity reference "
                                  "(expected OPP-nnn or UOPP-<12 hex>)")
    return opportunity_id


def _validate_awv_id(version_id):
    if not isinstance(version_id, str) or not AWV_RE.match(version_id):
        raise WorkspaceStoreError("invalid workspace version id")
    return version_id


class WorkspaceStore:
    """SQLite-backed store. One short-lived connection per operation (safe
    under the threading HTTP server); every write is a transaction."""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path
                            or os.environ.get("WORKSPACE_DB_PATH")
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
                raise WorkspaceStoreError("workspace database is newer than this code",
                                          status=500)
            if version < 1:
                conn.execute("""CREATE TABLE IF NOT EXISTS workspace_versions (
                    id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running','complete','failed')),
                    trigger TEXT NOT NULL
                        CHECK (trigger IN ('first_analysis','manual_refresh',
                                           'meaningful_change','stale','monitoring')),
                    question TEXT,
                    error TEXT,
                    research_run_id TEXT,
                    kb_evidence TEXT NOT NULL DEFAULT '[]',
                    claim_ids TEXT NOT NULL DEFAULT '[]',
                    preliminary_score TEXT,
                    gaps TEXT NOT NULL DEFAULT '[]',
                    provenance TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE (opportunity_id, version))""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_awv_opp "
                             "ON workspace_versions(opportunity_id, version)")
            if version < 2:
                # Phase R7 — verbatim excerpts from the user's uploaded
                # documents that grounded this version (snapshot: kept even
                # if the document is later deleted). Idempotent PRAGMA guard.
                existing = {row["name"] for row in
                            conn.execute("PRAGMA table_info(workspace_versions)")}
                if "document_evidence" not in existing:
                    conn.execute("ALTER TABLE workspace_versions "
                                 "ADD COLUMN document_evidence TEXT NOT NULL DEFAULT '[]'")
            conn.execute("INSERT OR REPLACE INTO meta (key, value) "
                         "VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))

    # -- serialization ------------------------------------------------------ #

    @staticmethod
    def _dict(row):
        d = dict(row)
        for key in _JSON_LIST_FIELDS:
            d[key] = json.loads(d.get(key) or "[]")
        for key in _JSON_DICT_FIELDS:
            d[key] = json.loads(d[key]) if d.get(key) else None
        return d

    # -- lifecycle ----------------------------------------------------------- #

    def create_version(self, opportunity_id, trigger, question=None):
        """Open a new `running` version. Version numbers increment per
        opportunity inside the same transaction (append-only concurrency:
        two simultaneous builds get distinct version numbers; readers only
        ever see `complete` versions)."""
        _validate_opp_ref(opportunity_id)
        if trigger not in TRIGGERS:
            raise WorkspaceStoreError(f"trigger must be one of {list(TRIGGERS)}")
        if question is not None:
            if not isinstance(question, str):
                raise WorkspaceStoreError("'question' must be a string")
            if len(question) > QUESTION_MAX:
                raise WorkspaceStoreError(f"'question' exceeds the {QUESTION_MAX}-character limit")
            question = question.strip() or None
        version_id = _new_id()
        now = _now()
        with self._connect() as conn:
            # retry once on a concurrent (opportunity_id, version) collision
            for attempt in (1, 2):
                row = conn.execute(
                    "SELECT COALESCE(MAX(version), 0) AS v FROM workspace_versions "
                    "WHERE opportunity_id=?", (opportunity_id,)).fetchone()
                try:
                    conn.execute(
                        """INSERT INTO workspace_versions
                           (id, opportunity_id, version, status, trigger, question, created_at)
                           VALUES (?,?,?,'running',?,?,?)""",
                        (version_id, opportunity_id, row["v"] + 1, trigger, question, now))
                    break
                except sqlite3.IntegrityError:
                    if attempt == 2:
                        raise WorkspaceStoreError(
                            "could not allocate a workspace version (concurrent builds)",
                            status=409)
        return self.get_version(version_id)

    def _terminal_guard(self, conn, version_id):
        row = conn.execute("SELECT status FROM workspace_versions WHERE id=?",
                           (version_id,)).fetchone()
        if row is None:
            raise WorkspaceStoreError("workspace version not found", status=404)
        if row["status"] != "running":
            raise WorkspaceStoreError(
                f"version is already terminal ({row['status']}) — versions are immutable",
                status=409)

    def complete_version(self, version_id, *, kb_evidence=None, claim_ids=None,
                         preliminary_score=None, gaps=None, provenance=None,
                         research_run_id=None, document_evidence=None):
        """Finish a running version as `complete` with the chain's outputs.
        Empty outputs are honest (they show up as gaps), never invented."""
        _validate_awv_id(version_id)
        for name, value in (("kb_evidence", kb_evidence), ("claim_ids", claim_ids),
                            ("gaps", gaps), ("document_evidence", document_evidence)):
            if value is not None and not isinstance(value, list):
                raise WorkspaceStoreError(f"'{name}' must be a list")
        for name, value in (("preliminary_score", preliminary_score),
                            ("provenance", provenance)):
            if value is not None and not isinstance(value, dict):
                raise WorkspaceStoreError(f"'{name}' must be an object")
        with self._connect() as conn:
            self._terminal_guard(conn, version_id)
            conn.execute(
                """UPDATE workspace_versions SET status='complete', error=NULL,
                   kb_evidence=?, claim_ids=?, preliminary_score=?, gaps=?,
                   provenance=?, research_run_id=?, document_evidence=?,
                   completed_at=? WHERE id=?""",
                (json.dumps(kb_evidence or []), json.dumps(claim_ids or []),
                 json.dumps(preliminary_score) if preliminary_score else None,
                 json.dumps(gaps or []),
                 json.dumps(provenance) if provenance else None,
                 research_run_id, json.dumps(document_evidence or []),
                 _now(), version_id))
        return self.get_version(version_id)

    def fail_version(self, version_id, error):
        """Finish a running version as `failed` with a mandatory reason."""
        _validate_awv_id(version_id)
        if not isinstance(error, str) or not error.strip():
            raise WorkspaceStoreError("a failed version requires an honest reason")
        with self._connect() as conn:
            self._terminal_guard(conn, version_id)
            conn.execute(
                "UPDATE workspace_versions SET status='failed', error=?, completed_at=? "
                "WHERE id=?", (error.strip()[:ERROR_MAX], _now(), version_id))
        return self.get_version(version_id)

    # -- reads --------------------------------------------------------------- #

    def get_version(self, version_id):
        _validate_awv_id(version_id)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM workspace_versions WHERE id=?",
                               (version_id,)).fetchone()
        if row is None:
            raise WorkspaceStoreError("workspace version not found", status=404)
        return self._dict(row)

    def latest(self, opportunity_id, status="complete"):
        """The newest version with the given status (readers want 'complete').
        None when no such version exists — an honest empty state."""
        _validate_opp_ref(opportunity_id)
        if status not in STATUSES:
            raise WorkspaceStoreError(f"status must be one of {list(STATUSES)}")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workspace_versions WHERE opportunity_id=? AND status=? "
                "ORDER BY version DESC LIMIT 1", (opportunity_id, status)).fetchone()
        return self._dict(row) if row else None

    def list_versions(self, opportunity_id, limit=50):
        """Version summaries (no bulky JSON payloads), newest first."""
        _validate_opp_ref(opportunity_id)
        limit = max(1, min(int(limit), 200))
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, opportunity_id, version, status, trigger, question,
                          error, research_run_id, created_at, completed_at
                   FROM workspace_versions WHERE opportunity_id=?
                   ORDER BY version DESC LIMIT ?""", (opportunity_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def is_stale(self, version, stale_hours=None):
        """Deterministic staleness from the version's completion time.
        Threshold from WORKSPACE_STALE_HOURS (default 24h). A version with no
        completion time is honestly treated as stale (it never finished)."""
        if stale_hours is None:
            try:
                stale_hours = int(os.environ.get("WORKSPACE_STALE_HOURS",
                                                 DEFAULT_STALE_HOURS))
            except ValueError:
                stale_hours = DEFAULT_STALE_HOURS
        completed = version.get("completed_at")
        if not completed:
            return True
        try:
            done = datetime.datetime.strptime(completed, "%Y-%m-%dT%H:%M:%SZ") \
                .replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            return True
        age = datetime.datetime.now(datetime.timezone.utc) - done
        return age.total_seconds() > stale_hours * 3600

    # -- retention ------------------------------------------------------------ #

    def prune(self, opportunity_id, keep=DEFAULT_KEEP):
        """Delete all but the newest `keep` versions for an opportunity.
        Claims (and their approvals) live in the research store and are
        untouched. Returns the number of versions removed."""
        _validate_opp_ref(opportunity_id)
        keep = max(1, int(keep))
        with self._connect() as conn:
            cur = conn.execute(
                """DELETE FROM workspace_versions WHERE opportunity_id=? AND id NOT IN
                   (SELECT id FROM workspace_versions WHERE opportunity_id=?
                    ORDER BY version DESC LIMIT ?)""",
                (opportunity_id, opportunity_id, keep))
        return cur.rowcount


def compare_versions(older, newer):
    """Deterministic version diff — the seed for R6 change notifications.
    Pure data comparison: composite delta from the stored engine outputs and
    claim/gap set differences. Nothing is interpreted or scored here."""
    def _composite(v):
        score = v.get("preliminary_score") or {}
        return score.get("composite")

    old_claims = set(older.get("claim_ids") or [])
    new_claims = set(newer.get("claim_ids") or [])
    old_gaps = set(older.get("gaps") or [])
    new_gaps = set(newer.get("gaps") or [])
    old_c, new_c = _composite(older), _composite(newer)
    return {
        "older_id": older.get("id"), "newer_id": newer.get("id"),
        "composite_before": old_c, "composite_after": new_c,
        "composite_delta": (round(new_c - old_c, 2)
                            if isinstance(old_c, (int, float)) and isinstance(new_c, (int, float))
                            else None),
        "new_claim_ids": sorted(new_claims - old_claims),
        "removed_claim_ids": sorted(old_claims - new_claims),
        "new_gaps": sorted(new_gaps - old_gaps),
        "resolved_gaps": sorted(old_gaps - new_gaps),
    }
