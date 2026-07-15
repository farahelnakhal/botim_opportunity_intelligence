"""Phases 6-7 — the runtime user-opportunity store and monitoring
configuration: schema init in a temp path, CRUD lifecycle, deletion policy,
validation bounds, restart persistence, and monitoring config transitions."""

import sys
import tempfile
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[2]
for p in (str(UI),):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import serialize, user_store  # noqa: E402
from api.user_store import StoreError, UserStore  # noqa: E402


def _tmp_db():
    return Path(tempfile.mkdtemp()) / "user-opportunities.db"


class TestSchemaAndCrud(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.s = UserStore(self.db)

    def test_schema_initializes_with_version(self):
        import sqlite3
        conn = sqlite3.connect(self.db)
        v = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        self.assertEqual(int(v), user_store.SCHEMA_VERSION)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertLessEqual({"user_opportunities", "monitoring_configs"}, tables)
        conn.close()

    def test_create_read_update_archive_restore_delete(self):
        o = self.s.create({"title": "My product", "problem_statement": "pain",
                           "created_from_analysis": True})
        self.assertRegex(o["id"], r"^UOPP-[0-9a-f]{12}$")
        self.assertEqual(o["status"], "draft")
        self.assertEqual(o["version"], 1)
        self.assertEqual(o["source"], "user")
        self.assertTrue(o["created_at"].endswith("Z"))
        o = self.s.update(o["id"], {"status": "saved", "assumptions": ["a"]})
        self.assertEqual((o["status"], o["version"]), ("saved", 2))
        a = self.s.archive(o["id"])
        self.assertEqual(a["status"], "archived")
        self.assertTrue(a["archived_at"])
        self.assertNotIn(a["id"], [x["id"] for x in self.s.list()])
        self.assertIn(a["id"], [x["id"] for x in self.s.list(include_archived=True)])
        r = self.s.restore(a["id"])
        self.assertEqual(r["status"], "saved")
        d = self.s.create({"title": "scratch draft"})
        self.assertEqual(self.s.delete(d["id"]), {"deleted": True, "id": d["id"]})

    def test_deletion_policy(self):
        o = self.s.create({"title": "keep me", "status": "saved"})
        with self.assertRaises(StoreError) as cm:
            self.s.delete(o["id"])
        self.assertEqual(cm.exception.status, 409)
        self.s.archive(o["id"])
        with self.assertRaises(StoreError):
            self.s.delete(o["id"])  # archived needs the explicit confirm flag
        self.assertTrue(self.s.delete(o["id"], confirm="archived")["deleted"])

    def test_validation_bounds_and_unknown_fields(self):
        with self.assertRaises(StoreError):
            self.s.create({"title": ""})
        with self.assertRaises(StoreError):
            self.s.create({"title": "x" * 201})
        with self.assertRaises(StoreError):
            self.s.create({"title": "ok", "hacker_field": 1})
        with self.assertRaises(StoreError):
            self.s.create({"title": "ok", "assumptions": ["y" * 501]})
        with self.assertRaises(StoreError):
            self.s.create({"title": "ok", "assumptions": list("x" * 51)})
        with self.assertRaises(StoreError):
            self.s.create({"title": "ok", "source_conversation_id": "../etc"})
        o = self.s.create({"title": "ok"})
        with self.assertRaises(StoreError):
            self.s.update(o["id"], {"status": "archived"})  # archive has its own endpoint
        self.s.update(o["id"], {"status": "saved"})
        with self.assertRaises(StoreError):
            self.s.update(o["id"], {"status": "draft"})  # no demotion

    def test_optimistic_lock_conflict(self):
        o = self.s.create({"title": "v1"})
        self.s.update(o["id"], {"title": "v2", "version": 1})
        with self.assertRaises(StoreError) as cm:
            self.s.update(o["id"], {"title": "v3", "version": 1})
        self.assertEqual(cm.exception.status, 409)

    def test_archived_records_are_read_only(self):
        o = self.s.create({"title": "arch", "status": "saved"})
        self.s.archive(o["id"])
        with self.assertRaises(StoreError) as cm:
            self.s.update(o["id"], {"title": "nope"})
        self.assertEqual(cm.exception.status, 409)

    def test_unknown_and_invalid_ids(self):
        with self.assertRaises(StoreError) as cm:
            self.s.get("UOPP-000000000000")
        self.assertEqual(cm.exception.status, 404)
        for bad in ("OPP-010", "UOPP-../x", "", None):
            with self.assertRaises(StoreError):
                self.s.get(bad)

    def test_persistence_across_store_restart(self):
        o = self.s.create({"title": "survives restart", "status": "saved"})
        self.s.monitoring_put(o["id"], {"enabled": True, "cadence": "weekly"})
        reopened = UserStore(self.db)  # simulates an API/process restart
        self.assertEqual(reopened.get(o["id"])["title"], "survives restart")
        self.assertEqual(reopened.monitoring_get(o["id"])["cadence"], "weekly")


class TestMonitoringConfig(unittest.TestCase):
    def setUp(self):
        self.s = UserStore(_tmp_db())
        self.opp = self.s.create({"title": "Monitored product", "status": "saved",
                                  "target_segment": "UAE SMEs"})

    def test_not_configured_then_put_pause_resume_delete(self):
        cfg = self.s.monitoring_get(self.opp["id"])
        self.assertEqual(cfg["status"], "not_configured")
        cfg = self.s.monitoring_put(self.opp["id"], {
            "enabled": True, "cadence": "weekly", "topics": ["competitors"],
            "preferred_domains": ["example.com"], "geographic_scope": "UAE"})
        # honest: never claims 'active' before any run has happened
        self.assertEqual(cfg["status"], "never_run")
        self.assertIsNone(cfg["last_run_at"])
        self.assertTrue(self.s.get(self.opp["id"])["monitoring_enabled"])
        self.assertEqual(self.s.monitoring_pause(self.opp["id"])["status"], "paused")
        self.assertEqual(self.s.monitoring_resume(self.opp["id"])["status"], "never_run")
        self.assertTrue(self.s.monitoring_delete(self.opp["id"])["deleted"])
        self.assertEqual(self.s.monitoring_get(self.opp["id"])["status"], "not_configured")
        self.assertFalse(self.s.get(self.opp["id"])["monitoring_enabled"])

    def test_validation(self):
        with self.assertRaises(StoreError):
            self.s.monitoring_put(self.opp["id"], {"cadence": "0 * * * *"})  # no cron
        with self.assertRaises(StoreError):
            self.s.monitoring_put(self.opp["id"], {"enabled": "yes"})
        with self.assertRaises(StoreError):
            self.s.monitoring_put(self.opp["id"], {"surprise": 1})
        with self.assertRaises(StoreError):
            self.s.monitoring_pause(self.opp["id"])  # not configured yet -> 404

    def test_archived_opportunity_cannot_be_configured(self):
        self.s.archive(self.opp["id"])
        with self.assertRaises(StoreError) as cm:
            self.s.monitoring_put(self.opp["id"], {"enabled": True})
        self.assertEqual(cm.exception.status, 409)

    def test_suggested_topics_are_derived_and_bounded(self):
        topics = user_store.suggested_monitoring_topics(self.opp)
        self.assertTrue(any("UAE SMEs" in t for t in topics))
        self.assertLessEqual(len(topics), 8)

    def test_monitoring_list_joins_titles(self):
        self.s.monitoring_put(self.opp["id"], {"enabled": True})
        rows = self.s.monitoring_list()
        self.assertEqual(rows[0]["opportunity_title"], "Monitored product")


class TestUserBrief(unittest.TestCase):
    def test_partial_brief_is_honest(self):
        s = UserStore(_tmp_db())
        o = s.create({"title": "Partial", "status": "saved"})
        b = serialize.user_brief_payload(s, o["id"])
        self.assertEqual(b["record_type"], "user_opportunity")
        self.assertEqual(b["classification"], "unscored")
        self.assertIn("unvalidated", b["classification_label"])
        self.assertIsNone(b["product_definition"])   # not fabricated
        self.assertEqual(b["monitoring"]["status"], "not_configured")
        import json
        blob = json.dumps(b)
        self.assertNotIn("/home/", blob)


if __name__ == "__main__":
    unittest.main()
