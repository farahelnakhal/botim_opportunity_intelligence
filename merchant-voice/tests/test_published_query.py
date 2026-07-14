"""Read-only published-query-layer tests: only approved+published findings
surface, unreviewed/rejected/suppressed/needs_revalidation content never
does, withdrawn-participant content disappears immediately, no identity
fields or raw transcript content leak, and segment/opportunity/assumption/
campaign-limitations filters behave correctly."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (ADMIN, RESEARCHER, REVIEWER, make_active_campaign_with_approved_guide,
                      make_approved_observation, make_dbs, make_observation, make_participant, make_response)

from app import candidates, findings, observation_review, published_query, suppression


class PublishedQueryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn, self.identity_conn, self.config = make_dbs(self.tmp.name)
        self.clock_n = 0
        self.camp, self.guide = make_active_campaign_with_approved_guide(
            self.conn, self.config, self._clock, campaign_overrides={"linked_opportunities": ["OPP-013"],
                                                                     "linked_assumptions": ["ASM-OPP-013-wtp"]})

    def _clock(self):
        self.clock_n += 1
        return f"2026-01-01T00:00:{self.clock_n:02d}Z"

    def _approved(self, text, **overrides):
        return make_approved_observation(self.conn, self.identity_conn, self.config, self._clock, self.camp,
                                         self.guide, text, **overrides)

    def _published_finding(self, text="Suppliers cancel late payments every week.", **overrides):
        obs, participant, _ = self._approved(text, **overrides)
        candidate = candidates.create(self.conn, RESEARCHER, self.config, {
            "campaign_id": self.camp["campaign_id"], "finding_type": "pain",
            "statement": "Suppliers cancel late payments.", "proposed_evidence_role": "supporting",
            "linked_opportunities": ["OPP-013"], "linked_assumptions": ["ASM-OPP-013-wtp"],
            "observations": [{"observation_id": obs["observation_id"], "role": "supporting"}]}, self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        _approved_candidate, finding = candidates.approve(self.conn, self.config, REVIEWER,
                                                          candidate["candidate_id"], self._clock())
        findings.publish(self.conn, REVIEWER, finding["finding_id"], self._clock())
        return finding, participant

    def test_only_approved_published_findings_returned(self):
        finding, _ = self._published_finding()
        results = published_query.list_findings(self.conn)
        self.assertEqual([f["finding_id"] for f in results], [finding["finding_id"]])

    def test_unpublished_excluded(self):
        obs, _, _ = self._approved("Suppliers cancel late payments every week.")
        candidate = candidates.create(self.conn, RESEARCHER, self.config, {
            "campaign_id": self.camp["campaign_id"], "finding_type": "pain",
            "statement": "Suppliers cancel late payments.", "proposed_evidence_role": "supporting",
            "observations": [{"observation_id": obs["observation_id"], "role": "supporting"}]}, self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        candidates.approve(self.conn, self.config, REVIEWER, candidate["candidate_id"], self._clock())
        self.assertEqual(published_query.list_findings(self.conn), [])

    def test_needs_revalidation_excluded(self):
        finding, participant = self._published_finding()
        # a second, independent 2-supporter finding: withdrawing ONE of its
        # two supporters leaves it needs_revalidation (not suppressed),
        # while the untouched single-supporter finding above stays published
        obs1, p1, _ = self._approved("Two-supporter A: suppliers cancel payments.")
        obs2, p2, _ = self._approved("Two-supporter B: suppliers cancel payments.")
        candidate2 = candidates.create(self.conn, RESEARCHER, self.config, {
            "campaign_id": self.camp["campaign_id"], "finding_type": "pain",
            "statement": "Two-supporter finding.", "proposed_evidence_role": "supporting",
            "observations": [{"observation_id": obs1["observation_id"], "role": "supporting"},
                             {"observation_id": obs2["observation_id"], "role": "supporting"}]}, self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate2["candidate_id"], self._clock())
        _approved2, finding2 = candidates.approve(self.conn, self.config, REVIEWER, candidate2["candidate_id"],
                                                  self._clock())
        findings.publish(self.conn, REVIEWER, finding2["finding_id"], self._clock())
        suppression.suppress_participant(self.conn, ADMIN, p1["participant_id"], "withdrawn", self._clock())
        after = findings.get(self.conn, finding2["finding_id"])
        self.assertEqual(after["publication_status"], "needs_revalidation")
        ids = [f["finding_id"] for f in published_query.list_findings(self.conn)]
        self.assertNotIn(finding2["finding_id"], ids)
        self.assertIn(finding["finding_id"], ids)  # the untouched finding still surfaces

    def test_suppressed_excluded(self):
        finding, participant = self._published_finding()
        findings.suppress(self.conn, REVIEWER, finding["finding_id"], self._clock())
        self.assertEqual(published_query.list_findings(self.conn), [])

    def test_withdrawn_participant_content_excluded(self):
        finding, participant = self._published_finding()
        suppression.suppress_participant(self.conn, ADMIN, participant["participant_id"], "withdrawn",
                                         self._clock())
        self.assertEqual(published_query.list_findings(self.conn), [])

    def test_identity_fields_absent(self):
        finding, participant = self._published_finding()
        result = published_query.list_findings(self.conn)
        blob = str(result)
        self.assertNotIn(participant["merchant_identity_id"], blob)
        self.assertNotIn(participant["participant_id"], blob)

    def test_raw_transcript_absent(self):
        finding, _ = self._published_finding()
        result = published_query.get_campaign_summary(self.conn, self.camp["campaign_id"])
        self.assertNotIn("transcript", str(result).lower())

    def test_unreviewed_observations_absent(self):
        finding, _ = self._published_finding()
        participant2 = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                        self.camp["campaign_id"])
        response2 = make_response(self.conn, self.config, self._clock, self.camp, self.guide, participant2,
                                  [{"question_id": self.guide["questions"][0]["question_id"],
                                    "answer": "An unreviewed pending statement."}])
        pending_obs = make_observation(self.conn, self.config, self._clock, response2, 0,
                                       "An unreviewed pending statement.")
        blob = str(published_query.get_campaign_summary(self.conn, self.camp["campaign_id"]))
        self.assertNotIn("An unreviewed pending statement.", blob)
        self.assertNotIn(pending_obs["observation_id"], blob)

    def test_prohibited_quotes_absent(self):
        from app import participants as participants_module
        finding, participant = self._published_finding(
            text="Suppliers cancel late payments every week.", is_direct_quote=True,
            normalized_statement="Suppliers cancel late payments every week.")
        participants_module.update(self.conn, self.identity_conn, self.config, RESEARCHER,
                                   participant["participant_id"], {"quote_permission": False}, self._clock())
        quotes = published_query.get_merchant_quotes(self.conn, self._clock(), campaign_id=self.camp["campaign_id"])
        self.assertEqual(quotes, [])

    def test_segment_filter_correct(self):
        p1 = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                              self.camp["campaign_id"], segment_id="SEG-alpha")
        finding, _ = self._published_finding(text="Alpha segment supplier pain.", participant=p1)
        results = published_query.list_findings(self.conn, segment_id="SEG-alpha")
        self.assertEqual([f["finding_id"] for f in results], [finding["finding_id"]])
        self.assertEqual(published_query.list_findings(self.conn, segment_id="SEG-beta"), [])

    def test_opportunity_filter_correct(self):
        finding, _ = self._published_finding()
        results = published_query.list_findings(self.conn, opportunity_id="OPP-013")
        self.assertEqual([f["finding_id"] for f in results], [finding["finding_id"]])
        self.assertEqual(published_query.list_findings(self.conn, opportunity_id="OPP-999"), [])

    def test_assumption_filter_correct(self):
        finding, _ = self._published_finding()
        results = published_query.list_findings(self.conn, assumption_id="ASM-OPP-013-wtp")
        self.assertEqual([f["finding_id"] for f in results], [finding["finding_id"]])

    def test_campaign_limitations_returned(self):
        finding, _ = self._published_finding()
        result = published_query.get_campaign_limitations(self.conn, self.camp["campaign_id"])
        self.assertEqual(result["campaign_id"], self.camp["campaign_id"])
        self.assertIsInstance(result["limitations"], list)

    def test_never_opens_identity_db(self):
        import inspect
        source = inspect.getsource(published_query)
        self.assertNotIn("identity_conn", source)
        self.assertNotIn("connect_identity", source)
        self.assertNotIn("import identity", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
