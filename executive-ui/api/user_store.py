"""Runtime persistence for user-created opportunity drafts and their
monitoring configuration (Phases 6-7).

Design:

- The committed Git knowledge base stays READ-ONLY. User-created records
  live in a separate runtime SQLite database, by default
  `runtime/user-opportunities.db` under the repository root, overridable via
  the USER_OPPORTUNITIES_DB_PATH environment variable. The runtime directory
  is gitignored — a runtime database is never committed.
- Schema is versioned (meta table, SCHEMA_VERSION below); the database is
  initialized on first use and future migrations run inside a transaction.
- Foreign keys are enabled per connection; every statement is parameterized;
  no SQL is ever built from request strings.
- Timestamps are UTC ISO-8601 (seconds precision, trailing Z).
- Deletion policy (documented, enforced): a **draft** may be permanently
  deleted; a **saved** opportunity must be archived instead (DELETE returns
  a conflict); an **archived** record may be permanently deleted only with
  the explicit `confirm=archived` acknowledgement flag. Archiving is the
  default non-destructive path.
- IDs use the UOPP- namespace (`UOPP-<12 hex>`), which cannot collide with
  committed OPP-nnn ids; monitoring configuration ids use MCFG-<12 hex>.
- Lifecycle (the `status` field IS the lifecycle state):
  draft -> saved -> archived (restore: archived -> saved).
  A draft is never presented as validated or scored.
"""

import json
import os
import re
import sqlite3
import uuid
import datetime
from pathlib import Path

SCHEMA_VERSION = 3

REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO / "runtime" / "user-opportunities.db"

UOPP_RE = re.compile(r"^UOPP-[0-9a-f]{12}$")
CONV_RE = re.compile(r"^conv_[0-9a-f]{12}$")

STATUSES = ("draft", "saved", "archived")
MONITORING_STATUSES = ("not_configured", "active", "paused", "error", "never_run")
CADENCES = ("manual", "daily", "weekly", "monthly")

# bounded sizes — requests beyond these are rejected, never truncated silently
TITLE_MAX = 200
TEXT_MAX = 4000
NOTES_MAX = 2000
SHORT_MAX = 120
LIST_MAX_ITEMS = 50
LIST_ITEM_MAX = 500

TEXT_FIELDS = ("product_definition", "problem_statement", "target_segment",
               "customer_description", "value_proposition")
LIST_FIELDS = ("assumptions", "risks", "unknowns", "next_actions")

MONITORING_LIST_FIELDS = ("topics", "keywords", "entities", "source_categories",
                          "preferred_domains", "excluded_domains")


class StoreError(Exception):
    """Safe, structured store error — `status` maps to the HTTP status; the
    message never contains SQL or paths."""

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
            raise StoreError(f"'{key}' is required")
        return None
    if not isinstance(value, str):
        raise StoreError(f"'{key}' must be a string")
    if len(value) > max_len:
        raise StoreError(f"'{key}' exceeds the {max_len}-character limit")
    return value.strip() or None


def _require_list(payload, key):
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        raise StoreError(f"'{key}' must be an array of strings")
    if len(value) > LIST_MAX_ITEMS:
        raise StoreError(f"'{key}' exceeds {LIST_MAX_ITEMS} items")
    out = []
    for item in value:
        if not isinstance(item, str):
            raise StoreError(f"'{key}' items must be strings")
        if len(item) > LIST_ITEM_MAX:
            raise StoreError(f"'{key}' items exceed the {LIST_ITEM_MAX}-character limit")
        item = item.strip()
        if item:
            out.append(item)
    return out


def _validate_uopp_id(opp_id):
    if not isinstance(opp_id, str) or not UOPP_RE.match(opp_id):
        raise StoreError("invalid user-opportunity id", status=400)
    return opp_id


