"""Phase R4b — source revalidation: append-only history, honest outcomes,
source-health rollup, v1->v2 migration. Offline (injected fetch)."""

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.research import (MockSearchProvider, ResearchStore,  # noqa: E402
                             ResearchStoreError, execute_run, revalidate_run)


def make_store():
    return ResearchStore(Path(tempfile.mkdtemp()) / "research.db")


def executed_run(store, urls=("https://example.com/a",)):
    run = store.create_run({"title": "revalidation seed"})
    store.add_query(run["id"], {"query_text": "q"})
    provider = MockSearchProvider({"q": [{"url": u} for u in urls]})
    execute_run(store, run["id"], provider,
                fetch_fn=lambda u, t: (200, "text/html",
                                       f"<html><title>t</title><body>original {u}</body>".encode()),
                sleep_fn=lambda s: None)
    return store.get_run(run["id"], include_children=True)


class Outcomes(unittest.TestCase):
    def setUp(self):
        self.store = make_store()

    def test_unchanged_when_content_hash_matches(self):
        run = executed_run(self.store)
        url = run["sources"][0]["canonical_url"]
        summary = revalidate_run(
            self.store, run["id"], sleep_fn=lambda s: None,
            fetch_fn=lambda u, t: (200, "text/html",
                                   f"<html><title>t</title><body>original {u}</body>".encode()))
        self.assertEqual(summary["unchanged"], 1)
        detail = self.store.get_run(run["id"], include_children=True)
        rev = detail["sources"][0]["last_revalidation"]
        self.assertEqual(rev["outcome"], "unchanged")
        # the original source row is never mutated
        self.assertEqual(detail["sources"][0]["canonical_url"], url)
        self.assertIn("original", detail["sources"][0]["excerpt"])

    def test_changed_when_content_differs(self):
        run = executed_run(self.store)
        summary = revalidate_run(
            self.store, run["id"], sleep_fn=lambda s: None,
            fetch_fn=lambda u, t: (200, "text/html",
                                   b"<html><title>t</title><body>totally different now</body>"))
        self.assertEqual(summary["changed"], 1)
        detail = self.store.get_run(run["id"], include_children=True)
        self.assertEqual(detail["sources"][0]["last_revalidation"]["outcome"], "changed")

    def test_unreachable_when_fetch_fails(self):
        run = executed_run(self.store)

        def dead(u, t):
            raise OSError("gone")
        summary = revalidate_run(self.store, run["id"], fetch_fn=dead, sleep_fn=lambda s: None)
        self.assertEqual(summary["unreachable"], 1)
        rev = self.store.get_run(run["id"], include_children=True)["sources"][0]["last_revalidation"]
        self.assertEqual(rev["outcome"], "unreachable")
        self.assertIn("OSError", rev["note"])

    def test_history_appends_latest_wins_on_read(self):
        run = executed_run(self.store)
        revalidate_run(self.store, run["id"], sleep_fn=lambda s: None,
                       fetch_fn=lambda u, t: (200, "text/html", b"<html><body>new</body>"))
        revalidate_run(self.store, run["id"], sleep_fn=lambda s: None,
                       fetch_fn=lambda u, t: (_ for _ in ()).throw(OSError("down")))
        latest = self.store.latest_revalidations(run["id"])
        self.assertEqual(len(latest), 1)
        self.assertEqual(list(latest.values())[0]["outcome"], "unreachable")

    def test_duplicates_skipped_and_bounded(self):
        run = executed_run(self.store, urls=[f"https://example.com/{i}" for i in range(5)])
        calls = []

        def counting(u, t):
            calls.append(u)
            return 200, "text/html", b"<html><body>x</body>"
        summary = revalidate_run(self.store, run["id"], fetch_fn=counting,
                                 sleep_fn=lambda s: None, max_checks=3)
        self.assertEqual(summary["checked"], 3)
        self.assertEqual(summary["skipped"], 2)
        self.assertEqual(len(calls), 3)

    def test_invalid_outcome_rejected(self):
        run = executed_run(self.store)
        with self.assertRaises(ResearchStoreError):
            self.store.add_revalidation(run["sources"][0]["id"], "sideways")


class SourceHealth(unittest.TestCase):
    def test_candidate_health_rolls_up_worst_outcome(self):
        store = make_store()
        run = executed_run(store, urls=("https://example.com/a", "https://example.com/b"))
        sources = store.get_run(run["id"], include_children=True)["sources"]
        cand = store.add_candidate(run["id"], {"claim": "two-source claim",
                                               "source_ids": [s["id"] for s in sources]})
        # no revalidation yet -> ok (absence of a check is not a failure)
        detail = store.get_run(run["id"], include_children=True)
        self.assertEqual(detail["candidate_evidence"][0]["source_health"], "ok")

        store.add_revalidation(sources[0]["id"], "changed")
        detail = store.get_run(run["id"], include_children=True)
        self.assertEqual(detail["candidate_evidence"][0]["source_health"], "changed")

        store.add_revalidation(sources[1]["id"], "unreachable")
        detail = store.get_run(run["id"], include_children=True)
        self.assertEqual(detail["candidate_evidence"][0]["source_health"], "unreachable")
        # the review decision itself is untouched — propose, never auto-apply
        self.assertEqual(detail["candidate_evidence"][0]["status"], "pending_review")
        self.assertEqual(detail["candidate_evidence"][0]["id"], cand["id"])


class Migration(unittest.TestCase):
    def test_v1_research_db_migrates_in_place(self):
        db = Path(tempfile.mkdtemp()) / "research.db"
        store = ResearchStore(db)
        run = executed_run(store)
        with sqlite3.connect(db) as conn:  # simulate a v1 database
            conn.execute("DROP TABLE source_revalidations")
            conn.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
        reopened = ResearchStore(db)
        self.assertEqual(reopened.latest_revalidations(run["id"]), {})
        detail = reopened.get_run(run["id"], include_children=True)
        self.assertIsNone(detail["sources"][0]["last_revalidation"])


if __name__ == "__main__":
    unittest.main()
