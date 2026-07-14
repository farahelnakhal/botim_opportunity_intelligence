"""Evidence candidate tests: creation from approved observations, structural
support/contradiction/segment/method checks, known-contradiction exclusion,
draft editing, submit/approve/reject workflow, self-approval separation,
staleness detection, immutability once approved."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (ADMIN, RESEARCHER, REVIEWER, make_active_campaign_with_approved_guide,
                      make_approved_observation, make_dbs, make_observation, make_participant, make_response)

from app import candidates, findings, observation_review
from app.models import Phase4Error, ValidationError


class CandidateTests(unittest.TestCase):
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
        obs, participant, response = make_approved_observation(
            self.conn, self.identity_conn, self.config, self._clock, self.camp, self.guide, text, **overrides)
        return obs, participant, response

    def _approved_contradicting(self, text, target_observation_id, **overrides):
        """Creates a pending observation, sets contradiction_target via
        edit() (campaign-scoped, so it may point at a different response's
        observation), then approves it."""
        participant = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                       self.camp["campaign_id"])
        response = make_response(self.conn, self.config, self._clock, self.camp, self.guide, participant,
                                 [{"question_id": self.guide["questions"][0]["question_id"], "answer": text}])
        obs = make_observation(self.conn, self.config, self._clock, response, 0, text, **overrides)
        obs = observation_review.edit(self.conn, RESEARCHER, obs["observation_id"],
                                      {"contradiction_target": target_observation_id}, self._clock())
        approved = observation_review.approve(self.conn, self.config, REVIEWER, obs["observation_id"],
                                              self._clock())
        return approved, participant, response

    def _base_data(self, observations, **overrides):
        data = {
            "campaign_id": self.camp["campaign_id"], "finding_type": "pain",
            "statement": "Suppliers cancel late payments frequently.",
            "proposed_evidence_role": "supporting", "observations": observations,
        }
        data.update(overrides)
        return data

    def test_candidate_created_from_approved_observations(self):
        obs, _, _ = self._approved("Suppliers cancel late payments every week.")
        candidate = candidates.create(self.conn, RESEARCHER, self.config,
                                      self._base_data([{"observation_id": obs["observation_id"],
                                                        "role": "supporting"}]), self._clock())
        self.assertEqual(candidate["workflow_status"], "draft")
        self.assertEqual(candidate["support_count"], 1)
        self.assertEqual(candidate["included_participant_count"], 1)

    def test_pending_observation_cannot_be_used(self):
        participant = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                       self.camp["campaign_id"])
        response = make_response(self.conn, self.config, self._clock, self.camp, self.guide, participant,
                                 [{"question_id": self.guide["questions"][0]["question_id"],
                                   "answer": "Suppliers cancel late payments every week."}])
        pending_obs = make_observation(self.conn, self.config, self._clock, response, 0,
                                       "Suppliers cancel late payments every week.")
        with self.assertRaises(Phase4Error) as ctx:
            candidates.create(self.conn, RESEARCHER, self.config,
                              self._base_data([{"observation_id": pending_obs["observation_id"],
                                                "role": "supporting"}]), self._clock())
        self.assertEqual(ctx.exception.code, "observation_not_approved")

    def test_rejected_observation_cannot_be_used(self):
        participant = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                       self.camp["campaign_id"])
        response = make_response(self.conn, self.config, self._clock, self.camp, self.guide, participant,
                                 [{"question_id": self.guide["questions"][0]["question_id"],
                                   "answer": "Suppliers cancel late payments every week."}])
        obs = make_observation(self.conn, self.config, self._clock, response, 0,
                               "Suppliers cancel late payments every week.")
        observation_review.reject(self.conn, REVIEWER, obs["observation_id"], "duplicate", self._clock())
        with self.assertRaises(Phase4Error) as ctx:
            candidates.create(self.conn, RESEARCHER, self.config,
                              self._base_data([{"observation_id": obs["observation_id"],
                                                "role": "supporting"}]), self._clock())
        self.assertEqual(ctx.exception.code, "observation_not_approved")

    def test_suppressed_observation_cannot_be_used(self):
        from app import suppression
        obs, participant, _ = self._approved("Suppliers cancel late payments every week.")
        suppression.suppress_participant(self.conn, ADMIN, participant["participant_id"], "withdrawn",
                                         self._clock())
        with self.assertRaises(Phase4Error) as ctx:
            candidates.create(self.conn, RESEARCHER, self.config,
                              self._base_data([{"observation_id": obs["observation_id"],
                                                "role": "supporting"}]), self._clock())
        self.assertEqual(ctx.exception.code, "source_suppressed")

    def test_candidate_requires_at_least_one_supporting_observation(self):
        obs, _, _ = self._approved("Suppliers cancel late payments every week.")
        with self.assertRaises(Phase4Error) as ctx:
            candidates.create(self.conn, RESEARCHER, self.config,
                              self._base_data([{"observation_id": obs["observation_id"],
                                                "role": "contextual"}]), self._clock())
        self.assertEqual(ctx.exception.code, "missing_support")

    def test_support_and_contradiction_counts_always_computed_server_side(self):
        obs1, _, _ = self._approved("Suppliers cancel late payments every week.")
        obs2, _, _ = self._approved("Suppliers cancel late payments monthly too.")
        contra, _, _ = self._approved("We never have late payment problems.")
        data = self._base_data([
            {"observation_id": obs1["observation_id"], "role": "supporting"},
            {"observation_id": obs2["observation_id"], "role": "supporting"},
            {"observation_id": contra["observation_id"], "role": "contradicting"}])
        candidate = candidates.create(self.conn, RESEARCHER, self.config, data, self._clock())
        self.assertEqual(candidate["support_count"], 2)
        self.assertEqual(candidate["contradiction_count"], 1)
        self.assertEqual(candidate["included_participant_count"], 2)

    def test_cross_campaign_observation_rejected(self):
        obs, _, _ = self._approved("Suppliers cancel late payments every week.")
        camp2, guide2 = make_active_campaign_with_approved_guide(self.conn, self.config, self._clock)
        with self.assertRaises(ValidationError):
            candidates.create(self.conn, RESEARCHER, self.config,
                              self._base_data([{"observation_id": obs["observation_id"], "role": "supporting"}],
                                              campaign_id=camp2["campaign_id"]), self._clock())

    def test_segment_mismatch_rejected(self):
        p1 = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                              self.camp["campaign_id"], segment_id="SEG-alpha")
        p2 = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                              self.camp["campaign_id"], segment_id="SEG-beta")
        obs1, _, _ = self._approved("Suppliers cancel late payments every week.", participant=p1)
        obs2, _, _ = self._approved("Suppliers cancel late payments too often.", participant=p2)
        with self.assertRaises(Phase4Error) as ctx:
            candidates.create(self.conn, RESEARCHER, self.config,
                              self._base_data([
                                  {"observation_id": obs1["observation_id"], "role": "supporting"},
                                  {"observation_id": obs2["observation_id"], "role": "supporting"}]),
                              self._clock())
        self.assertEqual(ctx.exception.code, "incompatible_segment")

    def test_explicit_segment_id_must_match_supporting_observations(self):
        p1 = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                              self.camp["campaign_id"], segment_id="SEG-alpha")
        obs1, _, _ = self._approved("Suppliers cancel late payments every week.", participant=p1)
        with self.assertRaises(Phase4Error) as ctx:
            candidates.create(self.conn, RESEARCHER, self.config,
                              self._base_data([{"observation_id": obs1["observation_id"], "role": "supporting"}],
                                              segment_id="SEG-beta"), self._clock())
        self.assertEqual(ctx.exception.code, "incompatible_segment")

    def test_concept_test_campaign_restricts_finding_type(self):
        camp, guide = make_active_campaign_with_approved_guide(self.conn, self.config, self._clock,
                                                                method="concept_test")
        obs, _, _ = make_approved_observation(self.conn, self.identity_conn, self.config, self._clock, camp, guide,
                                              "Suppliers cancel late payments every week.")
        with self.assertRaises(Phase4Error) as ctx:
            candidates.create(self.conn, RESEARCHER, self.config,
                              self._base_data([{"observation_id": obs["observation_id"], "role": "supporting"}],
                                              campaign_id=camp["campaign_id"], finding_type="pain"), self._clock())
        self.assertEqual(ctx.exception.code, "incompatible_method")
        ok = candidates.create(self.conn, RESEARCHER, self.config,
                               self._base_data([{"observation_id": obs["observation_id"], "role": "supporting"}],
                                               campaign_id=camp["campaign_id"], finding_type="concept_reaction"),
                               self._clock())
        self.assertEqual(ok["finding_type"], "concept_reaction")

    def test_known_contradiction_requires_exclusion_reason(self):
        obs1, _, _ = self._approved("We would pay for a solution to this.",
                                    observation_type="willingness_to_pay_signal")
        self._approved_contradicting("We would never pay for anything like this.", obs1["observation_id"],
                                     observation_type="willingness_to_pay_signal")
        with self.assertRaises(Phase4Error) as ctx:
            candidates.create(self.conn, RESEARCHER, self.config,
                              self._base_data([{"observation_id": obs1["observation_id"], "role": "supporting"}],
                                              finding_type="willingness_to_pay_signal"), self._clock())
        self.assertEqual(ctx.exception.code, "contradiction_exclusion_requires_reason")

    def test_known_contradiction_excluded_with_reason_recorded_as_limitation(self):
        obs1, _, _ = self._approved("We would pay for a solution to this.",
                                    observation_type="willingness_to_pay_signal")
        self._approved_contradicting("We would never pay for anything like this.", obs1["observation_id"],
                                     observation_type="willingness_to_pay_signal")
        candidate = candidates.create(
            self.conn, RESEARCHER, self.config,
            self._base_data([{"observation_id": obs1["observation_id"], "role": "supporting"}],
                            finding_type="willingness_to_pay_signal",
                            contradiction_exclusion_reason="contradiction concerns a different pricing tier"),
            self._clock())
        self.assertTrue(any("excluded" in l for l in candidate["limitations"]))

    def test_known_contradiction_can_be_included_as_contradicting(self):
        obs1, _, _ = self._approved("We would pay for a solution to this.",
                                    observation_type="willingness_to_pay_signal")
        contra, _, _ = self._approved_contradicting(
            "We would never pay for anything like this.", obs1["observation_id"],
            observation_type="willingness_to_pay_signal")
        candidate = candidates.create(
            self.conn, RESEARCHER, self.config,
            self._base_data([{"observation_id": obs1["observation_id"], "role": "supporting"},
                             {"observation_id": contra["observation_id"], "role": "contradicting"}],
                            finding_type="willingness_to_pay_signal"), self._clock())
        self.assertEqual(candidate["contradiction_count"], 1)

    def test_draft_editing_updates_counts(self):
        obs1, _, _ = self._approved("Suppliers cancel late payments every week.")
        candidate = candidates.create(self.conn, RESEARCHER, self.config,
                                      self._base_data([{"observation_id": obs1["observation_id"],
                                                        "role": "supporting"}]), self._clock())
        obs2, _, _ = self._approved("Suppliers cancel late payments monthly too.")
        updated = candidates.update_draft(
            self.conn, RESEARCHER, candidate["candidate_id"],
            {"observations": [{"observation_id": obs1["observation_id"], "role": "supporting"},
                              {"observation_id": obs2["observation_id"], "role": "supporting"}]}, self._clock())
        self.assertEqual(updated["support_count"], 2)
        self.assertEqual(updated["included_participant_count"], 2)

    def test_only_draft_may_be_edited(self):
        obs1, _, _ = self._approved("Suppliers cancel late payments every week.")
        candidate = candidates.create(self.conn, RESEARCHER, self.config,
                                      self._base_data([{"observation_id": obs1["observation_id"],
                                                        "role": "supporting"}]), self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        with self.assertRaises(Phase4Error) as ctx:
            candidates.update_draft(self.conn, RESEARCHER, candidate["candidate_id"], {"statement": "x"},
                                    self._clock())
        self.assertEqual(ctx.exception.code, "invalid_transition")

    def test_submit_then_approve_creates_immutable_finding(self):
        obs1, _, _ = self._approved("Suppliers cancel late payments every week.")
        candidate = candidates.create(self.conn, RESEARCHER, self.config,
                                      self._base_data([{"observation_id": obs1["observation_id"],
                                                        "role": "supporting"}]), self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        approved_candidate, finding = candidates.approve(self.conn, self.config, REVIEWER,
                                                         candidate["candidate_id"], self._clock())
        self.assertEqual(approved_candidate["workflow_status"], "approved")
        self.assertEqual(finding["workflow_status"], "approved")
        self.assertEqual(finding["candidate_id"], candidate["candidate_id"])
        self.assertEqual(finding["numerator"], 1)
        self.assertGreaterEqual(finding["denominator"], 1)
        # no identity fields anywhere on the finding
        finding_str = str(finding)
        self.assertNotIn(obs1["participant_id"], finding_str)

    def test_self_approval_blocked_by_default(self):
        obs1, _, _ = self._approved("Suppliers cancel late payments every week.")
        candidate = candidates.create(self.conn, REVIEWER, self.config,
                                      self._base_data([{"observation_id": obs1["observation_id"],
                                                        "role": "supporting"}]), self._clock())
        candidates.submit(self.conn, REVIEWER, candidate["candidate_id"], self._clock())
        with self.assertRaises(Phase4Error) as ctx:
            candidates.approve(self.conn, self.config, REVIEWER, candidate["candidate_id"], self._clock())
        self.assertEqual(ctx.exception.code, "self_approval_forbidden")

    def test_self_approval_override_audited(self):
        from app import audit
        obs1, _, _ = self._approved("Suppliers cancel late payments every week.")
        candidate = candidates.create(self.conn, REVIEWER, self.config,
                                      self._base_data([{"observation_id": obs1["observation_id"],
                                                        "role": "supporting"}]), self._clock())
        candidates.submit(self.conn, REVIEWER, candidate["candidate_id"], self._clock())
        allowed_config = type(self.config)(env={"MV_TOKENS": "a:t:admin", "MV_ALLOW_SELF_APPROVAL": "1",
                                                 "MV_SYNTHETIC_ONLY": "1"})
        approved_candidate, _finding = candidates.approve(self.conn, allowed_config, REVIEWER,
                                                          candidate["candidate_id"], self._clock())
        self.assertTrue(approved_candidate["self_approval"])
        events = audit.list_for_object(self.conn, "evidence_candidate", candidate["candidate_id"])
        approve_event = next(e for e in events if e["action"] == "approve")
        self.assertTrue(approve_event["self_approval"])

    def test_approved_candidate_immutable(self):
        obs1, _, _ = self._approved("Suppliers cancel late payments every week.")
        candidate = candidates.create(self.conn, RESEARCHER, self.config,
                                      self._base_data([{"observation_id": obs1["observation_id"],
                                                        "role": "supporting"}]), self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        candidates.approve(self.conn, self.config, REVIEWER, candidate["candidate_id"], self._clock())
        with self.assertRaises(Phase4Error) as ctx:
            candidates.update_draft(self.conn, RESEARCHER, candidate["candidate_id"], {"statement": "x"},
                                    self._clock())
        self.assertEqual(ctx.exception.code, "invalid_transition")

    def test_stale_source_version_detected_on_submit(self):
        from app import suppression
        obs1, participant, _ = self._approved("Suppliers cancel late payments every week.")
        obs2, _, _ = self._approved("Suppliers cancel late payments monthly too.")
        candidate = candidates.create(self.conn, RESEARCHER, self.config,
                                      self._base_data([
                                          {"observation_id": obs1["observation_id"], "role": "supporting"},
                                          {"observation_id": obs2["observation_id"], "role": "supporting"}]),
                                      self._clock())
        suppression.suppress_participant(self.conn, ADMIN, participant["participant_id"], "withdrawn",
                                         self._clock())
        with self.assertRaises(Phase4Error) as ctx:
            candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        self.assertEqual(ctx.exception.code, "stale_source_version")

    def test_refreshing_draft_clears_staleness(self):
        from app import suppression
        obs1, participant, _ = self._approved("Suppliers cancel late payments every week.")
        obs2, _, _ = self._approved("Suppliers cancel late payments monthly too.")
        candidate = candidates.create(self.conn, RESEARCHER, self.config,
                                      self._base_data([
                                          {"observation_id": obs1["observation_id"], "role": "supporting"},
                                          {"observation_id": obs2["observation_id"], "role": "supporting"}]),
                                      self._clock())
        suppression.suppress_participant(self.conn, ADMIN, participant["participant_id"], "withdrawn",
                                         self._clock())
        refreshed = candidates.update_draft(
            self.conn, RESEARCHER, candidate["candidate_id"],
            {"observations": [{"observation_id": obs2["observation_id"], "role": "supporting"}]}, self._clock())
        self.assertEqual(refreshed["support_count"], 1)
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())  # no longer stale

    def test_reject_requires_reason_and_preserves_candidate(self):
        obs1, _, _ = self._approved("Suppliers cancel late payments every week.")
        candidate = candidates.create(self.conn, RESEARCHER, self.config,
                                      self._base_data([{"observation_id": obs1["observation_id"],
                                                        "role": "supporting"}]), self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        with self.assertRaises(ValidationError):
            candidates.reject(self.conn, REVIEWER, candidate["candidate_id"], "not_a_real_reason", self._clock())
        rejected = candidates.reject(self.conn, REVIEWER, candidate["candidate_id"], "insufficient_context",
                                     self._clock())
        self.assertEqual(rejected["workflow_status"], "rejected")
        still_there = candidates.get(self.conn, candidate["candidate_id"])
        self.assertEqual(still_there["workflow_status"], "rejected")

    def test_finding_provenance_traces_back_to_candidate_and_observations(self):
        obs1, _, _ = self._approved("Suppliers cancel late payments every week.")
        candidate = candidates.create(self.conn, RESEARCHER, self.config,
                                      self._base_data([{"observation_id": obs1["observation_id"],
                                                        "role": "supporting"}]), self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        _approved_candidate, finding = candidates.approve(self.conn, self.config, REVIEWER,
                                                          candidate["candidate_id"], self._clock())
        full_finding = findings.get(self.conn, finding["finding_id"])
        self.assertEqual(full_finding["candidate_id"], candidate["candidate_id"])
        stored_candidate = candidates.get(self.conn, candidate["candidate_id"])
        self.assertEqual(stored_candidate["observations"][0]["observation_id"], obs1["observation_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
