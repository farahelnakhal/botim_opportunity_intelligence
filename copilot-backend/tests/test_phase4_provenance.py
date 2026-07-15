"""Phase 4 — copilot-backend evidence provenance, freshness metadata, and
deterministic stale-evidence warnings. All read-only against the live repo;
stale-warning tests use synthetic tool results so the assertions do not
depend on the current calendar date."""

import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from app import grounding, tools_registry  # noqa: E402


class TestEvidenceRecordProvenance(unittest.TestCase):
    def test_full_source_metadata_extraction(self):
        r = tools_registry.call_tool("get_evidence_record", {"ev_id": "EV-2026-W28-001"})
        p = r["provenance"]
        self.assertEqual(p["source_title"], "Trustpilot — Telr")
        self.assertEqual(p["publisher"], "Trustpilot")
        self.assertEqual(p["source_url"], "https://trustpilot.com/review/www.telr.com")
        self.assertEqual(p["retrieved_at"], "2026-07-10")
        self.assertEqual(p["created_at"], "2026-07-10")
        self.assertEqual(p["last_verified_at"], "2026-07-10")
        self.assertEqual(p["access_label"], "search-snippet")
        self.assertIn("held for more than 2 months", p["excerpt"])
        self.assertIn(p["freshness_status"], ("fresh", "aging", "stale"))
        self.assertTrue(p["freshness_reason"])

    def test_record_without_external_url_returns_none(self):
        r = tools_registry.call_tool("get_evidence_record", {"ev_id": "EV-2026-W28-013"})
        self.assertIsNone(r["provenance"]["source_url"])

    def test_provenance_urls_are_http_https_only_and_no_paths(self):
        import json
        records = tools_registry._records()
        for ev_id in records:
            r = tools_registry.call_tool("get_evidence_record", {"ev_id": ev_id})
            p = r["provenance"]
            if p["source_url"] is not None:
                self.assertRegex(p["source_url"], r"^https?://", ev_id)
            blob = json.dumps(p)
            self.assertNotIn("/home/", blob, ev_id)
            self.assertNotIn("file://", blob, ev_id)
            self.assertNotIn("knowledge-base/", blob, ev_id)

    def test_opportunity_view_includes_evidence_freshness(self):
        r = tools_registry.call_tool("get_opportunity", {"opp_id": "OPP-013"})
        self.assertTrue(r["evidence_freshness"])
        for ev_id, f in r["evidence_freshness"].items():
            self.assertIn(f["freshness_status"], ("fresh", "aging", "stale", "unknown"), ev_id)
            self.assertTrue(f["freshness_reason"], ev_id)


def _stale_record_result(ev_id="EV-2026-W28-001"):
    return ("get_evidence_record", {
        "ev_id": ev_id, "title": "Old evidence", "status": "active",
        "evidence_confidence": "Low — old", "segment": "", "pain_category": "",
        "workaround": "", "contradictory_evidence": "", "scores": {},
        "is_weak_lead": False,
        "provenance": {
            "source_title": "Trustpilot — Example", "source_url": "https://example.com/r",
            "publisher": "Trustpilot", "publication_date": None,
            "date_of_evidence": None, "retrieved_at": "2025-12-01",
            "created_at": "2025-12-01", "last_verified_at": "2025-12-13",
            "excerpt": "quote", "access_label": "direct",
            "freshness_status": "stale", "freshness_reference_date": "2025-12-13",
            "freshness_age_days": 214,
            "freshness_reason": "Last verified 214 days ago. Older than the 180-day staleness threshold.",
        }})


class TestStaleWarnings(unittest.TestCase):
    def test_stale_warning_is_grounded_in_deterministic_metadata(self):
        pack = grounding.build("evidence_lookup", [_stale_record_result()], {})
        stale = [w for w in pack.warnings if "stale" in w]
        self.assertEqual(len(stale), 1)
        self.assertIn("EV-2026-W28-001 was last verified 214 days ago", stale[0])
        self.assertNotIn("freshly checked", stale[0].lower())

    def test_duplicate_citations_produce_one_warning(self):
        executed = [_stale_record_result(), _stale_record_result(),
                    ("get_opportunity", {
                        "opportunity_id": "OPP-999", "name": "X",
                        "score": {"raw_score": 1, "composite_score": 1, "classification": "weak",
                                  "capped": False, "assumption_count": 0, "assumption_cap": 9,
                                  "critical_flags": []},
                        "customer": {}, "confidence": {},
                        "supporting_primary": ["EV-2026-W28-001"], "supporting_leads": [],
                        "contradicting": [], "risks": [], "next_validation": {},
                        "assumptions": {"unresolved": 0, "total": 0}, "inflection_points": {},
                        "evidence_freshness": {"EV-2026-W28-001": {
                            "freshness_status": "stale", "freshness_reason": "Last verified 214 days ago.",
                            "freshness_age_days": 214, "last_verified_at": "2025-12-13"}},
                    })]
        pack = grounding.build("evidence_lookup", executed, {})
        stale = [w for w in pack.warnings if "stale" in w and "EV-2026-W28-001" in w]
        self.assertEqual(len(stale), 1, pack.warnings)

    def test_fresh_evidence_produces_no_stale_warning(self):
        rec = _stale_record_result()
        rec[1]["provenance"].update({"freshness_status": "fresh", "freshness_age_days": 3,
                                     "freshness_reason": "Last verified 3 days ago."})
        pack = grounding.build("evidence_lookup", [rec], {})
        self.assertFalse([w for w in pack.warnings if "stale" in w])

    def test_citation_metadata_is_bounded_and_safe(self):
        pack = grounding.build("evidence_lookup", [_stale_record_result()], {})
        meta = pack.citations["EV-2026-W28-001"]["metadata"]
        self.assertEqual(meta["source_url"], "https://example.com/r")
        self.assertEqual(meta["freshness_status"], "stale")
        allowed = set(grounding._EVIDENCE_META_FIELDS) | {"excerpt"}
        self.assertLessEqual(set(meta), allowed)


class TestLiveRepoCitationMetadata(unittest.TestCase):
    def test_real_record_citation_gets_metadata(self):
        executed = [("get_evidence_record",
                     tools_registry.call_tool("get_evidence_record", {"ev_id": "EV-2026-W28-001"}))]
        pack = grounding.build("evidence_lookup", executed, {})
        meta = pack.citations["EV-2026-W28-001"]["metadata"]
        self.assertEqual(meta["publisher"], "Trustpilot")
        self.assertRegex(meta["source_url"], r"^https://")


if __name__ == "__main__":
    unittest.main()
