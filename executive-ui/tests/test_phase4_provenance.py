"""Phase 4 — adapter provenance/freshness/link enrichment, against the live
repository (read-only). The EvidenceRef contract must carry real source
metadata, a deterministic freshness status, safe URLs only, and honest
reverse links — never invented values."""

import sys
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
REPO = UI.parents[0]
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from adapter import collect  # noqa: E402


class TestEvidenceProvenance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = collect.build_model(str(REPO))
        cls.by_id = {e.ev_id: e for e in cls.m.evidence}

    def test_resolved_records_carry_dates(self):
        for e in self.m.evidence:
            if e.resolved:
                self.assertIsNotNone(e.created_at, e.ev_id)
                self.assertIsNotNone(e.last_verified_at, e.ev_id)

    def test_source_metadata_present_where_recorded(self):
        e = self.by_id["EV-2026-W28-001"]
        self.assertEqual(e.publisher, "Trustpilot")
        self.assertEqual(e.source_title, "Trustpilot — Telr")
        self.assertEqual(e.source_url, "https://trustpilot.com/review/www.telr.com")
        self.assertEqual(e.access_label, "search-snippet")
        self.assertTrue(e.excerpt and "held for more than 2 months" in e.excerpt)

    def test_no_url_record_stays_none(self):
        e = self.by_id["EV-2026-W28-013"]
        self.assertIsNone(e.source_url)

    def test_all_urls_are_http_https_and_never_local_paths(self):
        for e in self.m.evidence:
            if e.source_url is not None:
                self.assertRegex(e.source_url, r"^https?://", e.ev_id)
                self.assertNotIn("knowledge-base", e.source_url, e.ev_id)

    def test_freshness_fields_always_present_and_banded(self):
        for e in self.m.evidence:
            self.assertIn(e.freshness_status, ("fresh", "aging", "stale", "unknown"), e.ev_id)
            self.assertTrue(e.freshness_reason, e.ev_id)
            if e.resolved:
                self.assertIsNotNone(e.freshness_reference_date, e.ev_id)
                self.assertIsInstance(e.freshness_age_days, int, e.ev_id)

    def test_unresolved_citation_freshness_is_unknown(self):
        unresolved = [e for e in self.m.evidence if not e.resolved]
        for e in unresolved:
            self.assertEqual(e.freshness_status, "unknown")
            self.assertIsNone(e.freshness_reference_date)

    def test_multiple_linked_opportunities_and_assumptions(self):
        linked_opps = {o for e in self.m.evidence for o in e.linked_opportunity_ids}
        self.assertGreaterEqual(len(linked_opps), 2, "evidence must link to >1 opportunity overall")
        with_asm = [e for e in self.m.evidence if e.linked_assumption_ids]
        self.assertTrue(with_asm, "some evidence must link to assumptions")
        for e in with_asm:
            for aid in e.linked_assumption_ids:
                opp_id, _, factor = aid.partition("::")
                self.assertRegex(opp_id, r"^OPP-\d{3}$")
                self.assertTrue(factor)
                # the target must actually exist in the assumption table
                self.assertTrue(any(a.opportunity_id == opp_id and a.factor_key == factor
                                    for a in self.m.assumptions), aid)

    def test_links_are_real_citations_not_invented(self):
        for e in self.m.evidence:
            for oid in e.linked_opportunity_ids:
                opp = next(o for o, in [(o,) for o in self.m.opportunities + self.m.archived]
                           if o.id == oid)
                cited = {i for f in opp.factors for i in f.evidence_ids}
                self.assertIn(e.ev_id, cited, f"{e.ev_id} not actually cited by {oid}")

    def test_no_local_filesystem_path_in_serialized_evidence(self):
        import json
        from dataclasses import asdict
        blob = json.dumps([asdict(e) for e in self.m.evidence])
        self.assertNotIn("/home/", blob)
        self.assertNotIn("file://", blob)


if __name__ == "__main__":
    unittest.main()
