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

Phase 3 tables:
  mv.db:       observations, extraction_runs — model-proposed observations
               are never authoritative; every one is created with
               review_status='pending_review' and workflow_status='active'
               (superseded on an explicit rerun, never overwritten).

Phase 4: observations.workflow_status is repurposed to carry the human
review lifecycle directly (pending_review -> approved/rejected, or
superseded by a rerun or a merge) — the old review_status column (which
only ever held 'pending_review') is dropped as redundant; existing
'active' rows become 'pending_review' (their true state — nothing had
reviewed them yet). A new observations.suppression_status tracks privacy
suppression independently of the review decision, mirroring the
participant/response pattern from Phase 2. Adds evidence_candidates,
candidate_observations (join table), and merchant_findings — approved
findings are still NOT authoritative Part A evidence; nothing in this
service writes there.

Merchant identity data (protected_external_reference, identity-level
consent/permission fields) lives ONLY in identity.db. Participants in
mv.db carry a `merchant_identity_id` reference and their own per-campaign
consent snapshot, but never identity.db's other fields — see app/models.py
and app/participants.py for the enforcement that a participant's consent
scope can only narrow, never widen, the identity-level grant.

Phase 5 adds part_a_proposals: a human-reviewed, non-authoritative PROPOSAL
mapping of an approved+published Merchant Voice finding into the shape
Workstream A's Part A evidence-candidate intake expects. workflow_status
(draft/pending_review/approved/rejected/superseded) and publication_status
(unpublished/export_approved/needs_revalidation/suppressed/
exported_synthetic) are separate concepts, mirroring the observation/
candidate/finding pattern — never combined into one status field. Approving
a proposal never mints an EV ID, never writes to
knowledge-base/customer-evidence/records/, and never promotes anything into
Part A; see app/part_a_proposal.py.
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
    (3, [
        """CREATE TABLE IF NOT EXISTS extraction_runs (
            extraction_run_id TEXT PRIMARY KEY,
            response_id TEXT NOT NULL REFERENCES responses(response_id),
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL,
            input_source_hash TEXT NOT NULL,
            proposed_count INTEGER,
            accepted_count INTEGER,
            rejected_count INTEGER,
            safe_error_code TEXT,
            actor_id TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS observations (
            observation_id TEXT PRIMARY KEY,
            response_id TEXT NOT NULL REFERENCES responses(response_id),
            campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
            participant_id TEXT NOT NULL REFERENCES participants(participant_id),
            source_answer_id TEXT NOT NULL REFERENCES raw_answers(answer_id),
            observation_type TEXT NOT NULL,
            normalized_statement TEXT NOT NULL,
            source_excerpt TEXT NOT NULL,
            is_direct_quote INTEGER NOT NULL DEFAULT 0,
            extraction_confidence TEXT NOT NULL,
            frequency TEXT,
            severity TEXT,
            current_workaround TEXT,
            payment_rail TEXT,
            linked_segments_json TEXT NOT NULL,
            linked_opportunities_json TEXT NOT NULL,
            linked_assumptions_json TEXT NOT NULL,
            contradiction_target TEXT,
            follow_up_question TEXT,
            sensitivity_flags_json TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            workflow_status TEXT NOT NULL DEFAULT 'active',
            superseded_by_run_id TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            model_provider TEXT NOT NULL,
            model_name TEXT NOT NULL,
            extraction_run_id TEXT NOT NULL REFERENCES extraction_runs(extraction_run_id),
            source_hash TEXT NOT NULL
        )""",
    ]),
    (4, [
        # repurpose workflow_status to carry the review lifecycle; drop the
        # now-redundant review_status column (it only ever held one value)
        "UPDATE observations SET workflow_status='pending_review' WHERE workflow_status='active'",
        "ALTER TABLE observations DROP COLUMN review_status",
        "ALTER TABLE observations ADD COLUMN suppression_status TEXT NOT NULL DEFAULT 'active'",
        "ALTER TABLE observations ADD COLUMN reviewer_notes TEXT",
        "ALTER TABLE observations ADD COLUMN rejection_reason TEXT",
        "ALTER TABLE observations ADD COLUMN reviewed_by TEXT",
        "ALTER TABLE observations ADD COLUMN reviewed_at TEXT",
        "ALTER TABLE observations ADD COLUMN self_approval INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE observations ADD COLUMN superseded_by_observation_id TEXT",
        """CREATE TABLE IF NOT EXISTS evidence_candidates (
            candidate_id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
            finding_type TEXT NOT NULL,
            statement TEXT NOT NULL,
            segment_id TEXT,
            linked_opportunities_json TEXT NOT NULL,
            linked_assumptions_json TEXT NOT NULL,
            proposed_evidence_role TEXT NOT NULL,
            workflow_status TEXT NOT NULL DEFAULT 'draft',
            strength_band TEXT,
            limitations_json TEXT NOT NULL,
            denominator_definition TEXT,
            included_participant_count INTEGER NOT NULL DEFAULT 0,
            support_count INTEGER NOT NULL DEFAULT 0,
            contradiction_count INTEGER NOT NULL DEFAULT 0,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            reviewed_by TEXT,
            reviewed_at TEXT,
            rejection_reason TEXT,
            superseded_by_candidate_id TEXT,
            supersedes_candidate_id TEXT,
            source_version_hash TEXT NOT NULL,
            self_approval INTEGER NOT NULL DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS candidate_observations (
            candidate_id TEXT NOT NULL REFERENCES evidence_candidates(candidate_id),
            observation_id TEXT NOT NULL REFERENCES observations(observation_id),
            role TEXT NOT NULL,
            PRIMARY KEY (candidate_id, observation_id)
        )""",
        """CREATE TABLE IF NOT EXISTS merchant_findings (
            finding_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL REFERENCES evidence_candidates(candidate_id),
            campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
            approved_statement TEXT NOT NULL,
            segment_id TEXT,
            method TEXT NOT NULL,
            linked_opportunities_json TEXT NOT NULL,
            linked_assumptions_json TEXT NOT NULL,
            strength_band TEXT NOT NULL,
            limitations_json TEXT NOT NULL,
            numerator INTEGER NOT NULL,
            denominator INTEGER NOT NULL,
            denominator_definition TEXT,
            support_count INTEGER NOT NULL,
            contradiction_count INTEGER NOT NULL,
            workflow_status TEXT NOT NULL DEFAULT 'approved',
            publication_status TEXT NOT NULL DEFAULT 'unpublished',
            approved_by TEXT NOT NULL,
            approved_at TEXT NOT NULL,
            source_version_hash TEXT NOT NULL,
            superseded_by_finding_id TEXT,
            published_at TEXT,
            published_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
    ]),
    (5, [
        """CREATE TABLE IF NOT EXISTS part_a_proposals (
            proposal_id TEXT PRIMARY KEY,
            finding_id TEXT NOT NULL REFERENCES merchant_findings(finding_id),
            campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
            source_finding_version_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            rendered_markdown TEXT NOT NULL,
            workflow_status TEXT NOT NULL DEFAULT 'draft',
            publication_status TEXT NOT NULL DEFAULT 'unpublished',
            reviewer TEXT,
            reviewed_at TEXT,
            rejection_reason TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            export_status TEXT NOT NULL DEFAULT 'not_exported',
            export_path TEXT,
            exported_at TEXT,
            superseded_by_proposal_id TEXT,
            synthetic_only INTEGER NOT NULL DEFAULT 1,
            needs_revalidation_reason TEXT
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
