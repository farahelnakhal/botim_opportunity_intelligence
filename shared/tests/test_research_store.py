"""Phase R1 — research-run persistence: lifecycle honesty, traceability,
restart survival, URL safety, and zero fabrication. All offline."""

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.research import ResearchStore, ResearchStoreError  # noqa: E402


def make_store(path=None):
    return ResearchStore(path or Path(tempfile.mkdtemp()) / "research.db")


def seeded_run(store, **overrides):
    payload = {"title": "UAE SME card market sizing",
               "objective": "Size the UAE/GCC SME corporate-card opportunity",
               "objectives": ["market size", "competitor benchmark"],
               "profile": "sme-financial-product",
               **overrides}
    return store.create_run(payload)


class RunLifecycle(unittest.TestCase):
    def test_create_starts_pending_with_null_execution_fields(self):
        run = seeded_run(make_store())
        self.assertTrue(run["id"].startswith("RRUN-"))
        self.assertEqual(run["status"], "pending")
        self.assertIsNone(run["started_at"])
        self.assertIsNone(run["completed_at"])
        self.assertIsNone(run["error"])
        self.assertEqual(run["counts"], {"queries": 0, "sources": 0, "candidates": 0})

    def test_full_happy_path_pending_running_complete(self):
        store = make_store()
        run = seeded_run(store)
        run = store.start_run(run["id"])
        self.assertEqual(run["status"], "running")
        self.assertIsNotNone(run["started_at"])
        run = store.finish_run(run["id"], "complete")
        self.assertEqual(run["status"], "complete")
        self.assertIsNotNone(run["completed_at"])
        self.assertIsNone(run["error"])

    def test_partial_and_failed_require_a_reason(self):
        store = make_store()
        for status in ("partial", "failed"):
            run = store.start_run(seeded_run(store)["id"])
            with self.assertRaises(ResearchStoreError):
                store.finish_run(run["id"], status)          # no reason -> rejected
            finished = store.finish_run(run["id"], status, error="provider timed out on 3 of 5 queries")
            self.assertEqual(finished["status"], status)
            self.assertIn("timed out", finished["error"])

    def test_complete_must_not_carry_an_error(self):
        store = make_store()
        run = store.start_run(seeded_run(store)["id"])
        with self.assertRaises(ResearchStoreError):
            store.finish_run(run["id"], "complete", error="but something broke")

    def test_terminal_states_are_immutable(self):
        store = make_store()
        run = store.start_run(seeded_run(store)["id"])
        store.finish_run(run["id"], "complete")
        with self.assertRaises(ResearchStoreError) as cm:
            store.finish_run(run["id"], "failed", error="late failure")
        self.assertEqual(cm.exception.status, 409)
        with self.assertRaises(ResearchStoreError):
            store.start_run(run["id"])

    def test_never_started_run_can_only_fail(self):
        store = make_store()
        run = seeded_run(store)
        with self.assertRaises(ResearchStoreError):
            store.finish_run(run["id"], "complete")
        failed = store.finish_run(run["id"], "failed", error="no provider configured")
        self.assertEqual(failed["status"], "failed")

    def test_opportunity_ref_validated(self):
        store = make_store()
        self.assertEqual(seeded_run(store, opportunity_ref="OPP-013")["opportunity_ref"], "OPP-013")
        with self.assertRaises(ResearchStoreError):
            seeded_run(store, opportunity_ref="EV-2026-W28-001")

    def test_list_filters_and_orders(self):
        store = make_store()
        a = seeded_run(store, title="run a")
        b = seeded_run(store, title="run b", opportunity_ref="OPP-010")
        store.finish_run(store.start_run(a["id"])["id"], "complete")
        self.assertEqual([r["id"] for r in store.list_runs(status="complete")], [a["id"]])
        self.assertEqual([r["id"] for r in store.list_runs(opportunity_ref="OPP-010")], [b["id"]])
        self.assertEqual(len(store.list_runs()), 2)
        with self.assertRaises(ResearchStoreError):
            store.list_runs(status="sideways")


class RestartSurvival(unittest.TestCase):
    def test_runs_and_children_survive_a_new_store_instance(self):
        db = Path(tempfile.mkdtemp()) / "research.db"
        store = make_store(db)
        run = store.start_run(seeded_run(store)["id"])
        q = store.add_query(run["id"], {"query_text": "UAE SME card issuers 2026"})
        s = store.add_source(run["id"], {"canonical_url": "https://example.com/report",
                                         "query_id": q["id"], "title": "Some report"})
        store.add_candidate(run["id"], {"claim": "At least one issuer targets UAE SMEs",
                                        "source_ids": [s["id"]]})
        store.finish_run(run["id"], "partial", error="second provider unavailable")

        reopened = ResearchStore(db)  # simulates a backend restart
        full = reopened.get_run(run["id"], include_children=True)
        self.assertEqual(full["status"], "partial")
        self.assertEqual(full["counts"], {"queries": 1, "sources": 1, "candidates": 1})
        self.assertEqual(full["queries"][0]["query_text"], "UAE SME card issuers 2026")
        self.assertEqual(full["candidate_evidence"][0]["source_ids"], [s["id"]])


