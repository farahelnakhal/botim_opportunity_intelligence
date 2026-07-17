"""Runtime persistence for external-research runs (Phase R1).

Design (mirrors executive-ui/api/user_store.py, the established runtime-store
pattern in this repository):

- The committed Git knowledge base stays READ-ONLY. Research output lives in
  a separate runtime SQLite database, by default `runtime/research.db` under
  the repository root, overridable via the RESEARCH_DB_PATH environment
  variable. The runtime directory is gitignored — never committed.
- Schema is versioned (meta table, SCHEMA_VERSION below); initialized on
  first use; future migrations run per-version inside a transaction.
- Foreign keys are enabled per connection; every statement is parameterized.
- Timestamps are UTC ISO-8601 (seconds precision, trailing Z).
- **No fabrication:** absent metadata stays NULL — this layer never invents
  publishers, dates, authors, quality signals, or result counts. Source URLs
  must pass shared.source_urls.safe_url (absolute http(s) only).
- **Traceability:** candidate evidence -> source ids -> query -> run. A
  candidate may only cite sources recorded in the same run; a source may
  only reference a query of the same run.
- **Candidate boundary:** nothing here writes the knowledge base, mints EV
  ids, or promotes anything. `candidate_evidence.status` starts at
  `pending_review`; approval semantics arrive with the review workflow (R3)
  and even "approved" here will never mean authoritative Part A evidence.
- ID namespaces (cannot collide with committed KB ids or UOPP-/MCFG-):
  runs RRUN-<12 hex>, queries RQRY-<12 hex>, sources RSRC-<12 hex>,
  candidates RCAND-<12 hex>.

Run lifecycle (the `status` field IS the lifecycle):

    pending -> running -> complete | partial | failed
    pending -> failed            (setup failure before any execution)

`partial` is an honest first-class outcome: some queries/sources succeeded
and are kept, some failed and say so. Terminal states are immutable.
"""

import json
import os
import re
import sqlite3
import uuid
import datetime
from pathlib import Path

try:
    from shared.source_urls import safe_url
except ImportError:  # imported with repo root not on sys.path (e.g. as shared.research from elsewhere)
    from ..source_urls import safe_url

SCHEMA_VERSION = 4

REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO / "runtime" / "research.db"

RUN_RE = re.compile(r"^RRUN-[0-9a-f]{12}$")
QUERY_RE = re.compile(r"^RQRY-[0-9a-f]{12}$")
SOURCE_RE = re.compile(r"^RSRC-[0-9a-f]{12}$")
CANDIDATE_RE = re.compile(r"^RCAND-[0-9a-f]{12}$")
REVALIDATION_OUTCOMES = ("unchanged", "changed", "unreachable")
# a run may optionally be linked to a committed or user opportunity
OPP_REF_RE = re.compile(r"^(OPP-\d{3}|UOPP-[0-9a-f]{12})$")

RUN_STATUSES = ("pending", "running", "partial", "complete", "failed")
TERMINAL_RUN_STATUSES = ("partial", "complete", "failed")
QUERY_STATUSES = ("pending", "executed", "failed")
CANDIDATE_STATUSES = ("pending_review", "approved", "rejected")

# bounded sizes — oversize input is rejected, never silently truncated
TITLE_MAX = 200
SHORT_MAX = 120
TEXT_MAX = 4000
EXCERPT_MAX = 2000
URL_MAX = 2000
ERROR_MAX = 1000
LIST_MAX_ITEMS = 50
LIST_ITEM_MAX = 500
QUALITY_SIGNALS_MAX = 20
CANDIDATE_SOURCES_MAX = 25


