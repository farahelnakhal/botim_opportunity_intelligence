"""Phase R4a — manual monitoring runs: real events from real sources, honest
zero/failed outcomes, idempotent reruns, config state discipline. Offline
(injected mock search provider + temp DBs)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("BOTIM_APP_MODE", "test")
os.environ.setdefault("USER_OPPORTUNITIES_DB_PATH",
                      os.path.join(tempfile.mkdtemp(), "user-opportunities.db"))

UI = Path(__file__).resolve().parents[2]
REPO = UI.parents[0]
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import monitoring_runner                     # noqa: E402
from api.user_store import UserStore                  # noqa: E402
from shared.research import MockSearchProvider, ResearchStore  # noqa: E402
from shared.research.runner import execute_run        # noqa: E402


def offline_execute(store, run_id, provider, **kw):
    # page body varies by URL — identical bodies would (correctly) be
    # content-hash-deduplicated by the research runner
    kw.setdefault("fetch_fn", lambda u, t: (
        200, "text/html",
        f"<html><title>Page</title><body>content of {u}</body>".encode()))
    kw.setdefault("sleep_fn", lambda s: None)
    return execute_run(store, run_id, provider, **kw)


class RunnerTestCase(unittest.TestCase):
    def setUp(self):
        self.users = UserStore(Path(tempfile.mkdtemp()) / "u.db")
        self.research = ResearchStore(Path(tempfile.mkdtemp()) / "r.db")
        self.opp = self.users.create({"title": "Instant settlement for grocers"})
        self.users.monitoring_put(self.opp["id"], {
            "enabled": True, "topics": ["grocery instant settlement UAE"],
            "keywords": ["chargebacks"], "excluded_domains": ["blocked.example"]})

    def _run(self, provider, **kw):
        return monitoring_runner.run_monitoring(
            self.users, self.research, self.opp["id"], provider,
            execute_run_fn=offline_execute, **kw)

    def test_successful_run_creates_events_from_real_sources(self):
        provider = MockSearchProvider({
            "grocery instant settlement UAE": [
                {"url": "https://news.example.com/a", "title": "Settlement news",
                 "published_at": "2026-07-01"}],
            "Instant settlement for grocers chargebacks": [
                {"url": "https://news.example.com/b", "title": "Chargeback study"}]})
        result = self._run(provider)
        self.assertEqual(result["run_status"], "complete")
        self.assertEqual(result["events_created"], 2)
        for e in result["new_events"]:
            self.assertTrue(e["id"].startswith("MEVT-"))
            self.assertTrue(e["source_id"].startswith("RSRC-"))     # grounded in RSRC
            self.assertEqual(e["research_run_id"], result["run_id"])  # traceable to the run
        config = self.users.monitoring_get(self.opp["id"])
        self.assertEqual(config["status"], "active")
        self.assertIsNotNone(config["last_run_at"])
        self.assertEqual(config["consecutive_failure_count"], 0)

    def test_rerun_is_idempotent_only_new_urls_become_events(self):
        provider = MockSearchProvider({
            "grocery instant settlement UAE": [{"url": "https://news.example.com/a"}]})
        first = self._run(provider)
        self.assertEqual(first["events_created"], 1)
        second = self._run(provider)  # same URL again -> no second "new" event
        self.assertEqual(second["events_created"], 0)
        self.assertIn("No new developments", second["note"])
        self.assertEqual(second["run_status"], "complete")  # still a successful run
        self.assertEqual(len(self.users.monitoring_events(self.opp["id"])), 1)

    def test_no_provider_records_honest_error_and_never_advances_last_run(self):
        result = self._run(None)
        self.assertEqual(result["run_status"], "failed")
        self.assertEqual(result["events_created"], 0)
        config = self.users.monitoring_get(self.opp["id"])
        self.assertEqual(config["status"], "error")
        self.assertIn("no search provider configured", config["last_error"])
        self.assertEqual(config["consecutive_failure_count"], 1)
        self.assertIsNone(config["last_run_at"])   # a failed run monitored nothing

    def test_failure_counter_accumulates_and_success_resets_it(self):
        self._run(None)
        self._run(None)
        self.assertEqual(self.users.monitoring_get(self.opp["id"])["consecutive_failure_count"], 2)
        self._run(MockSearchProvider({"grocery instant settlement UAE": [
            {"url": "https://news.example.com/x"}]}))
        config = self.users.monitoring_get(self.opp["id"])
        self.assertEqual(config["consecutive_failure_count"], 0)
        self.assertEqual(config["status"], "active")

    def test_paused_config_refuses_to_run(self):
        self.users.monitoring_pause(self.opp["id"])
        with self.assertRaises(monitoring_runner.MonitoringRunError) as cm:
            self._run(MockSearchProvider())
        self.assertEqual(cm.exception.status, 409)

    def test_unconfigured_opportunity_404s(self):
        other = self.users.create({"title": "No monitoring here"})
        with self.assertRaises(monitoring_runner.MonitoringRunError) as cm:
            monitoring_runner.run_monitoring(self.users, self.research, other["id"],
                                             MockSearchProvider(), execute_run_fn=offline_execute)
        self.assertEqual(cm.exception.status, 404)

    def test_excluded_domains_flow_through_to_execution(self):
        provider = MockSearchProvider({
            "grocery instant settlement UAE": [
                {"url": "https://blocked.example/story"},
                {"url": "https://kept.example.com/story"}]})
        result = self._run(provider)
        self.assertEqual(result["events_created"], 1)
        self.assertEqual(result["new_events"][0]["domain"], "kept.example.com")

    def test_empty_config_lists_refuse_with_a_clear_reason(self):
        self.users.monitoring_put(self.opp["id"], {"enabled": True, "topics": [],
                                                   "keywords": [], "entities": []})
        with self.assertRaises(monitoring_runner.MonitoringRunError) as cm:
            self._run(MockSearchProvider())
        self.assertIn("no topics", str(cm.exception))

    def test_partial_provider_failure_is_partial_with_events_kept(self):
        provider = MockSearchProvider(
            {"grocery instant settlement UAE": [{"url": "https://news.example.com/ok"}]},
            fail_queries={"Instant settlement for grocers chargebacks"})
        result = self._run(provider)
        self.assertEqual(result["run_status"], "partial")
        self.assertEqual(result["events_created"], 1)
        self.assertIn("partially", result["note"])
        # partial execution still counts as a run that happened
        self.assertEqual(self.users.monitoring_get(self.opp["id"])["status"], "active")

    def test_events_survive_restart(self):
        provider = MockSearchProvider({
            "grocery instant settlement UAE": [{"url": "https://news.example.com/a"}]})
        self._run(provider)
        reopened = UserStore(self.users.db_path)
        events = reopened.monitoring_events(self.opp["id"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["canonical_url"], "https://news.example.com/a")


class V1MigrationCompat(unittest.TestCase):
    def test_v1_database_migrates_to_v2_in_place(self):
        import sqlite3
        db = Path(tempfile.mkdtemp()) / "u.db"
        store = UserStore(db)              # creates v2
        with sqlite3.connect(db) as conn:  # simulate an old v1 DB
            conn.execute("DROP TABLE monitoring_events")
            conn.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
        reopened = UserStore(db)           # must migrate, not crash
        opp = reopened.create({"title": "post-migration"})
        self.assertEqual(reopened.monitoring_events(opp["id"]), [])


if __name__ == "__main__":
    unittest.main()