class Traceability(unittest.TestCase):
    def setUp(self):
        self.store = make_store()
        self.run = self.store.start_run(seeded_run(self.store)["id"])
        self.other = self.store.start_run(seeded_run(self.store, title="other run")["id"])

    def test_candidate_requires_at_least_one_source(self):
        with self.assertRaises(ResearchStoreError) as cm:
            self.store.add_candidate(self.run["id"], {"claim": "unsourced claim", "source_ids": []})
        self.assertIn("fabrication", str(cm.exception))

    def test_candidate_sources_must_belong_to_the_same_run(self):
        foreign = self.store.add_source(self.other["id"],
                                        {"canonical_url": "https://example.org/x"})
        with self.assertRaises(ResearchStoreError):
            self.store.add_candidate(self.run["id"],
                                     {"claim": "cross-run claim", "source_ids": [foreign["id"]]})

    def test_source_query_must_belong_to_the_same_run(self):
        foreign_q = self.store.add_query(self.other["id"], {"query_text": "q"})
        with self.assertRaises(ResearchStoreError):
            self.store.add_source(self.run["id"], {"canonical_url": "https://example.org/y",
                                                   "query_id": foreign_q["id"]})

    def test_duplicate_of_must_be_same_run(self):
        foreign = self.store.add_source(self.other["id"],
                                        {"canonical_url": "https://example.org/z"})
        with self.assertRaises(ResearchStoreError):
            self.store.add_source(self.run["id"], {"canonical_url": "https://example.org/z2",
                                                   "duplicate_of": foreign["id"]})

    def test_no_children_can_be_added_to_a_finished_run(self):
        self.store.finish_run(self.run["id"], "complete")
        with self.assertRaises(ResearchStoreError):
            self.store.add_query(self.run["id"], {"query_text": "late query"})
        with self.assertRaises(ResearchStoreError):
            self.store.add_source(self.run["id"], {"canonical_url": "https://example.com/late"})


class SourceHonesty(unittest.TestCase):
    def setUp(self):
        self.store = make_store()
        self.run = self.store.start_run(seeded_run(self.store)["id"])

    def test_unsafe_urls_rejected(self):
        for url in ("javascript:alert(1)", "file:///etc/passwd", "ftp://x.com/a",
                    "/local/path", "not a url", ""):
            with self.assertRaises(ResearchStoreError, msg=url):
                self.store.add_source(self.run["id"], {"canonical_url": url})

    def test_absent_metadata_stays_null_never_invented(self):
        s = self.store.add_source(self.run["id"], {"canonical_url": "https://example.com/bare"})
        for field in ("title", "publisher", "author", "published_at",
                      "retrieved_at", "language", "excerpt", "content_hash", "duplicate_of"):
            self.assertIsNone(s[field], field)
        self.assertEqual(s["quality_signals"], {})
        self.assertEqual(s["domain"], "example.com")

    def test_quality_signals_are_bounded_flat_scalars(self):
        s = self.store.add_source(self.run["id"], {
            "canonical_url": "https://example.com/q",
            "quality_signals": {"domain_tier": "news", "has_publication_date": True, "rank": 3}})
        self.assertEqual(s["quality_signals"]["domain_tier"], "news")
        with self.assertRaises(ResearchStoreError):
            self.store.add_source(self.run["id"], {
                "canonical_url": "https://example.com/q2",
                "quality_signals": {"nested": {"not": "allowed"}}})


class QueryHonesty(unittest.TestCase):
    def setUp(self):
        self.store = make_store()
        self.run = self.store.start_run(seeded_run(self.store)["id"])

    def test_failed_query_requires_error_and_executed_forbids_it(self):
        q1 = self.store.add_query(self.run["id"], {"query_text": "a"})
        with self.assertRaises(ResearchStoreError):
            self.store.mark_query(q1["id"], "failed")
        marked = self.store.mark_query(q1["id"], "failed", error="429 rate limited")
        self.assertEqual(marked["status"], "failed")
        q2 = self.store.add_query(self.run["id"], {"query_text": "b"})
        with self.assertRaises(ResearchStoreError):
            self.store.mark_query(q2["id"], "executed", error="should not be here")
        done = self.store.mark_query(q2["id"], "executed", result_count=7)
        self.assertEqual(done["result_count"], 7)

    def test_query_cannot_be_marked_twice(self):
        q = self.store.add_query(self.run["id"], {"query_text": "a"})
        self.store.mark_query(q["id"], "executed", result_count=0)
        with self.assertRaises(ResearchStoreError) as cm:
            self.store.mark_query(q["id"], "failed", error="flip-flop")
        self.assertEqual(cm.exception.status, 409)

    def test_result_count_is_recorded_never_invented(self):
        q = self.store.add_query(self.run["id"], {"query_text": "a"})
        self.assertIsNone(q["result_count"])
        done = self.store.mark_query(q["id"], "executed")  # count unknown -> stays null
        self.assertIsNone(done["result_count"])


if __name__ == "__main__":
    unittest.main()
