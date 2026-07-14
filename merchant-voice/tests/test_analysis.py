"""Campaign-level analysis tests: numerator/denominator correctness,
segment separation, no bare percentages, contradiction preservation,
follow-up question surfacing, and viewer-level detail stripping."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (RESEARCHER, REVIEWER, make_active_campaign_with_approved_guide, make_approved_observation,
                      make_dbs, make_observation, make_participant, make_response)

from app import analysis, candidates, observation_review


class CampaignAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn, self.identity_conn, self.config = make_dbs(self.tmp.name)
        self.clock_n = 0
        self.camp, self.guide = make_active_campaign_with_approved_guide(self.conn, self.config, self._clock)

    def _clock(self):
        self.clock_n += 1
        return f"2026-01-01T00:00:{self.clock_n:02d}Z"

    def _approved(self, text, **overrides):
        return make_approved_observation(self.conn, self.identity_conn, self.config, self._clock, self.camp,
                                         self.guide, text, **overrides)

    def test_numerator_denominator_present_for_every_category(self):
        self._approved("Suppliers cancel late payments weekly.")
        result = analysis.compute_campaign_analysis(self.conn, self.camp["campaign_id"])
        self.assertEqual(result["included_participant_count"], 1)
        for segment_id, categories in result["segments"].items():
            for name, entry in categories.items():
                self.assertIn("numerator", entry)
                self.assertIn("denominator", entry)
                self.assertIn("denominator_definition", entry)
                self.assertEqual(entry["campaign_id"], self.camp["campaign_id"])
                self.assertEqual(entry["method"], "interview")
                self.assertIn("contradiction_count", entry)

    def test_example_wording_three_of_eight_included_interviewed_merchants(self):
        for i in range(8):
            participant = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                           self.camp["campaign_id"])
            response = make_response(self.conn, self.config, self._clock, self.camp, self.guide, participant,
                                     [{"question_id": self.guide["questions"][0]["question_id"],
                                       "answer": f"Filler answer number {i}."}])
            if i < 3:
                obs = make_observation(self.conn, self.config, self._clock, response, 0,
                                       f"Filler answer number {i}.")
                observation_review.approve(self.conn, self.config, REVIEWER, obs["observation_id"], self._clock())
        result = analysis.compute_campaign_analysis(self.conn, self.camp["campaign_id"])
        pain_entry = next(iter(result["segments"].values()))["recurring_pains"]
        self.assertEqual(pain_entry["numerator"], 3)
        self.assertEqual(pain_entry["denominator"], 8)
        wording = (f"{pain_entry['numerator']} of {pain_entry['denominator']} included {result['method']}ed "
                  f"merchants in {result['campaign_id']}")
        self.assertIn("3 of 8", wording)

    def test_analysis_never_returns_a_bare_percentage(self):
        self._approved("Suppliers cancel late payments weekly.")
        result = analysis.compute_campaign_analysis(self.conn, self.camp["campaign_id"])
        blob = str(result)
        self.assertNotIn("%", blob)

    def test_segments_never_silently_pooled(self):
        p1 = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                              self.camp["campaign_id"], segment_id="SEG-alpha")
        p2 = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                              self.camp["campaign_id"], segment_id="SEG-beta")
        self._approved("Suppliers in segment alpha cancel late payments.", participant=p1)
        self._approved("Suppliers in segment beta cancel late payments too.", participant=p2)
        result = analysis.compute_campaign_analysis(self.conn, self.camp["campaign_id"])
        self.assertEqual(set(result["segments"].keys()), {"SEG-alpha", "SEG-beta"})
        self.assertEqual(result["segments"]["SEG-alpha"]["recurring_pains"]["numerator"], 1)
        self.assertEqual(result["segments"]["SEG-beta"]["recurring_pains"]["numerator"], 1)
        self.assertIn("never", result["grouping_note"])

    def test_method_is_structural_via_single_campaign_scope(self):
        result = analysis.compute_campaign_analysis(self.conn, self.camp["campaign_id"])
        self.assertEqual(result["method"], self.camp["method"])

    def test_contradictions_preserved_and_counted(self):
        obs1, _, _ = self._approved("We would pay for a solution to this.",
                                    observation_type="willingness_to_pay_signal")
        participant2 = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                        self.camp["campaign_id"])
        response2 = make_response(self.conn, self.config, self._clock, self.camp, self.guide, participant2,
                                  [{"question_id": self.guide["questions"][0]["question_id"],
                                    "answer": "We would never pay for anything like this."}])
        contra = make_observation(self.conn, self.config, self._clock, response2, 0,
                                  "We would never pay for anything like this.",
                                  observation_type="contradiction")
        contra = observation_review.edit(self.conn, RESEARCHER, contra["observation_id"],
                                         {"contradiction_target": obs1["observation_id"]}, self._clock())
        observation_review.approve(self.conn, self.config, REVIEWER, contra["observation_id"], self._clock())
        result = analysis.compute_campaign_analysis(self.conn, self.camp["campaign_id"])
        wtp_entry = next(iter(result["segments"].values()))["wtp_signals"]
        contradiction_entry = next(iter(result["segments"].values()))["contradictions"]
        self.assertEqual(contradiction_entry["numerator"], 1)
        self.assertEqual(contradiction_entry["observation_count"], 1)
        self.assertEqual(wtp_entry["numerator"], 1)

    def test_unanswered_follow_up_questions_surfaced(self):
        participant = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                       self.camp["campaign_id"])
        response = make_response(self.conn, self.config, self._clock, self.camp, self.guide, participant,
                                 [{"question_id": self.guide["questions"][0]["question_id"],
                                   "answer": "This raises a question we should follow up on."}])
        obs = make_observation(self.conn, self.config, self._clock, response, 0,
                               "This raises a question we should follow up on.",
                               observation_type="follow_up_question",
                               follow_up_question="Should we ask about refund timelines?")
        observation_review.approve(self.conn, self.config, REVIEWER, obs["observation_id"], self._clock())
        result = analysis.compute_campaign_analysis(self.conn, self.camp["campaign_id"])
        self.assertEqual(result["unanswered_follow_up_questions"]["count"], 1)
        self.assertIn("refund timelines", result["unanswered_follow_up_questions"]["questions"][0])

    def test_findings_grouped_by_strength_band(self):
        obs, _, _ = self._approved("Suppliers cancel late payments weekly.")
        candidate = candidates.create(self.conn, RESEARCHER, self.config, {
            "campaign_id": self.camp["campaign_id"], "finding_type": "pain",
            "statement": "Suppliers cancel late payments.", "proposed_evidence_role": "supporting",
            "observations": [{"observation_id": obs["observation_id"], "role": "supporting"}]}, self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        candidates.approve(self.conn, self.config, REVIEWER, candidate["candidate_id"], self._clock())
        result = analysis.compute_campaign_analysis(self.conn, self.camp["campaign_id"])
        self.assertEqual(result["findings_by_strength_band"].get("single_signal"), 1)

    def test_viewer_level_detail_strips_sample_statements_and_questions(self):
        self._approved("Suppliers cancel late payments weekly.")
        detailed = analysis.compute_campaign_analysis(self.conn, self.camp["campaign_id"], include_detail=True)
        stripped = analysis.compute_campaign_analysis(self.conn, self.camp["campaign_id"], include_detail=False)
        pain_detailed = next(iter(detailed["segments"].values()))["recurring_pains"]
        pain_stripped = next(iter(stripped["segments"].values()))["recurring_pains"]
        self.assertIn("sample_statements", pain_detailed)
        self.assertNotIn("sample_statements", pain_stripped)
        self.assertNotIn("questions", stripped["unanswered_follow_up_questions"])
        self.assertEqual(pain_stripped["numerator"], pain_detailed["numerator"])

    def test_rejected_and_pending_observations_excluded_from_categories(self):
        participant = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                       self.camp["campaign_id"])
        response = make_response(self.conn, self.config, self._clock, self.camp, self.guide, participant,
                                 [{"question_id": self.guide["questions"][0]["question_id"],
                                   "answer": "Suppliers cancel late payments weekly."}])
        obs = make_observation(self.conn, self.config, self._clock, response, 0,
                               "Suppliers cancel late payments weekly.")
        observation_review.reject(self.conn, REVIEWER, obs["observation_id"], "duplicate", self._clock())
        result = analysis.compute_campaign_analysis(self.conn, self.camp["campaign_id"])
        self.assertEqual(result["rejected_observation_count"], 1)
        self.assertEqual(result["segments"], {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