class ResearchStoreError(Exception):
    """Safe, structured store error — `status` maps to an HTTP status; the
    message never contains SQL, paths, or fetched content."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _require_str(payload, key, max_len, required=False):
    value = payload.get(key)
    if value is None or value == "":
        if required:
            raise ResearchStoreError(f"'{key}' is required")
        return None
    if not isinstance(value, str):
        raise ResearchStoreError(f"'{key}' must be a string")
    if len(value) > max_len:
        raise ResearchStoreError(f"'{key}' exceeds the {max_len}-character limit")
    return value.strip() or None


def _require_str_list(payload, key, required=False):
    value = payload.get(key)
    if value is None:
        if required:
            raise ResearchStoreError(f"'{key}' is required")
        return []
    if not isinstance(value, list):
        raise ResearchStoreError(f"'{key}' must be an array of strings")
    if len(value) > LIST_MAX_ITEMS:
        raise ResearchStoreError(f"'{key}' exceeds {LIST_MAX_ITEMS} items")
    out = []
    for item in value:
        if not isinstance(item, str):
            raise ResearchStoreError(f"'{key}' items must be strings")
        if len(item) > LIST_ITEM_MAX:
            raise ResearchStoreError(f"'{key}' items exceed the {LIST_ITEM_MAX}-character limit")
        item = item.strip()
        if item:
            out.append(item)
    if required and not out:
        raise ResearchStoreError(f"'{key}' must contain at least one non-empty item")
    return out


def _require_quality_signals(payload):
    """Flat dict of short-string/number/bool signals — recorded observations
    only (e.g. domain reputation tier, has_publication_date). Never computed
    or invented here."""
    value = payload.get("quality_signals")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ResearchStoreError("'quality_signals' must be an object")
    if len(value) > QUALITY_SIGNALS_MAX:
        raise ResearchStoreError(f"'quality_signals' exceeds {QUALITY_SIGNALS_MAX} entries")
    out = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or len(key) > SHORT_MAX:
            raise ResearchStoreError("'quality_signals' keys must be short strings")
        if isinstance(item, bool) or isinstance(item, (int, float)):
            out[key] = item
        elif isinstance(item, str):
            if len(item) > LIST_ITEM_MAX:
                raise ResearchStoreError("'quality_signals' values exceed the size limit")
            out[key] = item
        else:
            raise ResearchStoreError("'quality_signals' values must be strings, numbers, or booleans")
    return out


def _validate_id(value, pattern, label):
    if not isinstance(value, str) or not pattern.match(value):
        raise ResearchStoreError(f"invalid {label}", status=400)
    return value


class ResearchStore:
    """SQLite-backed store. One short-lived connection per operation (safe
    under a threading HTTP server); every write is a transaction."""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path
                            or os.environ.get("RESEARCH_DB_PATH")
                            or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # -- schema ---------------------------------------------------------- #

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
                raise ResearchStoreError("research database is newer than this code", status=500)
            if version < 1:
                self._migrate_to_v1(conn)
            if version < 2:
                self._migrate_to_v2(conn)
            if version < 3:
                self._migrate_to_v3(conn)
            if version < 4:
                self._migrate_to_v4(conn)
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                         (str(SCHEMA_VERSION),))

    @staticmethod
    def _migrate_to_v1(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS research_runs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            objective TEXT,
            objectives TEXT NOT NULL DEFAULT '[]',
            profile TEXT,
            opportunity_ref TEXT,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','running','partial','complete','failed')),
            error TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS research_queries (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
            objective TEXT,
            query_text TEXT NOT NULL,
            provider TEXT,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','executed','failed')),
            error TEXT,
            result_count INTEGER,
            created_at TEXT NOT NULL,
            executed_at TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS research_sources (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
            query_id TEXT REFERENCES research_queries(id) ON DELETE SET NULL,
            canonical_url TEXT NOT NULL,
            domain TEXT NOT NULL,
            title TEXT,
            publisher TEXT,
            author TEXT,
            published_at TEXT,
            retrieved_at TEXT,
            language TEXT,
            excerpt TEXT,
            content_hash TEXT,
            duplicate_of TEXT REFERENCES research_sources(id) ON DELETE SET NULL,
            quality_signals TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS candidate_evidence (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
            claim TEXT NOT NULL,
            source_ids TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'pending_review'
                CHECK (status IN ('pending_review','approved','rejected')),
            review_note TEXT,
            contradicts TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_queries_run ON research_queries(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sources_run ON research_sources(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_candidates_run ON candidate_evidence(run_id)")

    @staticmethod
    def _migrate_to_v2(conn):
        # Phase R4b — source revalidation history. A revalidation NEVER
        # mutates the original source record (recorded observations stay
        # immutable); each re-check appends a row here. Outcomes:
        #   unchanged   — reachable, content hash matches the stored one
        #   changed     — reachable, content hash differs (or no baseline)
        #   unreachable — fetch failed / non-200 / unsupported type
        conn.execute("""CREATE TABLE IF NOT EXISTS source_revalidations (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES research_sources(id) ON DELETE CASCADE,
            outcome TEXT NOT NULL
                CHECK (outcome IN ('unchanged','changed','unreachable')),
            http_status INTEGER,
            new_content_hash TEXT,
            note TEXT,
            checked_at TEXT NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_revalidations_source "
                     "ON source_revalidations(source_id)")

    @staticmethod
    def _migrate_to_v3(conn):
        # PR3 — provenance for how a candidate claim came to exist:
        #   origin='human'      a person authored it from sources (R3 default)
        #   origin='extracted'  an LLM proposed it and it PASSED source
        #                       verification (exact-substring supporting quote,
        #                       quantitative-claim + universal-quantifier
        #                       guards). Either way it starts pending_review —
        #                       machine origin never shortcuts human approval.
        # extraction_meta (JSON) records the model and the per-source
        # supporting quotes, so a reviewer can see exactly what grounds it.
        # idempotent like the v1/v2 CREATE ... IF NOT EXISTS migrations: only
        # add a column that isn't already present (a DB stamped at an older
        # version may already carry it).
        existing = {row["name"] for row in
                    conn.execute("PRAGMA table_info(candidate_evidence)")}
        if "origin" not in existing:
            conn.execute("ALTER TABLE candidate_evidence "
                         "ADD COLUMN origin TEXT NOT NULL DEFAULT 'human'")
        if "extraction_meta" not in existing:
            conn.execute("ALTER TABLE candidate_evidence ADD COLUMN extraction_meta TEXT")

    # -- serialization ----------------------------------------------------- #

    @staticmethod
    def _run_dict(row, counts=None):
        d = dict(row)
        d["objectives"] = json.loads(d.get("objectives") or "[]")
        if counts is not None:
            d["counts"] = counts
        return d

    @staticmethod
    def _source_dict(row):
        d = dict(row)
        d["quality_signals"] = json.loads(d.get("quality_signals") or "{}")
        return d

    @staticmethod
    def _candidate_dict(row):
        d = dict(row)
        d["source_ids"] = json.loads(d.get("source_ids") or "[]")
        if "extraction_meta" in d:
            d["extraction_meta"] = json.loads(d["extraction_meta"]) if d.get("extraction_meta") else None
        d.setdefault("origin", "human")
        return d

    def _get_run_row(self, conn, run_id):
        _validate_id(run_id, RUN_RE, "research run id")
        row = conn.execute("SELECT * FROM research_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise ResearchStoreError("research run not found", status=404)
        return row

    # -- runs -------------------------------------------------------------- #

    @staticmethod
    def _migrate_to_v4(conn):
        # Phase R8b — per-user ownership of research runs. Pre-auth rows keep
        # a NULL owner and stay visible to every signed-in user (legacy
        # shared); new runs created under required-auth mode carry their
        # creator's USER- id. Idempotent (PRAGMA guard).
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(research_runs)")}
        if "owner_user_id" not in existing:
            conn.execute("ALTER TABLE research_runs ADD COLUMN owner_user_id TEXT")

    def create_run(self, payload, owner_user_id=None):
        if not isinstance(payload, dict):
            raise ResearchStoreError("payload must be an object")
        title = _require_str(payload, "title", TITLE_MAX, required=True)
        objective = _require_str(payload, "objective", TEXT_MAX)
        objectives = _require_str_list(payload, "objectives")
        profile = _require_str(payload, "profile", SHORT_MAX)
        notes = _require_str(payload, "notes", TEXT_MAX)
        opportunity_ref = payload.get("opportunity_ref")
        if opportunity_ref is not None:
            if not isinstance(opportunity_ref, str) or not OPP_REF_RE.match(opportunity_ref):
                raise ResearchStoreError("'opportunity_ref' must be an OPP-nnn or UOPP- id")
        run_id = _new_id("RRUN")
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO research_runs
                   (id, title, objective, objectives, profile, opportunity_ref,
                    status, notes, created_at, updated_at, owner_user_id)
                   VALUES (?,?,?,?,?,?,'pending',?,?,?,?)""",
                (run_id, title, objective, json.dumps(objectives), profile,
                 opportunity_ref, notes, now, now, owner_user_id))
        return self.get_run(run_id)

    def get_run(self, run_id, include_children=False):
        with self._connect() as conn:
            row = self._get_run_row(conn, run_id)
            counts = {
                "queries": conn.execute(
                    "SELECT COUNT(*) FROM research_queries WHERE run_id=?", (run_id,)).fetchone()[0],
                "sources": conn.execute(
                    "SELECT COUNT(*) FROM research_sources WHERE run_id=?", (run_id,)).fetchone()[0],
                "candidates": conn.execute(
                    "SELECT COUNT(*) FROM candidate_evidence WHERE run_id=?", (run_id,)).fetchone()[0],
            }
            result = self._run_dict(row, counts)
            if include_children:
                result["queries"] = [dict(r) for r in conn.execute(
                    "SELECT * FROM research_queries WHERE run_id=? ORDER BY created_at, id",
                    (run_id,))]
                result["sources"] = [self._source_dict(r) for r in conn.execute(
                    "SELECT * FROM research_sources WHERE run_id=? ORDER BY created_at, id",
                    (run_id,))]
                result["candidate_evidence"] = [self._candidate_dict(r) for r in conn.execute(
                    "SELECT * FROM candidate_evidence WHERE run_id=? ORDER BY created_at, id",
                    (run_id,))]
        # Phase R4b — computed at read time, never stored: latest re-check per
        # source and the worst cited-source outcome per candidate.
        if include_children:
            latest = self.latest_revalidations(run_id)
            for source in result["sources"]:
                source["last_revalidation"] = latest.get(source["id"])
            for cand in result["candidate_evidence"]:
                cand["source_health"] = self.source_health(cand, latest)
        return result

    def list_runs(self, status=None, opportunity_ref=None, limit=100, visible_to=None):
        if status is not None and status not in RUN_STATUSES:
            raise ResearchStoreError("unknown run status filter")
        if opportunity_ref is not None and not OPP_REF_RE.match(str(opportunity_ref)):
            raise ResearchStoreError("invalid opportunity_ref filter")
        limit = max(1, min(int(limit), 500))
        clauses, params = [], []
        if status:
            clauses.append("status=?")
            params.append(status)
        if opportunity_ref:
            clauses.append("opportunity_ref=?")
            params.append(opportunity_ref)
        if visible_to is not None:
            # Phase R8b — a user sees their own runs plus legacy shared rows
            clauses.append("(owner_user_id IS NULL OR owner_user_id=?)")
            params.append(visible_to)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM research_runs {where} ORDER BY created_at DESC, id LIMIT ?",
                (*params, limit)).fetchall()
            return [self._run_dict(r) for r in rows]

    def start_run(self, run_id):
        with self._connect() as conn:
            row = self._get_run_row(conn, run_id)
            if row["status"] != "pending":
                raise ResearchStoreError(
                    f"cannot start a run in status '{row['status']}'", status=409)
            now = _now()
            conn.execute(
                "UPDATE research_runs SET status='running', started_at=?, updated_at=? WHERE id=?",
                (now, now, run_id))
        return self.get_run(run_id)

    def finish_run(self, run_id, status, error=None):
        """Terminal transition. `partial` and `failed` require an honest
        `error` explaining what did not happen; `complete` must not carry one."""
        if status not in TERMINAL_RUN_STATUSES:
            raise ResearchStoreError("finish status must be partial, complete, or failed")
        if status in ("partial", "failed"):
            if not isinstance(error, str) or not error.strip():
                raise ResearchStoreError(f"'{status}' requires an error/reason message")
            if len(error) > ERROR_MAX:
                raise ResearchStoreError(f"error message exceeds the {ERROR_MAX}-character limit")
            error = error.strip()
        elif error:
            raise ResearchStoreError("'complete' must not carry an error message")
        with self._connect() as conn:
            row = self._get_run_row(conn, run_id)
            if row["status"] in TERMINAL_RUN_STATUSES:
                raise ResearchStoreError(
                    f"run already finished as '{row['status']}'", status=409)
            if row["status"] == "pending" and status != "failed":
                raise ResearchStoreError(
                    "a run that never started can only finish as 'failed'", status=409)
            now = _now()
            conn.execute(
                """UPDATE research_runs SET status=?, error=?, completed_at=?, updated_at=?
                   WHERE id=?""",
                (status, error, now, now, run_id))
        return self.get_run(run_id)

    # -- queries ------------------------------------------------------------ #

    def add_query(self, run_id, payload):
        if not isinstance(payload, dict):
            raise ResearchStoreError("payload must be an object")
        query_text = _require_str(payload, "query_text", TEXT_MAX, required=True)
        objective = _require_str(payload, "objective", TEXT_MAX)
        provider = _require_str(payload, "provider", SHORT_MAX)
        query_id = _new_id("RQRY")
        now = _now()
        with self._connect() as conn:
            row = self._get_run_row(conn, run_id)
            if row["status"] in TERMINAL_RUN_STATUSES:
                raise ResearchStoreError("cannot add queries to a finished run", status=409)
            conn.execute(
                """INSERT INTO research_queries
                   (id, run_id, objective, query_text, provider, status, created_at)
                   VALUES (?,?,?,?,?,'pending',?)""",
                (query_id, run_id, objective, query_text, provider, now))
            return dict(conn.execute(
                "SELECT * FROM research_queries WHERE id=?", (query_id,)).fetchone())

    def mark_query(self, query_id, status, error=None, result_count=None):
        _validate_id(query_id, QUERY_RE, "research query id")
        if status not in ("executed", "failed"):
            raise ResearchStoreError("query status must be executed or failed")
        if status == "failed":
            if not isinstance(error, str) or not error.strip():
                raise ResearchStoreError("a failed query requires an error message")
            if len(error) > ERROR_MAX:
                raise ResearchStoreError(f"error message exceeds the {ERROR_MAX}-character limit")
            error = error.strip()
        elif error:
            raise ResearchStoreError("an executed query must not carry an error message")
        if result_count is not None:
            if not isinstance(result_count, int) or isinstance(result_count, bool) or result_count < 0:
                raise ResearchStoreError("'result_count' must be a non-negative integer")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM research_queries WHERE id=?", (query_id,)).fetchone()
            if row is None:
                raise ResearchStoreError("research query not found", status=404)
            if row["status"] != "pending":
                raise ResearchStoreError(
                    f"query already marked '{row['status']}'", status=409)
            conn.execute(
                """UPDATE research_queries SET status=?, error=?, result_count=?, executed_at=?
                   WHERE id=?""",
                (status, error, result_count, _now(), query_id))
            return dict(conn.execute(
                "SELECT * FROM research_queries WHERE id=?", (query_id,)).fetchone())

    # -- sources ------------------------------------------------------------ #

    def add_source(self, run_id, payload):
        if not isinstance(payload, dict):
            raise ResearchStoreError("payload must be an object")
        raw_url = payload.get("canonical_url")
        if not isinstance(raw_url, str) or len(raw_url) > URL_MAX:
            raise ResearchStoreError("'canonical_url' is required and must be a bounded string")
        url = safe_url(raw_url)
        if url is None:
            raise ResearchStoreError("'canonical_url' must be an absolute http(s) URL")
        from urllib.parse import urlsplit
        domain = (urlsplit(url).hostname or "").lower()
        title = _require_str(payload, "title", TITLE_MAX)
        publisher = _require_str(payload, "publisher", SHORT_MAX)
        author = _require_str(payload, "author", SHORT_MAX)
        published_at = _require_str(payload, "published_at", SHORT_MAX)
        retrieved_at = _require_str(payload, "retrieved_at", SHORT_MAX)
        language = _require_str(payload, "language", SHORT_MAX)
        excerpt = _require_str(payload, "excerpt", EXCERPT_MAX)
        content_hash = _require_str(payload, "content_hash", SHORT_MAX)
        quality_signals = _require_quality_signals(payload)
        duplicate_of = payload.get("duplicate_of")
        source_id = _new_id("RSRC")
        now = _now()
        with self._connect() as conn:
            row = self._get_run_row(conn, run_id)
            if row["status"] in TERMINAL_RUN_STATUSES:
                raise ResearchStoreError("cannot add sources to a finished run", status=409)
            query_id = payload.get("query_id")
            if query_id is not None:
                _validate_id(query_id, QUERY_RE, "research query id")
                q = conn.execute(
                    "SELECT run_id FROM research_queries WHERE id=?", (query_id,)).fetchone()
                if q is None or q["run_id"] != run_id:
                    raise ResearchStoreError("'query_id' must belong to the same run")
            if duplicate_of is not None:
                _validate_id(duplicate_of, SOURCE_RE, "duplicate_of source id")
                d = conn.execute(
                    "SELECT run_id FROM research_sources WHERE id=?", (duplicate_of,)).fetchone()
                if d is None or d["run_id"] != run_id:
                    raise ResearchStoreError("'duplicate_of' must reference a source in the same run")
            conn.execute(
                """INSERT INTO research_sources
                   (id, run_id, query_id, canonical_url, domain, title, publisher,
                    author, published_at, retrieved_at, language, excerpt,
                    content_hash, duplicate_of, quality_signals, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (source_id, run_id, query_id, url, domain, title, publisher,
                 author, published_at, retrieved_at, language, excerpt,
                 content_hash, duplicate_of, json.dumps(quality_signals), now))
            return self._source_dict(conn.execute(
                "SELECT * FROM research_sources WHERE id=?", (source_id,)).fetchone())

    # -- candidate evidence -------------------------------------------------- #

    def add_candidate(self, run_id, payload):
        """Record a human-authored claim citing sources of this run. Allowed
        on finished runs too — reading sources and writing claims is human
        curation AFTER execution, not execution itself. Only a 'failed' run
        (which produced nothing to cite) refuses candidates."""
        if not isinstance(payload, dict):
            raise ResearchStoreError("payload must be an object")
        claim = _require_str(payload, "claim", TEXT_MAX, required=True)
        contradicts = _require_str(payload, "contradicts", TEXT_MAX)
        source_ids = payload.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids:
            raise ResearchStoreError("'source_ids' must be a non-empty array — "
                                     "a candidate claim without a source is fabrication")
        if len(source_ids) > CANDIDATE_SOURCES_MAX:
            raise ResearchStoreError(f"'source_ids' exceeds {CANDIDATE_SOURCES_MAX} items")
        # PR3 — origin/extraction_meta record whether a human or the verified
        # extractor produced the claim; both still start pending_review.
        origin = payload.get("origin", "human")
        if origin not in ("human", "extracted"):
            raise ResearchStoreError("'origin' must be 'human' or 'extracted'")
        extraction_meta = payload.get("extraction_meta")
        if extraction_meta is not None and not isinstance(extraction_meta, dict):
            raise ResearchStoreError("'extraction_meta' must be an object")
        candidate_id = _new_id("RCAND")
        now = _now()
        with self._connect() as conn:
            row = self._get_run_row(conn, run_id)
            if row["status"] == "failed":
                raise ResearchStoreError("a failed run has no sources to cite", status=409)
            seen = set()
            for sid in source_ids:
                _validate_id(sid, SOURCE_RE, "source id")
                if sid in seen:
                    raise ResearchStoreError("'source_ids' contains duplicates")
                seen.add(sid)
                s = conn.execute(
                    "SELECT run_id FROM research_sources WHERE id=?", (sid,)).fetchone()
                if s is None or s["run_id"] != run_id:
                    raise ResearchStoreError(
                        "every candidate source must belong to the same run", status=400)
            conn.execute(
                """INSERT INTO candidate_evidence
                   (id, run_id, claim, source_ids, status, contradicts, origin,
                    extraction_meta, created_at, updated_at)
                   VALUES (?,?,?,?,'pending_review',?,?,?,?,?)""",
                (candidate_id, run_id, claim, json.dumps(source_ids), contradicts,
                 origin, json.dumps(extraction_meta) if extraction_meta else None, now, now))
            return self._candidate_dict(conn.execute(
                "SELECT * FROM candidate_evidence WHERE id=?", (candidate_id,)).fetchone())

    def get_candidate(self, candidate_id):
        """One candidate claim by id (Phase R8b — lets routes resolve the
        owning run before acting on a candidate)."""
        _validate_id(candidate_id, CANDIDATE_RE, "candidate id")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM candidate_evidence WHERE id=?", (candidate_id,)).fetchone()
        if row is None:
            raise ResearchStoreError("candidate not found", status=404)
        return self._candidate_dict(row)

    def review_candidate(self, candidate_id, action, note=None):
        """Human review (Phase R3): pending_review -> approved | rejected,
        exactly once. Approval NEVER makes the claim authoritative knowledge —
        it never mints an EV id and never writes the knowledge base; it only
        marks the candidate usable as clearly-labelled external research."""
        _validate_id(candidate_id, CANDIDATE_RE, "candidate id")
        if action not in ("approve", "reject"):
            raise ResearchStoreError("action must be 'approve' or 'reject'")
        if note is not None:
            if not isinstance(note, str) or len(note) > TEXT_MAX:
                raise ResearchStoreError("'note' must be a bounded string")
            note = note.strip() or None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM candidate_evidence WHERE id=?", (candidate_id,)).fetchone()
            if row is None:
                raise ResearchStoreError("candidate not found", status=404)
            if row["status"] != "pending_review":
                raise ResearchStoreError(
                    f"candidate already reviewed ('{row['status']}')", status=409)
            status = "approved" if action == "approve" else "rejected"
            conn.execute(
                "UPDATE candidate_evidence SET status=?, review_note=?, updated_at=? WHERE id=?",
                (status, note, _now(), candidate_id))
            return self._candidate_dict(conn.execute(
                "SELECT * FROM candidate_evidence WHERE id=?", (candidate_id,)).fetchone())

    def list_candidates(self, status=None, opportunity_ref=None, limit=100,
                        visible_to=None):
        """Cross-run candidate listing (the review queue / grounding read).
        Each row carries its run's title, status, and opportunity_ref."""
        if status is not None and status not in CANDIDATE_STATUSES:
            raise ResearchStoreError("unknown candidate status filter")
        if opportunity_ref is not None and not OPP_REF_RE.match(str(opportunity_ref)):
            raise ResearchStoreError("invalid opportunity_ref filter")
        limit = max(1, min(int(limit), 500))
        clauses, params = [], []
        if status:
            clauses.append("c.status=?")
            params.append(status)
        if opportunity_ref:
            clauses.append("r.opportunity_ref=?")
            params.append(opportunity_ref)
        if visible_to is not None:
            # Phase R8b — candidates follow their run's ownership
            clauses.append("(r.owner_user_id IS NULL OR r.owner_user_id=?)")
            params.append(visible_to)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT c.*, r.title AS run_title, r.status AS run_status,
                           r.opportunity_ref AS opportunity_ref
                    FROM candidate_evidence c JOIN research_runs r ON r.id = c.run_id
                    {where} ORDER BY c.created_at DESC, c.id LIMIT ?""",
                (*params, limit)).fetchall()
            return [self._candidate_dict(r) for r in rows]

    def get_sources(self, source_ids):
        """The named sources (for citation metadata), in input order; unknown
        ids are simply absent — never invented."""
        out = []
        with self._connect() as conn:
            for sid in source_ids[:CANDIDATE_SOURCES_MAX]:
                if not isinstance(sid, str) or not SOURCE_RE.match(sid):
                    continue
                row = conn.execute(
                    "SELECT * FROM research_sources WHERE id=?", (sid,)).fetchone()
                if row is not None:
                    out.append(self._source_dict(row))
        return out

    # -- source revalidation (Phase R4b) ------------------------------------- #

    def add_revalidation(self, source_id, outcome, http_status=None,
                         new_content_hash=None, note=None):
        """Append one re-check result for a source. The source row itself is
        never modified — revalidations are history, and acting on them
        (re-running research, revising claims) stays a human decision."""
        _validate_id(source_id, SOURCE_RE, "source id")
        if outcome not in REVALIDATION_OUTCOMES:
            raise ResearchStoreError("outcome must be unchanged, changed, or unreachable")
        if http_status is not None and (not isinstance(http_status, int)
                                        or isinstance(http_status, bool)):
            raise ResearchStoreError("'http_status' must be an integer")
        if note is not None:
            if not isinstance(note, str) or len(note) > ERROR_MAX:
                raise ResearchStoreError("'note' must be a bounded string")
            note = note.strip() or None
        if new_content_hash is not None and (not isinstance(new_content_hash, str)
                                             or len(new_content_hash) > SHORT_MAX):
            raise ResearchStoreError("'new_content_hash' must be a bounded string")
        rev_id = _new_id("RREV")
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM research_sources WHERE id=?",
                               (source_id,)).fetchone()
            if row is None:
                raise ResearchStoreError("source not found", status=404)
            conn.execute(
                """INSERT INTO source_revalidations
                   (id, source_id, outcome, http_status, new_content_hash, note, checked_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (rev_id, source_id, outcome, http_status, new_content_hash, note, _now()))
            return dict(conn.execute(
                "SELECT * FROM source_revalidations WHERE id=?", (rev_id,)).fetchone())

    def latest_revalidations(self, run_id):
        """{source_id: latest revalidation dict} for one run's sources."""
        _validate_id(run_id, RUN_RE, "research run id")
        with self._connect() as conn:
            # rowid tiebreak: checked_at has second precision, so two checks
            # in the same second must still resolve "latest" by insertion
            # order, not by random-uuid id order.
            rows = conn.execute(
                """SELECT r.* FROM source_revalidations r
                    JOIN research_sources s ON s.id = r.source_id
                    WHERE s.run_id=? ORDER BY r.checked_at, r.rowid""", (run_id,)).fetchall()
        latest = {}
        for row in rows:  # ordered ascending — the last write per source wins
            latest[row["source_id"]] = dict(row)
        return latest

    @staticmethod
    def source_health(candidate, latest_by_source):
        """Worst latest revalidation outcome among a candidate's cited
        sources: 'unreachable' > 'changed' > 'ok'. 'ok' also covers
        never-revalidated sources — absence of a check is not a failure."""
        worst = "ok"
        for sid in candidate.get("source_ids") or []:
            rev = latest_by_source.get(sid)
            if rev is None:
                continue
            if rev["outcome"] == "unreachable":
                return "unreachable"
            if rev["outcome"] == "changed":
                worst = "changed"
        return worst
