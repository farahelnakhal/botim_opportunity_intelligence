"""Observation review tests: queue, source-context visibility, editing
(with safeguard re-validation), approve/reject, self-approval separation,
merge/supersession, contradiction-merge refusal."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (ADMIN, RESEARCHER, REVIEWER, VIEWER, make_active_campaign_with_approved_guide,
                      make_approved_observation, make_dbs, make_observation, make_participant, make_response)

from app import observation_review
from app.auth import AuthError
from app.extraction import get_observation
from app.models import Phase4Error, ValidationError


class ReviewQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn, self.identity_conn, self.config = make_dbs(self.tmp.name)
        self.clock_n = 0
        self.camp, self.guide = make_active_campaign_with_approved_guide(
            self.conn, self.config, self._clock, campaign_overrides={"linked_opportunities": ["OPP-013"]})
        self.participant = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                            self.camp["campaign_id"])
        q1 = self.guide["questions"][0]["question_id"]
        self.response = make_response(self.conn, self.config, self._clock, self.camp, self.guide,
                                      self.participant, [{"question_id": q1,
                                                          "answer": "Suppliers cancel late payments every week."}])
        self.obs = make_observation(self.conn, self.config, self._clock, self.response, 0,
                                    "Suppliers cancel late payments every week.")

    def _clock(self):
        self.clock_n += 1
        return f"2026-01-01T00:00:{self.clock_n:02d}Z"

    def test_pending_review_queue(self):
        queue = observation_review.list_review_queue(self.conn)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["observation_id"], self.obs["observation_id"])

    def test_researcher_sees_only_redacted_source_context(self):
        ctx = observation_review.get_review_context(self.conn, self.obs["observation_id"])
        self.assertEqual(ctx["question_text"], self.guide["questions"][0]["text"])
        self.assertIn("Suppliers cancel", ctx["redacted_source_answer"])
        self.assertEqual(ctx["campaign_method"], "interview")

    def test_editable_fields_update(self):
        updated = observation_review.edit(self.conn, RESEARCHER, self.obs["observation_id"], {
            "normalized_statement": "Merchant reports weekly late supplier payments.",
            "reviewer_notes": "confirmed with transcript"}, self._clock())
        self.assertEqual(updated["normalized_statement"], "Merchant reports weekly late supplier payments.")
        self.assertEqual(updated["reviewer_notes"], "confirmed with transcript")

    def test_source_fields_immutable(self):
        for field, value in (("source_excerpt", "fabricated"), ("source_answer_id", "MVA-fake"),
                             ("response_id", "MVR-fake"), ("campaign_id", "MVC-fake"),
                             ("source_hash", "sha256:fake"), ("extraction_run_id", "MER-fake"),
                             ("participant_id", "MVP-fake")):
            with self.assertRaises(Phase4Error) as ctx:
                observation_review.edit(self.conn, RESEARCHER, self.obs["observation_id"], {field: value},
                                        self._clock())
            self.assertEqual(ctx.exception.code, "source_immutable")

    def test_edited_statement_revalidated_aggregate_rejected(self):
        with self.assertRaises(ValidationError):
            observation_review.edit(self.conn, RESEARCHER, self.obs["observation_id"], {
                "normalized_statement": "Most merchants suffer from this every week."}, self._clock())

    def _second_response(self, answer_text):
        participant2 = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                        self.camp["campaign_id"])
        q1 = self.guide["questions"][0]["question_id"]
        return make_response(self.conn, self.config, self._clock, self.camp, self.guide, participant2,
                             [{"question_id": q1, "answer": answer_text}])

    def test_wtp_revalidation_after_edit(self):
        text = "Suppliers cancel late payments every week."
        response2 = self._second_response(text)
        wtp_obs = make_observation(self.conn, self.config, self._clock, response2, 0, text,
                                   observation_type="pain")  # created as 'pain' so it survives creation-time WTP check
        edited = observation_review.edit(self.conn, RESEARCHER, wtp_obs["observation_id"], {
            "observation_type": "willingness_to_pay_signal",
            "normalized_statement": "Merchant would find a solution useful."}, self._clock())
        # no WTP support in the (immutable) source excerpt -> downgraded to concept_reaction
        self.assertEqual(edited["observation_type"], "concept_reaction")

    def test_quote_downgrade_after_edit(self):
        text = "Suppliers cancel late payments every week."
        response2 = self._second_response(text)
        quote_obs = make_observation(self.conn, self.config, self._clock, response2, 0, text,
                                     is_direct_quote=True, normalized_statement=text)
        edited = observation_review.edit(self.conn, RESEARCHER, quote_obs["observation_id"], {
            "normalized_statement": "A paraphrased version of the complaint.", "is_direct_quote": True},
            self._clock())
        self.assertFalse(edited["is_direct_quote"])
        self.assertIn("quote_downgraded", edited["sensitivity_flags"])

    def test_observation_approval(self):
        approved = observation_review.approve(self.conn, self.config, REVIEWER, self.obs["observation_id"],
                                              self._clock())
        self.assertEqual(approved["workflow_status"], "approved")
        self.assertEqual(approved["reviewed_by"], REVIEWER["label"])

    def test_rejection_requires_reason(self):
        with self.assertRaises(ValidationError):
            observation_review.reject(self.conn, REVIEWER, self.obs["observation_id"], "not_a_real_reason",
                                      self._clock())
        rejected = observation_review.reject(self.conn, REVIEWER, self.obs["observation_id"],
                                             "unsupported_by_source", self._clock())
        self.assertEqual(rejected["workflow_status"], "rejected")
        self.assertEqual(rejected["rejection_reason"], "unsupported_by_source")

    def test_rejected_observation_excluded_from_queue(self):
        observation_review.reject(self.conn, REVIEWER, self.obs["observation_id"], "duplicate", self._clock())
        queue = observation_review.list_review_queue(self.conn)
        self.assertEqual(queue, [])
        # still stored, not deleted
        still_there = get_observation(self.conn, self.obs["observation_id"])
        self.assertEqual(still_there["workflow_status"], "rejected")

    def test_self_approval_blocked_by_default(self):
        # created via REVIEWER so the same actor clears approve()'s role
        # check and actually reaches the self-approval-specific guard
        response2 = self._second_response("Suppliers cancel late payments every week.")
        reviewer_obs = make_observation(self.conn, self.config, self._clock, response2, 0,
                                        "Suppliers cancel late payments every week.", principal=REVIEWER)
        with self.assertRaises(Phase4Error) as ctx:
            observation_review.approve(self.conn, self.config, REVIEWER, reviewer_obs["observation_id"],
                                       self._clock())
        self.assertEqual(ctx.exception.code, "self_approval_forbidden")

    def test_self_approval_override_audited(self):
        from app import audit
        response2 = self._second_response("Suppliers cancel late payments every week.")
        reviewer_obs = make_observation(self.conn, self.config, self._clock, response2, 0,
                                        "Suppliers cancel late payments every week.", principal=REVIEWER)
        allowed_config = type(self.config)(env={"MV_TOKENS": "a:t:admin", "MV_ALLOW_SELF_APPROVAL": "1",
                                                 "MV_SYNTHETIC_ONLY": "1"})
        approved = observation_review.approve(self.conn, allowed_config, REVIEWER, reviewer_obs["observation_id"],
                                             self._clock())
        self.assertTrue(approved["self_approval"])
        events = audit.list_for_object(self.conn, "observation", reviewer_obs["observation_id"])
        approve_event = next(e for e in events if e["action"] == "approve")
        self.assertTrue(approve_event["self_approval"])

    def test_approved_observation_immutable(self):
        observation_review.approve(self.conn, self.config, REVIEWER, self.obs["observation_id"], self._clock())
        with self.assertRaises(Phase4Error) as ctx:
            observation_review.edit(self.conn, RESEARCHER, self.obs["observation_id"],
                                    {"reviewer_notes": "too late"}, self._clock())
        self.assertEqual(ctx.exception.code, "invalid_transition")
        with self.assertRaises(Phase4Error):
            observation_review.approve(self.conn, self.config, ADMIN, self.obs["observation_id"], self._clock())

    def test_viewer_forbidden_via_role_helper(self):
        # observation_review functions enforce roles internally; viewer must
        # never reach edit/approve/reject/merge (API-level 403 tested in
        # test_phase4_api.py) — this documents the same guarantee service-side.
        with self.assertRaises(AuthError):
            observation_review.edit(self.conn, VIEWER, self.obs["observation_id"], {}, self._clock())
        with self.assertRaises(AuthError):
            observation_review.approve(self.conn, self.config, VIEWER, self.obs["observation_id"], self._clock())


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn, self.identity_conn, self.config = make_dbs(self.tmp.name)
        self.clock_n = 0
        self.camp, self.guide = make_active_campaign_with_approved_guide(self.conn, self.config, self._clock)

    def _clock(self):
        self.clock_n += 1
        return f"2026-01-01T00:00:{self.clock_n:02d}Z"

    def test_duplicate_merge_retains_provenance(self):
        obs1, p1, r1 = make_approved_observation(self.conn, self.identity_conn, self.config, self._clock,
                                                  self.camp, self.guide, "Late payments hurt us badly")
        obs2, p2, r2 = make_approved_observation(self.conn, self.identity_conn, self.config, self._clock,
                                                  self.camp, self.guide, "We also suffer from late payments")
        canonical, superseded = observation_review.merge(
            self.conn, REVIEWER, obs1["observation_id"], [obs2["observation_id"]], self._clock())
        self.assertEqual(canonical["observation_id"], obs1["observation_id"])
        self.assertEqual(canonical["workflow_status"], "approved")  # canonical untouched
        # the duplicate is stored, superseded, and still traceable to its own response/participant
        still_stored = get_observation(self.conn, obs2["observation_id"])
        self.assertEqual(still_stored["workflow_status"], "superseded")
        self.assertEqual(still_stored["superseded_by_observation_id"], obs1["observation_id"])
        self.assertEqual(still_stored["response_id"], r2["response_id"])
        self.assertEqual(still_stored["participant_id"], p2["participant_id"])
        self.assertEqual(still_stored["source_excerpt"], "We also suffer from late payments")

    def test_superseded_observation_excluded_from_queue_and_reuse(self):
        obs1, _, _ = make_approved_observation(self.conn, self.identity_conn, self.config, self._clock,
                                               self.camp, self.guide, "Late payments hurt us badly")
        response = make_response(self.conn, self.config, self._clock, self.camp, self.guide,
                                 make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                                 self.camp["campaign_id"]),
                                 [{"question_id": self.guide["questions"][0]["question_id"],
                                   "answer": "We also suffer from late payments"}])
        obs2 = make_observation(self.conn, self.config, self._clock, response, 0,
                                "We also suffer from late payments")
        observation_review.merge(self.conn, REVIEWER, obs1["observation_id"], [obs2["observation_id"]],
                                 self._clock())
        queue = observation_review.list_review_queue(self.conn, workflow_status=None)
        statuses = {o["observation_id"]: o["workflow_status"] for o in queue}
        self.assertEqual(statuses[obs2["observation_id"]], "superseded")

    def test_contradiction_cannot_merge_as_support(self):
        obs1, _, _ = make_approved_observation(self.conn, self.identity_conn, self.config, self._clock,
                                               self.camp, self.guide, "We would happily pay for this.",
                                               observation_type="willingness_to_pay_signal")
        response2 = make_response(self.conn, self.config, self._clock, self.camp, self.guide,
                                  make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                                  self.camp["campaign_id"]),
                                  [{"question_id": self.guide["questions"][0]["question_id"],
                                    "answer": "We would never pay for this."}])
        # created without contradiction_target (would be cleared — Phase 3's
        # extraction-time validation is scoped to this response only, and
        # obs1 came from a different response/participant); the reviewer
        # sets the cross-response link via edit(), which is campaign-scoped
        contradiction_obs = make_observation(
            self.conn, self.config, self._clock, response2, 0, "We would never pay for this.",
            observation_type="contradiction")
        contradiction_obs = observation_review.edit(
            self.conn, RESEARCHER, contradiction_obs["observation_id"],
            {"contradiction_target": obs1["observation_id"]}, self._clock())
        self.assertEqual(contradiction_obs["contradiction_target"], obs1["observation_id"])
        observation_review.approve(self.conn, self.config, REVIEWER, contradiction_obs["observation_id"],
                                   self._clock())
        with self.assertRaises(ValidationError):
            observation_review.merge(self.conn, REVIEWER, obs1["observation_id"],
                                     [contradiction_obs["observation_id"]], self._clock())


if __name__ == "__main__":
    unittest.main(verbosity=2)
