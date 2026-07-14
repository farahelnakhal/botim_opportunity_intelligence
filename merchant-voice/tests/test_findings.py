"""Merchant finding tests: immutable creation from an approved candidate, no
identity fields, deterministic strength bands (all 6 scenarios), publish/
suppress verification, and published-query exclusion rules."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (ADMIN, RESEARCHER, REVIEWER, make_active_campaign_with_approved_guide,
                      make_approved_observation, make_dbs, make_observation, make_participant, make_response)

from app import candidates, findings, observation_review
from app.models import Phase4Error
from app.strength import compute_strength_band


class FindingWorkflowTests(unittest.TestCase):
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

    def _candidate_from(self, roles_and_texts, finding_type="pain", **data_overrides):
        """roles_and_texts: list of (role, text) -> creates+approves an
        observation per entry, builds a draft/pending/approved candidate."""
        observations = []
        participants_out = []
        for role, text in roles_and_texts:
            obs, participant, _ = self._approved(text, observation_type=finding_type)
            observations.append({"observation_id": obs["observation_id"], "role": role})
            participants_out.append(participant)
        data = {
            "campaign_id": self.camp["campaign_id"], "finding_type": finding_type,
            "statement": "Suppliers cancel late payments.", "proposed_evidence_role": "supporting",
            "observations": observations,
        }
        data.update(data_overrides)
        candidate = candidates.create(self.conn, RESEARCHER, self.config, data, self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        approved_candidate, finding = candidates.approve(self.conn, self.config, REVIEWER,
                                                         candidate["candidate_id"], self._clock())
        return approved_candidate, finding, participants_out

    def test_approving_candidate_creates_approved_finding(self):
        _candidate, finding, _ = self._candidate_from([("supporting", "Suppliers cancel late payments weekly.")])
        self.assertEqual(finding["workflow_status"], "approved")
        self.assertEqual(finding["publication_status"], "unpublished")

    def test_finding_has_no_identity_fields(self):
        _candidate, finding, participants_out = self._candidate_from(
            [("supporting", "Suppliers cancel late payments weekly.")])
        blob = str(finding)
        self.assertNotIn(participants_out[0]["participant_id"], blob)
        self.assertNotIn(participants_out[0]["merchant_identity_id"], blob)

    def test_finding_counts_match_candidate(self):
        _candidate, finding, _ = self._candidate_from([
            ("supporting", "Suppliers cancel late payments weekly."),
            ("supporting", "Suppliers cancel late payments monthly too.")])
        self.assertEqual(finding["numerator"], 2)
        self.assertEqual(finding["support_count"], 2)
        self.assertGreaterEqual(finding["denominator"], 2)
        self.assertEqual(finding["denominator_definition"], f"included participants in campaign {self.camp['campaign_id']}")

    def test_strength_band_single_signal(self):
        _candidate, finding, _ = self._candidate_from([("supporting", "Suppliers cancel late payments weekly.")])
        self.assertEqual(finding["strength_band"], "single_signal")

    def test_strength_band_emerging_pattern(self):
        _candidate, finding, _ = self._candidate_from([
            ("supporting", "Suppliers cancel late payments weekly."),
            ("supporting", "Suppliers cancel late payments monthly too.")])
        self.assertEqual(finding["strength_band"], "emerging_pattern")

    def test_strength_band_repeated_pattern(self):
        _candidate, finding, _ = self._candidate_from([
            ("supporting", "Suppliers cancel late payments weekly."),
            ("supporting", "Suppliers cancel late payments monthly too."),
            ("supporting", "Suppliers cancel late payments quarterly as well.")])
        self.assertEqual(finding["strength_band"], "repeated_pattern")

    def test_strength_band_mixed_pattern(self):
        _candidate, finding, _ = self._candidate_from([
            ("supporting", "Suppliers cancel late payments weekly."),
            ("supporting", "Suppliers cancel late payments monthly too."),
            ("supporting", "Suppliers cancel late payments quarterly as well."),
            ("contradicting", "We never experience late supplier payments.")])
        self.assertEqual(finding["strength_band"], "mixed_pattern")

    def test_strength_band_contradicted(self):
        _candidate, finding, _ = self._candidate_from([
            ("supporting", "Suppliers cancel late payments weekly."),
            ("contradicting", "We never experience late supplier payments.")])
        self.assertEqual(finding["strength_band"], "contradicted")

    def test_strength_band_never_uses_market_validated_label(self):
        from app.models import STRENGTH_BANDS
        for band in STRENGTH_BANDS:
            self.assertNotIn("validated", band)
            self.assertNotEqual(band, "market validated")

    def test_compute_strength_band_insufficient_directly(self):
        band, _factors = compute_strength_band(0, 0, 0)
        self.assertEqual(band, "insufficient")

    def test_concept_reaction_finding_type_remains_labelled_as_such(self):
        camp, guide = make_active_campaign_with_approved_guide(self.conn, self.config, self._clock,
                                                                method="concept_test")
        obs, _, _ = make_approved_observation(self.conn, self.identity_conn, self.config, self._clock, camp, guide,
                                              "This concept sounds interesting to us.",
                                              observation_type="concept_reaction")
        candidate = candidates.create(self.conn, RESEARCHER, self.config, {
            "campaign_id": camp["campaign_id"], "finding_type": "concept_reaction",
            "statement": "Merchants reacted positively to the concept.", "proposed_evidence_role": "supporting",
            "observations": [{"observation_id": obs["observation_id"], "role": "supporting"}]}, self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        _approved_candidate, finding = candidates.approve(self.conn, self.config, REVIEWER,
                                                          candidate["candidate_id"], self._clock())
        self.assertEqual(finding["method"], "concept_test")
        stored_candidate = candidates.get(self.conn, candidate["candidate_id"])
        self.assertEqual(stored_candidate["finding_type"], "concept_reaction")

    def test_publish_requires_approved_workflow_status(self):
        _candidate, finding, _ = self._candidate_from([("supporting", "Suppliers cancel late payments weekly.")])
        published = findings.publish(self.conn, REVIEWER, finding["finding_id"], self._clock())
        self.assertEqual(published["publication_status"], "published")

    def test_suppressed_finding_cannot_be_published(self):
        _candidate, finding, _ = self._candidate_from([("supporting", "Suppliers cancel late payments weekly.")])
        findings.suppress(self.conn, REVIEWER, finding["finding_id"], self._clock(), reason="data quality concern")
        with self.assertRaises(Phase4Error) as ctx:
            findings.publish(self.conn, REVIEWER, finding["finding_id"], self._clock())
        self.assertEqual(ctx.exception.code, "finding_not_publishable")

    def test_quote_permission_denied_blocks_publish(self):
        from app import participants as participants_module
        obs, participant, _ = self._approved("Suppliers cancel late payments weekly.", is_direct_quote=True,
                                             normalized_statement="Suppliers cancel late payments weekly.")
        candidate = candidates.create(self.conn, RESEARCHER, self.config, {
            "campaign_id": self.camp["campaign_id"], "finding_type": "pain",
            "statement": "Suppliers cancel late payments.", "proposed_evidence_role": "supporting",
            "observations": [{"observation_id": obs["observation_id"], "role": "supporting"}]}, self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        _approved_candidate, finding = candidates.approve(self.conn, self.config, REVIEWER,
                                                          candidate["candidate_id"], self._clock())
        # narrowing-only participant update revokes quote_permission without
        # suppressing the participant/observation (that's a distinct action
        # from withdrawal — see app/participants.py's "may only narrow" rule)
        participants_module.update(self.conn, self.identity_conn, self.config, RESEARCHER,
                                   participant["participant_id"], {"quote_permission": False}, self._clock())
        with self.assertRaises(Phase4Error) as ctx:
            findings.publish(self.conn, REVIEWER, finding["finding_id"], self._clock())
        self.assertEqual(ctx.exception.code, "quote_permission_denied")

    def test_published_query_excludes_unpublished_needs_revalidation_and_suppressed(self):
        _candidate, finding, _ = self._candidate_from([("supporting", "Suppliers cancel late payments weekly.")])
        unpublished_list = findings.list_for_campaign(self.conn, self.camp["campaign_id"], published_only=True)
        self.assertEqual(unpublished_list, [])
        findings.publish(self.conn, REVIEWER, finding["finding_id"], self._clock())
        published_list = findings.list_for_campaign(self.conn, self.camp["campaign_id"], published_only=True)
        self.assertEqual(len(published_list), 1)
        findings.suppress(self.conn, REVIEWER, finding["finding_id"], self._clock())
        after_suppress = findings.list_for_campaign(self.conn, self.camp["campaign_id"], published_only=True)
        self.assertEqual(after_suppress, [])

    def test_get_published_raises_for_unpublished_finding(self):
        from app.db import DbError
        _candidate, finding, _ = self._candidate_from([("supporting", "Suppliers cancel late payments weekly.")])
        with self.assertRaises(DbError):
            findings.get_published(self.conn, finding["finding_id"])
        findings.publish(self.conn, REVIEWER, finding["finding_id"], self._clock())
        self.assertEqual(findings.get_published(self.conn, finding["finding_id"])["finding_id"],
                        finding["finding_id"])

    def test_recalculate_never_touches_approved_statement_or_approver(self):
        from app import suppression
        obs1, p1, _ = self._approved("Suppliers cancel late payments weekly.")
        obs2, p2, _ = self._approved("Suppliers cancel late payments monthly too.")
        candidate = candidates.create(self.conn, RESEARCHER, self.config, {
            "campaign_id": self.camp["campaign_id"], "finding_type": "pain",
            "statement": "Suppliers cancel late payments.", "proposed_evidence_role": "supporting",
            "observations": [{"observation_id": obs1["observation_id"], "role": "supporting"},
                             {"observation_id": obs2["observation_id"], "role": "supporting"}]}, self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        _approved_candidate, finding = candidates.approve(self.conn, self.config, REVIEWER,
                                                          candidate["candidate_id"], self._clock())
        findings.publish(self.conn, REVIEWER, finding["finding_id"], self._clock())
        suppression.suppress_participant(self.conn, ADMIN, p1["participant_id"], "withdrawn", self._clock())
        after = findings.get(self.conn, finding["finding_id"])
        self.assertEqual(after["approved_statement"], finding["approved_statement"])
        self.assertEqual(after["approved_by"], finding["approved_by"])
        self.assertEqual(after["approved_at"], finding["approved_at"])
        self.assertEqual(after["support_count"], 1)
        self.assertEqual(after["publication_status"], "needs_revalidation")

    def test_finding_becomes_suppressed_when_support_reaches_zero(self):
        from app import suppression
        obs1, p1, _ = self._approved("Suppliers cancel late payments weekly.")
        candidate = candidates.create(self.conn, RESEARCHER, self.config, {
            "campaign_id": self.camp["campaign_id"], "finding_type": "pain",
            "statement": "Suppliers cancel late payments.", "proposed_evidence_role": "supporting",
            "observations": [{"observation_id": obs1["observation_id"], "role": "supporting"}]}, self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        _approved_candidate, finding = candidates.approve(self.conn, self.config, REVIEWER,
                                                          candidate["candidate_id"], self._clock())
        findings.publish(self.conn, REVIEWER, finding["finding_id"], self._clock())
        suppression.suppress_participant(self.conn, ADMIN, p1["participant_id"], "withdrawn", self._clock())
        after = findings.get(self.conn, finding["finding_id"])
        self.assertEqual(after["support_count"], 0)
        self.assertEqual(after["publication_status"], "suppressed")
        self.assertEqual(findings.list_for_campaign(self.conn, self.camp["campaign_id"], published_only=True), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
