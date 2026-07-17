"""Phase R5 / PR4 — versioned analysis workspace: store lifecycle, honest
build chain (offline, injected providers), preliminary-score-via-real-engine,
retention, and the version diff that seeds R6 notifications."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.research import MockSearchProvider, ResearchStore  # noqa: E402
from shared.workspace import (WorkspaceStore, WorkspaceStoreError,  # noqa: E402
                              build_queries, build_workspace, compare_versions)
from shared.llm.provider import ConversationModel, ModelResponse  # noqa: E402


def make_stores():
    tmp = Path(tempfile.mkdtemp())
    return WorkspaceStore(tmp / "workspace.db"), ResearchStore(tmp / "research.db")


OPP = {"id": "UOPP-aaaaaaaaaaa1", "title": "Cross-border payroll tool",
       "target_segment": "regional SMEs", "problem_statement": "slow settlement"}


class StubExtractor(ConversationModel):
    def __init__(self, payload_fn, model="stub-llm"):
        self._payload_fn = payload_fn
        self.model = model

    def generate(self, messages, tools, system_prompt, configuration):
        return ModelResponse(content=self._payload_fn())


class _Cfg:
    model = "stub-llm"
    timeout_s = 30


class AnyQuerySearch(MockSearchProvider):
    """One deterministic hit for every query — the builder derives queries
    dynamically from the opportunity, so per-query canning is impractical."""

    def search(self, query, max_results=8):
        self.calls.append(query)
        from shared.research.providers import SearchResult
        return [SearchResult.build("mock", url="https://example.com/report",
                                   title="Payroll report")]


def _fetch(url, timeout_s):
    return (200, "text/html",
            b"<html><title>Payroll report</title><body>"
            b"Settlement takes 4 days on average for the segment.</body>")


def _execute(store, run_id, provider, **kw):
    from shared.research.runner import execute_run
    return execute_run(store, run_id, provider, fetch_fn=_fetch,
                       sleep_fn=lambda s: None)


class StoreLifecycle(unittest.TestCase):
    def setUp(self):
        self.ws, _ = make_stores()

    def test_versions_increment_per_opportunity(self):
        v1 = self.ws.create_version(OPP["id"], "first_analysis")
        v2 = self.ws.create_version(OPP["id"], "manual_refresh")
        other = self.ws.create_version("UOPP-bbbbbbbbbbb2", "first_analysis")
        self.assertEqual((v1["version"], v2["version"], other["version"]), (1, 2, 1))
        self.assertEqual(v1["status"], "running")

    def test_terminal_versions_are_immutable(self):
        v = self.ws.create_version(OPP["id"], "first_analysis")
        self.ws.complete_version(v["id"], gaps=["g"])
        with self.assertRaises(WorkspaceStoreError) as cm:
            self.ws.fail_version(v["id"], "nope")
        self.assertEqual(cm.exception.status, 409)

    def test_failed_version_requires_a_reason(self):
        v = self.ws.create_version(OPP["id"], "stale")
        with self.assertRaises(WorkspaceStoreError):
            self.ws.fail_version(v["id"], "")

    def test_invalid_trigger_and_ref_rejected(self):
        with self.assertRaises(WorkspaceStoreError):
            self.ws.create_version(OPP["id"], "ordinary_chat_message")
        with self.assertRaises(WorkspaceStoreError):
            self.ws.create_version("OPP-10", "manual_refresh")

    def test_latest_returns_newest_complete_only(self):
        self.assertIsNone(self.ws.latest(OPP["id"]))
        v1 = self.ws.create_version(OPP["id"], "first_analysis")
        self.ws.complete_version(v1["id"], claim_ids=["RCAND-1"])
        v2 = self.ws.create_version(OPP["id"], "manual_refresh")  # still running
        latest = self.ws.latest(OPP["id"])
        self.assertEqual(latest["id"], v1["id"])            # readers never see 'running'
        self.ws.fail_version(v2["id"], "provider exploded")
        self.assertEqual(self.ws.latest(OPP["id"])["id"], v1["id"])

    def test_prune_keeps_newest_n(self):
        for i in range(5):
            v = self.ws.create_version(OPP["id"], "manual_refresh")
            self.ws.complete_version(v["id"])
        removed = self.ws.prune(OPP["id"], keep=2)
        self.assertEqual(removed, 3)
        versions = self.ws.list_versions(OPP["id"])
        self.assertEqual([v["version"] for v in versions], [5, 4])

    def test_staleness_is_deterministic_from_completed_at(self):
        v = self.ws.create_version(OPP["id"], "first_analysis")
        v = self.ws.complete_version(v["id"])
        self.assertFalse(self.ws.is_stale(v, stale_hours=24))
        self.assertTrue(self.ws.is_stale(v, stale_hours=0))
        self.assertTrue(self.ws.is_stale({"completed_at": None}, stale_hours=24))


class BuildQueries(unittest.TestCase):
    def test_queries_derive_only_from_the_opportunity_fields(self):
        qs = build_queries(OPP, question="is settlement speed a real pain?")
        joined = " | ".join(q for _, q in qs)
        self.assertIn("Cross-border payroll tool", joined)
        self.assertIn("regional SMEs", joined)
        self.assertIn("settlement speed", joined)
        # nothing hardcodes a market/product the opportunity never mentioned
        self.assertNotIn("UAE", joined)
        self.assertNotIn("credit card", joined.lower())

    def test_bare_opportunity_yields_no_queries(self):
        self.assertEqual(build_queries({"id": "UOPP-aaaaaaaaaaa1"}), [])


class BuildChain(unittest.TestCase):
    def setUp(self):
        self.ws, self.rs = make_stores()

    def test_full_chain_with_injected_providers(self):
        search = AnyQuerySearch()

        # the extractor must cite a real source id from THIS run — resolve it
        # at generate time by peeking at the run the builder created
        def payload():
            runs = self.rs.list_runs()
            detail = self.rs.get_run(runs[0]["id"], include_children=True)
            # cite the primary (non-duplicate) source — the one carrying the
            # stored excerpt the validator checks quotes against
            sid = next(s["id"] for s in detail["sources"]
                       if not s.get("duplicate_of") and s.get("excerpt"))
            return json.dumps({"claims": [{
                "claim": "Settlement takes 4 days on average for the segment.",
                "sources": [{"source_id": sid,
                             "supporting_quote": "Settlement takes 4 days on average"}]}]})
        llm = StubExtractor(payload)

        v = build_workspace(self.ws, self.rs, OPP, trigger="first_analysis",
                            question="is settlement speed a pain?",
                            search_provider=search, llm_provider=llm,
                            llm_config=_Cfg(), kb_records={},
                            execute_run_fn=_execute)
        self.assertEqual(v["status"], "complete")
        self.assertEqual(len(v["claim_ids"]), 1)
        self.assertTrue(v["research_run_id"].startswith("RRUN-"))
        # the extracted claim is pending_review in the research store — the
        # workspace never shortcuts human review
        cand = self.rs.get_run(v["research_run_id"],
                               include_children=True)["candidate_evidence"][0]
        self.assertEqual(cand["status"], "pending_review")
        self.assertEqual(cand["origin"], "extracted")
        # provenance is first-class
        self.assertEqual(v["provenance"]["research_run_id"], v["research_run_id"])
        self.assertEqual(v["provenance"]["extraction_model"], "stub-llm")
        self.assertEqual(v["provenance"]["trigger"], "first_analysis")

    def test_preliminary_score_comes_from_the_real_engine_and_is_capped(self):
        v = build_workspace(self.ws, self.rs, OPP, trigger="first_analysis",
                            kb_records={})
        score = v["preliminary_score"]
        self.assertTrue(score["preliminary"])
        self.assertEqual(score["engine"], "opportunity_engine.scoring")
        self.assertEqual(score["assumption_count"], 17)
        self.assertTrue(score["assumption_capped"])
        self.assertEqual(score["max_classification"], "promising")  # engine cap
        self.assertEqual(score["confidence"], "low")

    def test_missing_providers_become_honest_gaps_not_failures(self):
        v = build_workspace(self.ws, self.rs, OPP, trigger="manual_refresh",
                            kb_records={})
        self.assertEqual(v["status"], "complete")
        gaps = " | ".join(v["gaps"])
        self.assertIn("no search provider configured", gaps)
        self.assertIn("no related internal evidence", gaps)
        self.assertEqual(v["claim_ids"], [])
        self.assertIsNone(v["research_run_id"])

    def test_search_without_llm_records_sources_but_flags_extraction_gap(self):
        search = AnyQuerySearch()
        v = build_workspace(self.ws, self.rs, OPP, trigger="manual_refresh",
                            search_provider=search, kb_records={},
                            execute_run_fn=_execute)
        self.assertEqual(v["status"], "complete")
        self.assertIn("claim extraction skipped", " | ".join(v["gaps"]))
        detail = self.rs.get_run(v["research_run_id"], include_children=True)
        self.assertGreater(len(detail["sources"]), 0)

    def test_kb_matches_are_recorded_with_ids(self):
        records = {"EV-2026-W01-001": {
            "id": "EV-2026-W01-001", "title": "Payroll settlement complaints",
            "segment": "SEG-x", "status": "active",
            "evidence_confidence": "Medium — survey", "excerpt": "payroll settlement slow"}}
        v = build_workspace(self.ws, self.rs, OPP, trigger="first_analysis",
                            kb_records=records)
        self.assertEqual(v["kb_evidence"][0]["id"], "EV-2026-W01-001")
        self.assertEqual(v["provenance"]["kb_record_ids"], ["EV-2026-W01-001"])

    def test_build_crash_fails_the_version_honestly(self):
        class ExplodingStore:
            def create_run(self, payload):
                raise RuntimeError("disk on fire")
        search = AnyQuerySearch()
        with self.assertRaises(RuntimeError):
            build_workspace(self.ws, ExplodingStore(), OPP, trigger="manual_refresh",
                            search_provider=search, kb_records={})
        versions = self.ws.list_versions(OPP["id"])
        self.assertEqual(versions[0]["status"], "failed")
        self.assertIn("disk on fire", versions[0]["error"])


class CompareVersions(unittest.TestCase):
    def test_diff_surfaces_new_claims_and_resolved_gaps(self):
        older = {"id": "AWV-1", "claim_ids": ["RCAND-a"], "gaps": ["g1", "g2"],
                 "preliminary_score": {"composite": 3.0}}
        newer = {"id": "AWV-2", "claim_ids": ["RCAND-a", "RCAND-b"], "gaps": ["g2"],
                 "preliminary_score": {"composite": 3.0}}
        diff = compare_versions(older, newer)
        self.assertEqual(diff["new_claim_ids"], ["RCAND-b"])
        self.assertEqual(diff["resolved_gaps"], ["g1"])
        self.assertEqual(diff["composite_delta"], 0.0)

    def test_diff_with_missing_scores_is_honest_none(self):
        diff = compare_versions({"id": "a"}, {"id": "b"})
        self.assertIsNone(diff["composite_delta"])


if __name__ == "__main__":
    unittest.main()
