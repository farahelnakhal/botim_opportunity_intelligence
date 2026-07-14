"""Part A proposal tests: generation eligibility, provenance/quote/
contradiction/limitation mapping, non-authoritative strength suggestion,
draft/submit/approve/reject workflow, self-approval separation, staleness
detection, and withdrawal-driven invalidation."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (ADMIN, RESEARCHER, REVIEWER, make_active_campaign_with_approved_guide,
                      make_approved_observation, make_dbs, make_observation, make_participant, make_response)

from app import candidates, findings, observation_review, part_a_proposal, suppression
from app.models import Phase5Error, ValidationError


class PartAProposalTests(unittest.TestCase):
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

    def _published_finding(self, texts=None, creator=RESEARCHER, approver=REVIEWER, observation_overrides=None,
                           **candidate_overrides):
        texts = texts or ["Suppliers cancel late payments every week."]
        observations = []
        participants_out = []
        for text in texts:
            obs, participant, _ = self._approved(text, approver=approver, **(observation_overrides or {}))
            observations.append({"observation_id": obs["observation_id"], "role": "supporting"})
            participants_out.append(participant)
        data = {
            "campaign_id": self.camp["campaign_id"], "finding_type": "pain",
            "statement": "Suppliers cancel late payments.", "proposed_evidence_role": "supporting",
            "observations": observations,
        }
        data.update(candidate_overrides)
        candidate = candidates.create(self.conn, creator, self.config, data, self._clock())
        candidates.submit(self.conn, creator, candidate["candidate_id"], self._clock())
        _approved_candidate, finding = candidates.approve(self.conn, self.config, approver,
                                                          candidate["candidate_id"], self._clock())
        findings.publish(self.conn, approver, finding["finding_id"], self._clock())
        return finding, participants_out

    # --- generation --------------------------------------------------------

    def test_generate_proposal_from_approved_published_finding(self):
        finding, _ = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        self.assertEqual(proposal["workflow_status"], "draft")
        self.assertEqual(proposal["publication_status"], "unpublished")
        self.assertEqual(proposal["finding_id"], finding["finding_id"])

    def test_unpublished_finding_rejected(self):
        obs, _, _ = self._approved("Suppliers cancel late payments every week.")
        candidate = candidates.create(self.conn, RESEARCHER, self.config, {
            "campaign_id": self.camp["campaign_id"], "finding_type": "pain",
            "statement": "Suppliers cancel late payments.", "proposed_evidence_role": "supporting",
            "observations": [{"observation_id": obs["observation_id"], "role": "supporting"}]}, self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        _approved_candidate, finding = candidates.approve(self.conn, self.config, REVIEWER,
                                                          candidate["candidate_id"], self._clock())
        with self.assertRaises(Phase5Error) as ctx:
            part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        self.assertEqual(ctx.exception.code, "finding_not_publishable")

    def test_needs_revalidation_finding_rejected(self):
        finding, participants_out = self._published_finding()
        suppression.suppress_participant(self.conn, ADMIN, participants_out[0]["participant_id"],
                                         "withdrawn", self._clock())
        after = findings.get(self.conn, finding["finding_id"])
        self.assertEqual(after["publication_status"], "suppressed")  # only one supporter -> zero support
        with self.assertRaises(Phase5Error) as ctx:
            part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        self.assertIn(ctx.exception.code, ("finding_needs_revalidation", "finding_not_publishable"))

    def test_suppressed_finding_rejected(self):
        finding, participants_out = self._published_finding()
        suppression.suppress_participant(self.conn, ADMIN, participants_out[0]["participant_id"],
                                         "withdrawn", self._clock())
        with self.assertRaises(Phase5Error) as ctx:
            part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        self.assertEqual(ctx.exception.code, "finding_not_publishable")

    def test_proposal_mapping_contains_provenance(self):
        finding, _ = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        prov = proposal["payload"]["provenance"]
        self.assertEqual(prov["finding_id"], finding["finding_id"])
        self.assertIn("candidate_id", prov)
        self.assertTrue(prov["observations"])
        entry = prov["observations"][0]
        for key in ("observation_id", "response_id", "participant_id", "source_answer_id", "question_id"):
            self.assertIn(key, entry)

    def test_proposal_contains_no_identity_fields(self):
        finding, participants_out = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        blob = str(proposal["payload"])
        self.assertNotIn(participants_out[0]["merchant_identity_id"], blob)

    def test_proposal_contains_no_raw_transcript(self):
        finding, _ = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        self.assertNotIn("transcript", str(proposal["payload"]).lower())

    def test_proposal_contains_no_ev_id(self):
        finding, _ = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        self.assertIsNone(proposal["payload"]["authoritative_ev_id"])

    def test_suggested_strength_remains_non_authoritative(self):
        finding, _ = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        payload = proposal["payload"]
        self.assertEqual(payload["suggested_strength"], finding["strength_band"])
        self.assertTrue(payload["reviewer_required"])
        self.assertIn("Workstream A decides", payload["strength_decision_note"])

    def test_quotes_included_only_with_permission(self):
        finding, _ = self._published_finding(
            texts=["Suppliers cancel late payments every week."],
            observation_overrides={"is_direct_quote": True,
                                   "normalized_statement": "Suppliers cancel late payments every week."})
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        self.assertEqual(len(proposal["payload"]["quotes"]), 1)

    def test_quotes_omitted_when_permission_invalid(self):
        from app import participants as participants_module
        finding, participants_out = self._published_finding(
            texts=["Suppliers cancel late payments every week."],
            observation_overrides={"is_direct_quote": True,
                                   "normalized_statement": "Suppliers cancel late payments every week."})
        participants_module.update(self.conn, self.identity_conn, self.config, RESEARCHER,
                                   participants_out[0]["participant_id"], {"quote_permission": False},
                                   self._clock())
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        self.assertEqual(proposal["payload"]["quotes"], [])
        self.assertTrue(any("quote" in l for l in proposal["payload"]["limitations"]))

    def test_contradictions_preserved(self):
        obs1, _, _ = self._approved("We would pay for a solution to this.",
                                    observation_type="willingness_to_pay_signal")
        participant2 = make_participant(self.conn, self.identity_conn, self.config, self._clock,
                                        self.camp["campaign_id"])
        response2 = make_response(self.conn, self.config, self._clock, self.camp, self.guide, participant2,
                                  [{"question_id": self.guide["questions"][0]["question_id"],
                                    "answer": "We would never pay for anything like this."}])
        contra = make_observation(self.conn, self.config, self._clock, response2, 0,
                                  "We would never pay for anything like this.", observation_type="contradiction")
        contra = observation_review.edit(self.conn, RESEARCHER, contra["observation_id"],
                                         {"contradiction_target": obs1["observation_id"]}, self._clock())
        observation_review.approve(self.conn, self.config, REVIEWER, contra["observation_id"], self._clock())
        candidate = candidates.create(self.conn, RESEARCHER, self.config, {
            "campaign_id": self.camp["campaign_id"], "finding_type": "willingness_to_pay_signal",
            "statement": "Some merchants would pay; one contradicts.", "proposed_evidence_role": "supporting",
            "observations": [{"observation_id": obs1["observation_id"], "role": "supporting"},
                             {"observation_id": contra["observation_id"], "role": "contradicting"}]},
            self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        _approved_candidate, finding = candidates.approve(self.conn, self.config, REVIEWER,
                                                          candidate["candidate_id"], self._clock())
        findings.publish(self.conn, REVIEWER, finding["finding_id"], self._clock())
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        self.assertEqual(len(proposal["payload"]["contradictory_evidence"]), 1)
        self.assertEqual(proposal["payload"]["contradiction_count"], 1)

    def test_denominator_semantics_preserved(self):
        finding, _ = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        self.assertEqual(proposal["payload"]["denominator"], finding["denominator"])
        self.assertEqual(proposal["payload"]["denominator_definition"], finding["denominator_definition"])
        self.assertEqual(proposal["payload"]["numerator"], finding["numerator"])

    def test_limitations_preserved(self):
        finding, _ = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        self.assertEqual(proposal["payload"]["limitations"], finding["limitations"])

    # --- workflow ------------------------------------------------------------

    def test_draft_edit(self):
        finding, _ = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        updated = part_a_proposal.update_draft(self.conn, RESEARCHER, proposal["proposal_id"],
                                               {"proposed_title": "Weekly late payments (interview)"},
                                               self._clock())
        self.assertEqual(updated["payload"]["proposed_title"], "Weekly late payments (interview)")

    def test_submit(self):
        finding, _ = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        submitted = part_a_proposal.submit(self.conn, RESEARCHER, proposal["proposal_id"], self._clock())
        self.assertEqual(submitted["workflow_status"], "pending_review")

    def test_approve(self):
        finding, _ = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        part_a_proposal.submit(self.conn, RESEARCHER, proposal["proposal_id"], self._clock())
        approved = part_a_proposal.approve(self.conn, self.config, REVIEWER, proposal["proposal_id"],
                                          self._clock())
        self.assertEqual(approved["workflow_status"], "approved")

    def test_reject_with_reason(self):
        finding, _ = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        part_a_proposal.submit(self.conn, RESEARCHER, proposal["proposal_id"], self._clock())
        with self.assertRaises(ValidationError):
            part_a_proposal.reject(self.conn, REVIEWER, proposal["proposal_id"], "not_a_real_reason",
                                   self._clock())
        rejected = part_a_proposal.reject(self.conn, REVIEWER, proposal["proposal_id"], "insufficient_context",
                                         self._clock())
        self.assertEqual(rejected["workflow_status"], "rejected")

    def test_self_approval_blocked(self):
        finding, _ = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, REVIEWER, finding["finding_id"], self._clock())
        part_a_proposal.submit(self.conn, REVIEWER, proposal["proposal_id"], self._clock())
        with self.assertRaises(Phase5Error) as ctx:
            part_a_proposal.approve(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock())
        self.assertEqual(ctx.exception.code, "self_approval_forbidden")

    def test_self_approval_override_audited(self):
        from app import audit
        finding, _ = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, REVIEWER, finding["finding_id"], self._clock())
        part_a_proposal.submit(self.conn, REVIEWER, proposal["proposal_id"], self._clock())
        allowed_config = type(self.config)(env={"MV_TOKENS": "a:t:admin", "MV_ALLOW_SELF_APPROVAL": "1",
                                                 "MV_SYNTHETIC_ONLY": "1"})
        approved = part_a_proposal.approve(self.conn, allowed_config, REVIEWER, proposal["proposal_id"],
                                          self._clock(), reason="synthetic smoke test override")
        self.assertEqual(approved["workflow_status"], "approved")
        events = audit.list_for_object(self.conn, "part_a_proposal", proposal["proposal_id"])
        approve_event = next(e for e in events if e["action"] == "approve")
        self.assertTrue(approve_event["self_approval"])

    def test_approved_proposal_immutable(self):
        finding, _ = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        part_a_proposal.submit(self.conn, RESEARCHER, proposal["proposal_id"], self._clock())
        part_a_proposal.approve(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock())
        with self.assertRaises(Phase5Error) as ctx:
            part_a_proposal.update_draft(self.conn, RESEARCHER, proposal["proposal_id"],
                                        {"proposed_title": "too late"}, self._clock())
        self.assertEqual(ctx.exception.code, "proposal_not_reviewable")

    def test_source_version_staleness_detected(self):
        finding, participants_out = self._published_finding(
            texts=["Suppliers cancel late payments every week.", "Suppliers cancel late payments monthly too."])
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        # a second participant remains supporting -> finding stays published but its
        # numerator/support_count change, drifting the fingerprint captured above
        suppression.suppress_participant(self.conn, ADMIN, participants_out[0]["participant_id"],
                                         "withdrawn", self._clock())
        with self.assertRaises(Phase5Error) as ctx:
            part_a_proposal.submit(self.conn, RESEARCHER, proposal["proposal_id"], self._clock())
        self.assertIn(ctx.exception.code, ("proposal_stale", "source_version_changed"))

    def test_withdrawal_marks_proposal_needs_revalidation(self):
        finding, participants_out = self._published_finding(
            texts=["Suppliers cancel late payments every week.", "Suppliers cancel late payments monthly too."])
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        suppression.suppress_participant(self.conn, ADMIN, participants_out[0]["participant_id"],
                                         "withdrawn", self._clock())
        after = part_a_proposal.get(self.conn, proposal["proposal_id"])
        self.assertEqual(after["publication_status"], "needs_revalidation")
        self.assertIsNotNone(after["needs_revalidation_reason"])

    def test_zero_support_suppresses_proposal(self):
        finding, participants_out = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        suppression.suppress_participant(self.conn, ADMIN, participants_out[0]["participant_id"],
                                         "withdrawn", self._clock())
        after = part_a_proposal.get(self.conn, proposal["proposal_id"])
        self.assertEqual(after["publication_status"], "suppressed")

    def test_export_blocked_after_invalidation(self):
        finding, participants_out = self._published_finding()
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        part_a_proposal.submit(self.conn, RESEARCHER, proposal["proposal_id"], self._clock())
        part_a_proposal.approve(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock())
        part_a_proposal.approve_export(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock())
        suppression.suppress_participant(self.conn, ADMIN, participants_out[0]["participant_id"],
                                         "withdrawn", self._clock())
        with self.assertRaises(Phase5Error) as ctx:
            part_a_proposal.export(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock(),
                                  Path(self.tmp.name))
        self.assertEqual(ctx.exception.code, "proposal_not_exportable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
