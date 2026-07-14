"""Synthetic-only export tests: gating, server-generated filename, path
containment, synthetic banner, no EV ID, no authoritative write, safe
audit, and re-invalidation of a previously-exported proposal."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (ADMIN, RESEARCHER, REVIEWER, make_active_campaign_with_approved_guide,
                      make_approved_observation, make_dbs)

from app import audit, candidates, findings, part_a_proposal, suppression
from app.config import Config
from app.models import Phase5Error


class SyntheticExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.export_root = tempfile.TemporaryDirectory()
        self.addCleanup(self.export_root.cleanup)
        self.conn, self.identity_conn, self.config = make_dbs(self.tmp.name)
        self.clock_n = 0
        self.camp, self.guide = make_active_campaign_with_approved_guide(self.conn, self.config, self._clock)

    def _clock(self):
        self.clock_n += 1
        return f"2026-01-01T00:00:{self.clock_n:02d}Z"

    def _ready_proposal(self, participant_count=1, synthetic=True, data_classification=None):
        texts = [f"Suppliers cancel late payments every week (#{i})." for i in range(participant_count)]
        observations = []
        participants_out = []
        for text in texts:
            obs, participant, _ = make_approved_observation(
                self.conn, self.identity_conn, self.config, self._clock, self.camp, self.guide, text)
            observations.append({"observation_id": obs["observation_id"], "role": "supporting"})
            participants_out.append(participant)
        candidate = candidates.create(self.conn, RESEARCHER, self.config, {
            "campaign_id": self.camp["campaign_id"], "finding_type": "pain",
            "statement": "Suppliers cancel late payments.", "proposed_evidence_role": "supporting",
            "observations": observations}, self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        _approved_candidate, finding = candidates.approve(self.conn, self.config, REVIEWER,
                                                          candidate["candidate_id"], self._clock())
        findings.publish(self.conn, REVIEWER, finding["finding_id"], self._clock())
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        part_a_proposal.submit(self.conn, RESEARCHER, proposal["proposal_id"], self._clock())
        proposal = part_a_proposal.approve(self.conn, self.config, REVIEWER, proposal["proposal_id"],
                                          self._clock())
        return proposal, finding, participants_out

    def test_synthetic_export_allowed_after_approval(self):
        proposal, _finding, _ = self._ready_proposal()
        part_a_proposal.approve_export(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock())
        exported = part_a_proposal.export(self.conn, self.config, REVIEWER, proposal["proposal_id"],
                                         self._clock(), Path(self.export_root.name))
        self.assertEqual(exported["export_status"], "exported")
        self.assertEqual(exported["publication_status"], "exported_synthetic")

    def test_non_synthetic_export_forbidden(self):
        non_synth_config = Config(env={"MV_TOKENS": "a:t:admin", "MV_SYNTHETIC_ONLY": "0"})
        camp, guide = make_active_campaign_with_approved_guide(
            self.conn, non_synth_config, self._clock, campaign_overrides={"data_classification": "internal"})
        obs, _, _ = make_approved_observation(self.conn, self.identity_conn, non_synth_config, self._clock,
                                              camp, guide, "Suppliers cancel late payments every week.")
        candidate = candidates.create(self.conn, RESEARCHER, non_synth_config, {
            "campaign_id": camp["campaign_id"], "finding_type": "pain",
            "statement": "Suppliers cancel late payments.", "proposed_evidence_role": "supporting",
            "observations": [{"observation_id": obs["observation_id"], "role": "supporting"}]}, self._clock())
        candidates.submit(self.conn, RESEARCHER, candidate["candidate_id"], self._clock())
        _approved_candidate, finding = candidates.approve(self.conn, non_synth_config, REVIEWER,
                                                          candidate["candidate_id"], self._clock())
        findings.publish(self.conn, REVIEWER, finding["finding_id"], self._clock())
        proposal = part_a_proposal.generate(self.conn, RESEARCHER, finding["finding_id"], self._clock())
        part_a_proposal.submit(self.conn, RESEARCHER, proposal["proposal_id"], self._clock())
        proposal = part_a_proposal.approve(self.conn, non_synth_config, REVIEWER, proposal["proposal_id"],
                                          self._clock())
        part_a_proposal.approve_export(self.conn, non_synth_config, REVIEWER, proposal["proposal_id"],
                                       self._clock())
        with self.assertRaises(Phase5Error) as ctx:
            part_a_proposal.export(self.conn, non_synth_config, REVIEWER, proposal["proposal_id"], self._clock(),
                                  Path(self.export_root.name))
        self.assertEqual(ctx.exception.code, "non_synthetic_export_forbidden")
        for prereq in ("privacy approval", "Workstream A approval"):
            self.assertIn(prereq, str(ctx.exception))
        self.assertFalse((Path(self.export_root.name) / "knowledge-base").exists())

    def test_export_requires_reviewer_or_admin(self):
        from app.auth import AuthError
        proposal, _finding, _ = self._ready_proposal()
        part_a_proposal.approve_export(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock())
        with self.assertRaises(AuthError):
            part_a_proposal.export(self.conn, self.config, RESEARCHER, proposal["proposal_id"], self._clock(),
                                  Path(self.export_root.name))

    def test_export_requires_export_approval(self):
        proposal, _finding, _ = self._ready_proposal()
        with self.assertRaises(Phase5Error) as ctx:
            part_a_proposal.export(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock(),
                                  Path(self.export_root.name))
        self.assertEqual(ctx.exception.code, "proposal_not_exportable")

    def test_export_filename_server_generated(self):
        proposal, _finding, _ = self._ready_proposal()
        part_a_proposal.approve_export(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock())
        exported = part_a_proposal.export(self.conn, self.config, REVIEWER, proposal["proposal_id"],
                                         self._clock(), Path(self.export_root.name))
        self.assertTrue(exported["export_path"].endswith(f"{proposal['proposal_id']}.md"))
        self.assertIn("merchant-voice-candidates", exported["export_path"])

    def test_user_path_ignored_or_rejected(self):
        """export() takes no path/filename argument at all — there is
        structurally no parameter through which a caller could supply one."""
        import inspect
        sig = inspect.signature(part_a_proposal.export)
        self.assertNotIn("path", sig.parameters)
        self.assertNotIn("filename", sig.parameters)

    def test_export_stays_inside_approved_folder(self):
        proposal, _finding, _ = self._ready_proposal()
        part_a_proposal.approve_export(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock())
        exported = part_a_proposal.export(self.conn, self.config, REVIEWER, proposal["proposal_id"],
                                         self._clock(), Path(self.export_root.name))
        full_path = Path(self.export_root.name) / exported["export_path"]
        expected_dir = Path(self.export_root.name, "knowledge-base", "customer-evidence",
                            "merchant-voice-candidates").resolve()
        self.assertEqual(full_path.resolve().parent, expected_dir)

    def test_export_contains_synthetic_banner(self):
        proposal, _finding, _ = self._ready_proposal()
        part_a_proposal.approve_export(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock())
        exported = part_a_proposal.export(self.conn, self.config, REVIEWER, proposal["proposal_id"],
                                         self._clock(), Path(self.export_root.name))
        content = (Path(self.export_root.name) / exported["export_path"]).read_text(encoding="utf-8")
        self.assertIn("SYNTHETIC DATA — DEMO ONLY", content)
        self.assertIn("NOT AUTHORITATIVE PART A EVIDENCE", content)
        self.assertIn("REQUIRES WORKSTREAM A REVIEW", content)

    def test_export_contains_no_ev_id(self):
        proposal, _finding, _ = self._ready_proposal()
        part_a_proposal.approve_export(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock())
        exported = part_a_proposal.export(self.conn, self.config, REVIEWER, proposal["proposal_id"],
                                         self._clock(), Path(self.export_root.name))
        content = (Path(self.export_root.name) / exported["export_path"]).read_text(encoding="utf-8")
        self.assertIn("authoritative_ev_id: None", content)
        import re
        self.assertIsNone(re.search(r"\bEV-\d{4}-W\d{2}-\d{3}\b", content))

    def test_export_does_not_write_authoritative_record(self):
        proposal, _finding, _ = self._ready_proposal()
        part_a_proposal.approve_export(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock())
        part_a_proposal.export(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock(),
                              Path(self.export_root.name))
        records_dir = Path(self.export_root.name, "knowledge-base", "customer-evidence", "records")
        self.assertFalse(records_dir.exists())

    def test_export_audit_safe(self):
        proposal, _finding, _ = self._ready_proposal()
        part_a_proposal.approve_export(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock())
        part_a_proposal.export(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock(),
                              Path(self.export_root.name))
        events = audit.list_for_object(self.conn, "part_a_proposal", proposal["proposal_id"])
        complete_event = next(e for e in events if e["action"] == "export_completed")
        self.assertNotIn("Suppliers cancel late payments", str(complete_event))
        self.assertIn("export_path", complete_event["safe_diff"])

    def test_previously_exported_proposal_flagged_after_invalidation(self):
        proposal, _finding, participants_out = self._ready_proposal(participant_count=1)
        part_a_proposal.approve_export(self.conn, self.config, REVIEWER, proposal["proposal_id"], self._clock())
        exported = part_a_proposal.export(self.conn, self.config, REVIEWER, proposal["proposal_id"],
                                         self._clock(), Path(self.export_root.name))
        self.assertEqual(exported["export_status"], "exported")
        suppression.suppress_participant(self.conn, ADMIN, participants_out[0]["participant_id"], "withdrawn",
                                         self._clock())
        after = part_a_proposal.get(self.conn, proposal["proposal_id"])
        self.assertEqual(after["export_status"], "exported")  # the export record itself is preserved
        self.assertIn(after["publication_status"], ("needs_revalidation", "suppressed"))
        self.assertIsNotNone(after["needs_revalidation_reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
