"""Phase 4 withdrawal/revalidation cascade tests: suppressing a participant
must cascade through their observations into candidate counts and finding
numerators/denominators/strength/publication_status, with a published
finding never left stale, and every step safely audited (hashes only, no
source content)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (ADMIN, RESEARCHER, REVIEWER, make_active_campaign_with_approved_guide,
                      make_approved_observation, make_dbs)

from app import audit, candidates, findings, suppression
from app.extraction import get_observation


class SuppressionCascadeTests(unittest.TestCase):
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

    def _published_finding_with_two_supporters(self):
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
        return obs1, p1, obs2, p2, candidate, finding

    def test_withdrawal_suppresses_the_participants_observations(self):
        obs1, p1, _obs2, _p2, _candidate, _finding = self._published_finding_with_two_supporters()
        suppression.suppress_participant(self.conn, ADMIN, p1["participant_id"], "withdrawn", self._clock())
        refreshed = get_observation(self.conn, obs1["observation_id"])
        self.assertEqual(refreshed["suppression_status"], "suppressed")
        # observation is retained, not deleted — workflow_status stays approved
        self.assertEqual(refreshed["workflow_status"], "approved")

    def test_withdrawal_removes_suppressed_observations_from_candidate_counts(self):
        obs1, p1, obs2, _p2, candidate, _finding = self._published_finding_with_two_supporters()
        suppression.suppress_participant(self.conn, ADMIN, p1["participant_id"], "withdrawn", self._clock())
        recalculated = candidates.get(self.conn, candidate["candidate_id"])
        self.assertEqual(recalculated["support_count"], 1)
        self.assertEqual(recalculated["included_participant_count"], 1)

    def test_withdrawal_recalculates_finding_numerator_and_denominator(self):
        obs1, p1, obs2, _p2, candidate, finding = self._published_finding_with_two_supporters()
        before_denominator = finding["denominator"]
        result = suppression.suppress_participant(self.conn, ADMIN, p1["participant_id"], "withdrawn",
                                                   self._clock())
        after = findings.get(self.conn, finding["finding_id"])
        self.assertEqual(after["numerator"], 1)
        self.assertLessEqual(after["denominator"], before_denominator)
        self.assertIn(candidate["candidate_id"], result["recalculated_candidates"])

    def test_finding_becomes_needs_revalidation_when_some_support_remains(self):
        obs1, p1, obs2, _p2, _candidate, finding = self._published_finding_with_two_supporters()
        suppression.suppress_participant(self.conn, ADMIN, p1["participant_id"], "withdrawn", self._clock())
        after = findings.get(self.conn, finding["finding_id"])
        self.assertEqual(after["publication_status"], "needs_revalidation")

    def test_finding_becomes_suppressed_when_no_support_remains(self):
        obs1, p1, obs2, p2, _candidate, finding = self._published_finding_with_two_supporters()
        suppression.suppress_participant(self.conn, ADMIN, p1["participant_id"], "withdrawn", self._clock())
        suppression.suppress_participant(self.conn, ADMIN, p2["participant_id"], "withdrawn", self._clock())
        after = findings.get(self.conn, finding["finding_id"])
        self.assertEqual(after["support_count"], 0)
        self.assertEqual(after["publication_status"], "suppressed")

    def test_published_query_immediately_excludes_invalidated_finding(self):
        obs1, p1, obs2, p2, _candidate, finding = self._published_finding_with_two_supporters()
        published = findings.list_for_campaign(self.conn, self.camp["campaign_id"], published_only=True)
        self.assertEqual(len(published), 1)
        suppression.suppress_participant(self.conn, ADMIN, p1["participant_id"], "withdrawn", self._clock())
        suppression.suppress_participant(self.conn, ADMIN, p2["participant_id"], "withdrawn", self._clock())
        published_after = findings.list_for_campaign(self.conn, self.camp["campaign_id"], published_only=True)
        self.assertEqual(published_after, [])

    def test_audit_contains_before_after_counts_not_raw_content(self):
        obs1, p1, obs2, _p2, candidate, finding = self._published_finding_with_two_supporters()
        suppression.suppress_participant(self.conn, ADMIN, p1["participant_id"], "withdrawn", self._clock())
        candidate_events = audit.list_for_object(self.conn, "evidence_candidate", candidate["candidate_id"])
        recalc_event = next(e for e in candidate_events if e["action"] == "recalculate")
        self.assertTrue(recalc_event["before_hash"].startswith("sha256:"))
        self.assertTrue(recalc_event["after_hash"].startswith("sha256:"))
        self.assertNotIn("Suppliers cancel late payments", str(recalc_event))
        self.assertNotIn(p1["participant_id"], str(recalc_event["safe_diff"]))
        finding_events = audit.list_for_object(self.conn, "finding", finding["finding_id"])
        finding_recalc = next(e for e in finding_events if e["action"] == "recalculate")
        self.assertNotIn("Suppliers cancel late payments", str(finding_recalc))

    def test_draft_and_pending_candidates_left_alone_by_cascade(self):
        obs1, p1, _ = self._approved("Suppliers cancel late payments weekly.")
        draft_candidate = candidates.create(self.conn, RESEARCHER, self.config, {
            "campaign_id": self.camp["campaign_id"], "finding_type": "pain",
            "statement": "Suppliers cancel late payments.", "proposed_evidence_role": "supporting",
            "observations": [{"observation_id": obs1["observation_id"], "role": "supporting"}]}, self._clock())
        suppression.suppress_participant(self.conn, ADMIN, p1["participant_id"], "withdrawn", self._clock())
        untouched = candidates.get(self.conn, draft_candidate["candidate_id"])
        self.assertEqual(untouched["workflow_status"], "draft")
        # counts are stale by design until the draft is refreshed/submitted —
        # submit() independently refuses on stale_source_version
        self.assertEqual(untouched["support_count"], 1)

    def test_approved_statement_and_approver_never_touched_by_cascade(self):
        obs1, p1, obs2, _p2, _candidate, finding = self._published_finding_with_two_supporters()
        before_statement = finding["approved_statement"]
        before_approver = finding["approved_by"]
        before_approved_at = finding["approved_at"]
        suppression.suppress_participant(self.conn, ADMIN, p1["participant_id"], "withdrawn", self._clock())
        after = findings.get(self.conn, finding["finding_id"])
        self.assertEqual(after["approved_statement"], before_statement)
        self.assertEqual(after["approved_by"], before_approver)
        self.assertEqual(after["approved_at"], before_approved_at)


if __name__ == "__main__":
    unittest.main(verbosity=2)