class UserStore:
    """SQLite-backed store. One short-lived connection per operation (safe
    under the threading HTTP server); every write is a transaction."""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path
                            or os.environ.get("USER_OPPORTUNITIES_DB_PATH")
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
                raise StoreError("user-opportunity database is newer than this code", status=500)
            if version < 1:
                self._migrate_to_v1(conn)
            if version < 2:
                self._migrate_to_v2(conn)
            if version < 3:
                self._migrate_to_v3(conn)
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                         (str(SCHEMA_VERSION),))

    @staticmethod
    def _migrate_to_v1(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS user_opportunities (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft','saved','archived')),
            product_definition TEXT,
            problem_statement TEXT,
            target_segment TEXT,
            customer_description TEXT,
            value_proposition TEXT,
            assumptions TEXT NOT NULL DEFAULT '[]',
            risks TEXT NOT NULL DEFAULT '[]',
            unknowns TEXT NOT NULL DEFAULT '[]',
            next_actions TEXT NOT NULL DEFAULT '[]',
            source_conversation_id TEXT,
            created_from_analysis INTEGER NOT NULL DEFAULT 0,
            monitoring_enabled INTEGER NOT NULL DEFAULT 0,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            archived_at TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS monitoring_configs (
            id TEXT PRIMARY KEY,
            opportunity_id TEXT NOT NULL UNIQUE
                REFERENCES user_opportunities(id) ON DELETE CASCADE,
            enabled INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'never_run'
                CHECK (status IN ('not_configured','active','paused','error','never_run')),
            cadence TEXT NOT NULL DEFAULT 'manual'
                CHECK (cadence IN ('manual','daily','weekly','monthly')),
            topics TEXT NOT NULL DEFAULT '[]',
            keywords TEXT NOT NULL DEFAULT '[]',
            entities TEXT NOT NULL DEFAULT '[]',
            source_categories TEXT NOT NULL DEFAULT '[]',
            preferred_domains TEXT NOT NULL DEFAULT '[]',
            excluded_domains TEXT NOT NULL DEFAULT '[]',
            geographic_scope TEXT,
            language TEXT,
            notes TEXT,
            last_error TEXT,
            consecutive_failure_count INTEGER NOT NULL DEFAULT 0,
            last_run_at TEXT,
            next_run_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)""")

    @staticmethod
    def _migrate_to_v2(conn):
        # Phase R4a — monitoring events produced by MANUAL monitoring runs.
        # An event is exactly "a new, non-duplicate source recorded by a
        # monitoring research run for this opportunity" — grounded in an
        # RSRC record (shared/research), never fabricated or summarized
        # here. The (opportunity_id, canonical_url) uniqueness makes reruns
        # idempotent: a URL already seen for this opportunity never becomes
        # a second "new" event.
        conn.execute("""CREATE TABLE IF NOT EXISTS monitoring_events (
            id TEXT PRIMARY KEY,
            opportunity_id TEXT NOT NULL
                REFERENCES user_opportunities(id) ON DELETE CASCADE,
            config_id TEXT NOT NULL,
            research_run_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            title TEXT,
            canonical_url TEXT NOT NULL,
            domain TEXT NOT NULL,
            published_at TEXT,
            detected_at TEXT NOT NULL,
            UNIQUE (opportunity_id, canonical_url))""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mevents_opp "
                     "ON monitoring_events(opportunity_id)")

    @staticmethod
    def _migrate_to_v3(conn):
        # Phase R8a — per-user ownership. Existing (pre-auth) rows keep a
        # NULL owner and are treated as legacy shared records: visible to
        # every signed-in user, never silently reassigned to whoever signs
        # up first. New records created under required-auth mode carry
        # their creator's USER- id. Idempotent (PRAGMA guard) like the
        # research store's v3 migration.
        existing = {row["name"] for row in conn.execute(
            "PRAGMA table_info(user_opportunities)")}
        if "owner_user_id" not in existing:
            conn.execute("ALTER TABLE user_opportunities ADD COLUMN owner_user_id TEXT")

    # -- serialization ---------------------------------------------------- #

    @staticmethod
    def _opp_dict(row):
        d = dict(row)
        for key in LIST_FIELDS:
            d[key] = json.loads(d.get(key) or "[]")
        d["created_from_analysis"] = bool(d["created_from_analysis"])
        d["monitoring_enabled"] = bool(d["monitoring_enabled"])
        d["source"] = "user"  # explicit source type for the read model
        return d

    @staticmethod
    def _config_dict(row):
        d = dict(row)
        for key in MONITORING_LIST_FIELDS:
            d[key] = json.loads(d.get(key) or "[]")
        d["enabled"] = bool(d["enabled"])
        return d

    # -- opportunity CRUD -------------------------------------------------- #

    def create(self, payload, owner_user_id=None):
        if not isinstance(payload, dict):
            raise StoreError("body must be a JSON object")
        allowed = {"title", "status", "source_conversation_id", "created_from_analysis",
                   *TEXT_FIELDS, *LIST_FIELDS}
        unknown = set(payload) - allowed
        if unknown:
            raise StoreError(f"unknown fields: {sorted(unknown)}")
        title = _require_str(payload, "title", TITLE_MAX, required=True)
        status = payload.get("status", "draft")
        if status not in ("draft", "saved"):
            raise StoreError("status must be 'draft' or 'saved' on creation")
        conv = payload.get("source_conversation_id")
        if conv is not None and not (isinstance(conv, str) and CONV_RE.match(conv)):
            raise StoreError("malformed source_conversation_id")
        created_from_analysis = payload.get("created_from_analysis", False)
        if not isinstance(created_from_analysis, bool):
            raise StoreError("created_from_analysis must be a boolean")
        now = _now()
        opp_id = _new_id("UOPP")
        fields = {k: _require_str(payload, k, TEXT_MAX) for k in TEXT_FIELDS}
        lists = {k: (_require_list(payload, k) or []) for k in LIST_FIELDS}
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO user_opportunities
                   (id, title, status, product_definition, problem_statement,
                    target_segment, customer_description, value_proposition,
                    assumptions, risks, unknowns, next_actions,
                    source_conversation_id, created_from_analysis,
                    version, created_at, updated_at, owner_user_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)""",
                (opp_id, title, status,
                 fields["product_definition"], fields["problem_statement"],
                 fields["target_segment"], fields["customer_description"],
                 fields["value_proposition"],
                 json.dumps(lists["assumptions"]), json.dumps(lists["risks"]),
                 json.dumps(lists["unknowns"]), json.dumps(lists["next_actions"]),
                 conv, int(created_from_analysis), now, now, owner_user_id))
        return self.get(opp_id)

    def list(self, include_archived=False, visible_to=None):
        """All records, or — when `visible_to` is a USER- id (required-auth
        mode) — that user's own records plus legacy shared rows (NULL owner).
        Another user's records are never listed."""
        where, params = [], []
        if not include_archived:
            where.append("status != 'archived'")
        if visible_to is not None:
            where.append("(owner_user_id IS NULL OR owner_user_id = ?)")
            params.append(visible_to)
        clause = f" WHERE {' AND '.join(where)}" if where else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM user_opportunities{clause} ORDER BY created_at DESC",
                params).fetchall()
        return [self._opp_dict(r) for r in rows]

    def get(self, opp_id):
        _validate_uopp_id(opp_id)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM user_opportunities WHERE id=?",
                               (opp_id,)).fetchone()
        if row is None:
            raise StoreError("user opportunity not found", status=404)
        return self._opp_dict(row)

    def update(self, opp_id, payload):
        if not isinstance(payload, dict):
            raise StoreError("body must be a JSON object")
        allowed = {"title", "status", "version", *TEXT_FIELDS, *LIST_FIELDS}
        unknown = set(payload) - allowed
        if unknown:
            raise StoreError(f"unknown fields: {sorted(unknown)}")
        current = self.get(opp_id)
        if current["status"] == "archived":
            raise StoreError("archived opportunities are read-only — restore it first",
                             status=409)
        expected = payload.get("version")
        if expected is not None:
            if not isinstance(expected, int):
                raise StoreError("version must be an integer")
            if expected != current["version"]:
                raise StoreError("version conflict — the record changed since it was loaded",
                                 status=409)
        new_status = payload.get("status")
        if new_status is not None:
            # only the draft -> saved promotion happens through PATCH;
            # archive/restore have their own explicit endpoints
            if new_status not in ("draft", "saved"):
                raise StoreError("status may only be 'draft' or 'saved' here — "
                                 "use the archive/restore endpoints for archival")
            if current["status"] == "saved" and new_status == "draft":
                raise StoreError("a saved opportunity cannot be demoted to draft", status=409)
        sets, params = [], []
        title = _require_str(payload, "title", TITLE_MAX) if "title" in payload else None
        if "title" in payload:
            if title is None:
                raise StoreError("'title' cannot be empty")
            sets.append("title=?"); params.append(title)
        for key in TEXT_FIELDS:
            if key in payload:
                sets.append(f"{key}=?"); params.append(_require_str(payload, key, TEXT_MAX))
        for key in LIST_FIELDS:
            if key in payload:
                sets.append(f"{key}=?")
                params.append(json.dumps(_require_list(payload, key) or []))
        if new_status is not None:
            sets.append("status=?"); params.append(new_status)
        if not sets:
            return current
        sets += ["version=version+1", "updated_at=?"]
        params += [_now(), opp_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE user_opportunities SET {', '.join(sets)} WHERE id=?",
                         params)
        return self.get(opp_id)

    def archive(self, opp_id):
        current = self.get(opp_id)
        if current["status"] == "archived":
            return current
        now = _now()
        with self._connect() as conn:
            conn.execute("UPDATE user_opportunities SET status='archived', archived_at=?, "
                         "version=version+1, updated_at=? WHERE id=?", (now, now, opp_id))
        return self.get(opp_id)

    def restore(self, opp_id):
        current = self.get(opp_id)
        if current["status"] != "archived":
            raise StoreError("only an archived opportunity can be restored", status=409)
        with self._connect() as conn:
            conn.execute("UPDATE user_opportunities SET status='saved', archived_at=NULL, "
                         "version=version+1, updated_at=? WHERE id=?", (_now(), opp_id))
        return self.get(opp_id)

    def delete(self, opp_id, confirm=None):
        """Deletion policy: drafts delete permanently; saved records must be
        archived instead; archived records delete only with confirm=archived."""
        current = self.get(opp_id)
        if current["status"] == "saved":
            raise StoreError("a saved opportunity cannot be deleted — archive it instead",
                             status=409)
        if current["status"] == "archived" and confirm != "archived":
            raise StoreError("deleting an archived opportunity requires confirm=archived",
                             status=409)
        with self._connect() as conn:
            conn.execute("DELETE FROM user_opportunities WHERE id=?", (opp_id,))
        return {"deleted": True, "id": opp_id}

    # -- monitoring configuration (Phase 7) -------------------------------- #

    def monitoring_get(self, opp_id):
        self.get(opp_id)  # 404 for unknown opportunity
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM monitoring_configs WHERE opportunity_id=?",
                               (opp_id,)).fetchone()
        if row is None:
            return {"opportunity_id": opp_id, "status": "not_configured", "enabled": False}
        return self._config_dict(row)

    def monitoring_put(self, opp_id, payload):
        """Create or replace the monitoring configuration. No live runner
        exists yet, so an enabled configuration that has never run is stored
        with status 'never_run' — presented as "Configured — awaiting
        monitoring run", never as actively monitoring."""
        current = self.get(opp_id)
        if current["status"] == "archived":
            raise StoreError("cannot configure monitoring for an archived opportunity",
                             status=409)
        if not isinstance(payload, dict):
            raise StoreError("body must be a JSON object")
        allowed = {"enabled", "cadence", "geographic_scope", "language", "notes",
                   *MONITORING_LIST_FIELDS}
        unknown = set(payload) - allowed
        if unknown:
            raise StoreError(f"unknown fields: {sorted(unknown)}")
        enabled = payload.get("enabled", True)
        if not isinstance(enabled, bool):
            raise StoreError("enabled must be a boolean")
        cadence = payload.get("cadence", "manual")
        if cadence not in CADENCES:
            raise StoreError(f"cadence must be one of {list(CADENCES)}")
        lists = {k: (_require_list(payload, k) or []) for k in MONITORING_LIST_FIELDS}
        geo = _require_str(payload, "geographic_scope", SHORT_MAX)
        language = _require_str(payload, "language", SHORT_MAX)
        notes = _require_str(payload, "notes", NOTES_MAX)
        now = _now()
        with self._connect() as conn:
            row = conn.execute("SELECT id, last_run_at FROM monitoring_configs "
                               "WHERE opportunity_id=?", (opp_id,)).fetchone()
            has_run = bool(row and row["last_run_at"])
            status = ("active" if has_run else "never_run") if enabled else "paused"
            if row:
                conn.execute(
                    """UPDATE monitoring_configs SET enabled=?, status=?, cadence=?,
                       topics=?, keywords=?, entities=?, source_categories=?,
                       preferred_domains=?, excluded_domains=?, geographic_scope=?,
                       language=?, notes=?, updated_at=? WHERE opportunity_id=?""",
                    (int(enabled), status, cadence,
                     json.dumps(lists["topics"]), json.dumps(lists["keywords"]),
                     json.dumps(lists["entities"]), json.dumps(lists["source_categories"]),
                     json.dumps(lists["preferred_domains"]), json.dumps(lists["excluded_domains"]),
                     geo, language, notes, now, opp_id))
            else:
                conn.execute(
                    """INSERT INTO monitoring_configs
                       (id, opportunity_id, enabled, status, cadence, topics, keywords,
                        entities, source_categories, preferred_domains, excluded_domains,
                        geographic_scope, language, notes, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (_new_id("MCFG"), opp_id, int(enabled), status, cadence,
                     json.dumps(lists["topics"]), json.dumps(lists["keywords"]),
                     json.dumps(lists["entities"]), json.dumps(lists["source_categories"]),
                     json.dumps(lists["preferred_domains"]), json.dumps(lists["excluded_domains"]),
                     geo, language, notes, now, now))
            conn.execute("UPDATE user_opportunities SET monitoring_enabled=?, updated_at=? "
                         "WHERE id=?", (int(enabled), now, opp_id))
        return self.monitoring_get(opp_id)

    def _monitoring_set_enabled(self, opp_id, enabled):
        self.get(opp_id)
        with self._connect() as conn:
            row = conn.execute("SELECT id, last_run_at FROM monitoring_configs "
                               "WHERE opportunity_id=?", (opp_id,)).fetchone()
            if row is None:
                raise StoreError("monitoring is not configured for this opportunity",
                                 status=404)
            has_run = bool(row["last_run_at"])
            status = ("active" if has_run else "never_run") if enabled else "paused"
            now = _now()
            conn.execute("UPDATE monitoring_configs SET enabled=?, status=?, updated_at=? "
                         "WHERE opportunity_id=?", (int(enabled), status, now, opp_id))
            conn.execute("UPDATE user_opportunities SET monitoring_enabled=?, updated_at=? "
                         "WHERE id=?", (int(enabled), now, opp_id))
        return self.monitoring_get(opp_id)

    def monitoring_pause(self, opp_id):
        return self._monitoring_set_enabled(opp_id, False)

    def monitoring_resume(self, opp_id):
        return self._monitoring_set_enabled(opp_id, True)

    def monitoring_delete(self, opp_id):
        self.get(opp_id)
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM monitoring_configs WHERE opportunity_id=?",
                               (opp_id,))
            if cur.rowcount == 0:
                raise StoreError("monitoring is not configured for this opportunity",
                                 status=404)
            conn.execute("UPDATE user_opportunities SET monitoring_enabled=0, updated_at=? "
                         "WHERE id=?", (_now(), opp_id))
        return {"deleted": True, "opportunity_id": opp_id}

    def monitoring_list(self):
        """All monitoring configurations joined to their opportunity title —
        for the monitoring overview."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT c.*, o.title AS opportunity_title, o.status AS opportunity_status
                   FROM monitoring_configs c
                   JOIN user_opportunities o ON o.id = c.opportunity_id
                   ORDER BY c.created_at DESC""").fetchall()
        return [self._config_dict(r) for r in rows]

    # -- monitoring runs + events (Phase R4a) ------------------------------- #

    def monitoring_record_result(self, opp_id, ok, error=None):
        """Record the outcome of a MANUAL monitoring run on the config:
        success -> status 'active', last_run_at set, failure counter reset;
        failure -> status 'error', honest last_error, counter incremented.
        last_run_at is only advanced on success — a failed run is never
        presented as having monitored anything."""
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM monitoring_configs WHERE opportunity_id=?",
                               (opp_id,)).fetchone()
            if row is None:
                raise StoreError("monitoring is not configured for this opportunity",
                                 status=404)
            now = _now()
            if ok:
                conn.execute(
                    """UPDATE monitoring_configs SET status='active', last_run_at=?,
                       last_error=NULL, consecutive_failure_count=0, updated_at=?
                       WHERE opportunity_id=?""", (now, now, opp_id))
            else:
                message = (error or "monitoring run failed")[:500]
                conn.execute(
                    """UPDATE monitoring_configs SET status='error', last_error=?,
                       consecutive_failure_count=consecutive_failure_count+1, updated_at=?
                       WHERE opportunity_id=?""", (message, now, opp_id))
        return self.monitoring_get(opp_id)

    def monitoring_add_events(self, opp_id, config_id, candidates):
        """Insert events for genuinely NEW sources. `candidates` are dicts
        with research_run_id, source_id, title, canonical_url, domain,
        published_at. A URL already evented for this opportunity is skipped
        (idempotent reruns). Returns the events actually inserted."""
        inserted = []
        now = _now()
        with self._connect() as conn:
            for c in candidates:
                url = c.get("canonical_url")
                if not isinstance(url, str) or not url:
                    continue
                event_id = _new_id("MEVT")
                cur = conn.execute(
                    """INSERT OR IGNORE INTO monitoring_events
                       (id, opportunity_id, config_id, research_run_id, source_id,
                        title, canonical_url, domain, published_at, detected_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (event_id, opp_id, config_id, c.get("research_run_id"),
                     c.get("source_id"), (c.get("title") or None),
                     url, c.get("domain") or "", c.get("published_at"), now))
                if cur.rowcount:
                    inserted.append(event_id)
            if not inserted:
                return []
            marks = ",".join("?" for _ in inserted)
            rows = conn.execute(
                f"SELECT * FROM monitoring_events WHERE id IN ({marks})",
                inserted).fetchall()
        return [dict(r) for r in rows]

    def monitoring_events(self, opp_id, limit=50):
        self.get(opp_id)  # 404 for unknown opportunity
        limit = max(1, min(int(limit), 200))
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM monitoring_events WHERE opportunity_id=?
                   ORDER BY detected_at DESC, id LIMIT ?""", (opp_id, limit)).fetchall()
        return [dict(r) for r in rows]


def suggested_monitoring_topics(opp):
    """Deterministic, editable topic suggestions derived ONLY from the saved
    opportunity's own fields — configuration drafts, never auto-enabled."""
    topics = []
    if opp.get("title"):
        topics.append(f"{opp['title']} — product category and competitors")
    if opp.get("target_segment"):
        topics.append(f"{opp['target_segment']} — segment demand signals")
    if opp.get("problem_statement"):
        topics.append("Problem space: " + opp["problem_statement"][:120])
    topics += ["Regulatory changes in scope", "Pricing moves by competitors",
               "Technology shifts affecting the category",
               "Merchant/customer feedback themes"]
    return topics[:8]
