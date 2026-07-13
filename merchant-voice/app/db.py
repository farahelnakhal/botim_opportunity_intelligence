"""SQLite foundation: separate mv.db / identity.db, forward-only migrations,
WAL mode, explicit transactions, parameterized SQL only.

Phase 1 tables:
  mv.db:       schema_meta, campaigns, guides, guide_questions, audit_events
  identity.db: schema_meta   (participant/identity tables land in Phase 2)
"""

import json
import sqlite3
from pathlib import Path


class DbError(Exception):
    pass


# --- forward-only migrations ------------------------------------------------

MV_MIGRATIONS = [
    (1, [
        "CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL)",
        """CREATE TABLE IF NOT EXISTS campaigns (
            campaign_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            objective TEXT NOT NULL,
            research_questions_json TEXT NOT NULL,
            target_segments_json TEXT NOT NULL,
            linked_opportunities_json TEXT NOT NULL,
            linked_assumptions_json TEXT NOT NULL,
            method TEXT NOT NULL,
            workflow_status TEXT NOT NULL,
            owner TEXT,
            consent_template_id TEXT,
            data_classification TEXT NOT NULL,
            sampling_notes TEXT,
            start_date TEXT,
            end_date TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS guides (
            guide_id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
            version INTEGER NOT NULL,
            workflow_status TEXT NOT NULL,
            approved_by TEXT,
            approved_at TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(campaign_id, version)
        )""",
        """CREATE TABLE IF NOT EXISTS guide_questions (
            question_id TEXT PRIMARY KEY,
            guide_id TEXT NOT NULL REFERENCES guides(guide_id),
            text TEXT NOT NULL,
            purpose TEXT NOT NULL,
            question_type TEXT NOT NULL,
            follow_up_prompts_json TEXT NOT NULL,
            linked_assumption TEXT,
            linked_hypothesis TEXT,
            position INTEGER NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS audit_events (
            audit_id TEXT PRIMARY KEY,
            actor_id TEXT NOT NULL,
            actor_role TEXT NOT NULL,
            action TEXT NOT NULL,
            object_type TEXT NOT NULL,
            object_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            reason TEXT,
            before_hash TEXT,
            after_hash TEXT,
            safe_diff_json TEXT,
            self_approval INTEGER NOT NULL DEFAULT 0
        )""",
    ]),
]

IDENTITY_MIGRATIONS = [
    (1, ["CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL)"]),
]


def _current_version(conn):
    row = conn.execute("SELECT version FROM schema_meta").fetchone()
    return row[0] if row else 0


def _apply_migrations(conn, migrations):
    conn.execute("CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL)")
    current = _current_version(conn)
    for version, statements in sorted(migrations, key=lambda m: m[0]):
        if version <= current:
            continue
        with conn:
            for stmt in statements:
                conn.execute(stmt)
            if current == 0:
                conn.execute("INSERT INTO schema_meta (version) VALUES (?)", (version,))
            else:
                conn.execute("UPDATE schema_meta SET version = ?", (version,))
            current = version


def connect(path, migrations):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _apply_migrations(conn, migrations)
    return conn


def connect_mv(path):
    return connect(path, MV_MIGRATIONS)


def connect_identity(path):
    return connect(path, IDENTITY_MIGRATIONS)


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


def loads(value):
    return json.loads(value) if value is not None else None
