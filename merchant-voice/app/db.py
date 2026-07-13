"""SQLite foundation: separate mv.db / identity.db, forward-only migrations,
WAL mode, explicit transactions, parameterized SQL only.

Phase 1 tables:
  mv.db:       schema_meta, campaigns, guides, guide_questions, audit_events
  identity.db: schema_meta

Phase 2 tables:
  mv.db:       participants, responses, raw_answers, transcripts,
               csv_import_tokens
  identity.db: merchant_identity, audit_events (identity.db gets its own
               append-only audit log — never joined with mv.db's — so
               identity operations are traceable without mixing the two
               stores; the shared `app.audit` module works against either
               connection since it only requires an `audit_events` table)

Merchant identity data (protected_external_reference, identity-level
consent/permission fields) lives ONLY in identity.db. Participants in
mv.db carry a `merchant_identity_id` reference and their own per-campaign
consent snapshot, but never identity.db's other fields — see app/models.py
and app/participants.py for the enforcement that a participant's consent
scope can only narrow, never widen, the identity-level grant.
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
    (2, [
        """CREATE TABLE IF NOT EXISTS participants (
            participant_id TEXT PRIMARY KEY,
            merchant_identity_id TEXT NOT NULL,
            campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
            segment_id TEXT,
            industry TEXT,
            company_size TEXT,
            geography TEXT,
            respondent_role TEXT,
            consent_status TEXT NOT NULL,
            permitted_use TEXT NOT NULL,
            quote_permission INTEGER NOT NULL DEFAULT 0,
            ai_processing_permission INTEGER NOT NULL DEFAULT 0,
            data_classification TEXT NOT NULL,
            retention_expires_at TEXT,
            workflow_status TEXT NOT NULL,
            suppression_status TEXT NOT NULL DEFAULT 'none',
            suppression_cause TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS responses (
            response_id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
            participant_id TEXT NOT NULL REFERENCES participants(participant_id),
            guide_id TEXT NOT NULL REFERENCES guides(guide_id),
            guide_version INTEGER NOT NULL,
            method TEXT NOT NULL,
            ingestion_source TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            processing_status TEXT NOT NULL,
            duplicate_status TEXT NOT NULL,
            consent_snapshot_json TEXT NOT NULL,
            transcript_status TEXT NOT NULL DEFAULT 'none',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS raw_answers (
            answer_id TEXT PRIMARY KEY,
            response_id TEXT NOT NULL REFERENCES responses(response_id),
            question_id TEXT NOT NULL,
            original_answer TEXT,
            language TEXT NOT NULL,
            transcript_location TEXT,
            is_direct_quote INTEGER NOT NULL DEFAULT 0,
            redaction_status TEXT NOT NULL,
            sensitive_data_flags_json TEXT NOT NULL,
            content_purged INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            normalized_answer_hash TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS transcripts (
            response_id TEXT PRIMARY KEY REFERENCES responses(response_id),
            extension TEXT NOT NULL,
            content_type TEXT,
            language TEXT,
            size_bytes INTEGER NOT NULL,
            storage_status TEXT NOT NULL,
            speaker_map_json TEXT NOT NULL DEFAULT '{}',
            storage_filename TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS csv_import_tokens (
            token_id TEXT PRIMARY KEY,
            file_hash TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            guide_id TEXT NOT NULL,
            actor_label TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            consumed_at TEXT,
            created_at TEXT NOT NULL
        )""",
    ]),
]

IDENTITY_MIGRATIONS = [
    (1, ["CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL)"]),
    (2, [
        """CREATE TABLE IF NOT EXISTS merchant_identity (
            merchant_identity_id TEXT PRIMARY KEY,
            protected_external_reference TEXT,
            consent_status TEXT NOT NULL,
            permitted_use TEXT NOT NULL,
            quote_permission INTEGER NOT NULL DEFAULT 0,
            ai_processing_permission INTEGER NOT NULL DEFAULT 0,
            data_classification TEXT NOT NULL,
            retention_expires_at TEXT,
            deletion_requested_at TEXT,
            deleted_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        # Same shape as mv.db's audit_events — identity.db keeps its own,
        # separate append-only log (never joined with mv.db).
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
