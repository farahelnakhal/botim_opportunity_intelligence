"""Database foundation tests: migrations, WAL, transactions, parameterization."""

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from app.db import connect_identity, connect_mv  # noqa: E402


class DbMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.mv_path = Path(self.tmp.name) / "mv.db"
        self.id_path = Path(self.tmp.name) / "identity.db"

    def test_mv_schema_created_with_expected_tables(self):
        conn = connect_mv(self.mv_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        for expected in ("schema_meta", "campaigns", "guides", "guide_questions", "audit_events",
                        "participants", "responses", "raw_answers", "transcripts", "csv_import_tokens",
                        "observations", "extraction_runs", "evidence_candidates", "candidate_observations",
                        "merchant_findings", "part_a_proposals"):
            self.assertIn(expected, tables)
        version = conn.execute("SELECT version FROM schema_meta").fetchone()[0]
        self.assertEqual(version, 5)

    def test_identity_schema_phase2_tables(self):
        conn = connect_identity(self.id_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        self.assertEqual(tables, {"schema_meta", "merchant_identity", "audit_events"})

    def test_migration_idempotent(self):
        connect_mv(self.mv_path)
        conn2 = connect_mv(self.mv_path)  # reconnect / re-migrate
        version = conn2.execute("SELECT version FROM schema_meta").fetchone()[0]
        self.assertEqual(version, 5)
        rows = conn2.execute("SELECT COUNT(*) FROM schema_meta").fetchone()[0]
        self.assertEqual(rows, 1)  # no duplicate schema_meta rows from re-migration

    def test_wal_mode_enabled(self):
        conn = connect_mv(self.mv_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(mode.lower(), "wal")

    def test_foreign_keys_enabled(self):
        conn = connect_mv(self.mv_path)
        self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_parameterized_insert_handles_hostile_strings_safely(self):
        conn = connect_mv(self.mv_path)
        hostile = "'); DROP TABLE campaigns; --"
        now = "2026-01-01T00:00:00Z"
        with conn:
            conn.execute(
                "INSERT INTO campaigns (campaign_id, title, objective, research_questions_json, "
                "target_segments_json, linked_opportunities_json, linked_assumptions_json, method, "
                "workflow_status, owner, consent_template_id, data_classification, sampling_notes, "
                "start_date, end_date, created_by, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("MVC-TEST-999", hostile, "obj", "[]", "[]", "[]", "[]", "interview", "draft",
                 "owner", None, "synthetic", None, None, None, "tester", now, now))
        row = conn.execute("SELECT title FROM campaigns WHERE campaign_id=?", ("MVC-TEST-999",)).fetchone()
        self.assertEqual(row[0], hostile)  # stored literally, table still intact
        still_there = conn.execute("SELECT name FROM sqlite_master WHERE name='campaigns'").fetchone()
        self.assertIsNotNone(still_there)

    def test_transaction_rolls_back_on_failure(self):
        conn = connect_mv(self.mv_path)
        try:
            with conn:
                conn.execute("INSERT INTO schema_meta (version) VALUES (?)", (99,))
                raise RuntimeError("simulated failure mid-transaction")
        except RuntimeError:
            pass
        # the extra row must not have been committed
        count = conn.execute("SELECT COUNT(*) FROM schema_meta").fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
