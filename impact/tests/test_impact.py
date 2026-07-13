"""Test matrix for the evidence-impact workflow.

Every test runs against a throwaway temp repo (paths.set_repo_root); no live
knowledge-base evidence, segment, scorecard, history or email data is touched.
No email is ever sent (the email module has no send capability).
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from impact import (apply as apply_mod, email, history, paths, proposal,  # noqa: E402
                    rollback, transaction)
from impact.errors import ImpactError  # noqa: E402

# 17 factors summing to 60, with 8 assumption:true (wtp=3, credit_need=5 among them)
_SCORES = {
    "pain_severity": (4, True), "pain_frequency": (4, True), "financial_impact": (4, True),
    "workaround_cost": (4, True), "switching_intent": (3, False), "willingness_to_pay": (3, True),
    "digital_readiness": (3, False), "payment_volume": (3, False), "credit_need": (5, True),
    "botim_distribution_advantage": (4, False), "transaction_data_advantage": (3, True),
    "payment_revenue_potential": (2, False), "lending_revenue_potential": (4, False),
    "credit_risk_visibility": (3, False), "competitive_defensibility": (3, True),
    "ease_of_validation": (4, False), "mvp_feasibility_7wk": (4, False),
}


def make_scorecard():
    return {
        "opportunity_id": "OPP-TEST", "name": "Synthetic test opportunity",
        "is_lending_product": True, "proposed_classification": "promising",
        "evidence_confidence": "medium", "comment": "test fixture",
        "scores": {k: {"score": s, "assumption": a, "basis": "fixture"} for k, (s, a) in _SCORES.items()},
    }


def make_descriptor():
    return {
        "ev_id": "EV-TEST-001", "evidence_confidence": "medium",
        "evidence_strength": 3, "evidence_class": "workaround spending",
        "observations": [
            {"evidence_field": "willingness_to_pay_signal", "proposed_score": 4,
             "justification": "merchants pay a surcharge today for the faster alternative"},
            {"evidence_field": "credit_need_confirmation", "deassume_only": True,
             "justification": "credit need now evidenced by behavioural data"},
        ],
        "segment": {"segment_id": "SEG-TEST", "current_confidence": "Low",
                    "proposed_confidence": "Medium",
                    "upgrade_rule": "Medium only after multiple independent first-person accounts.",
                    "justification": "two independent first-person accounts now recorded"},
    }


def weak_descriptor():
    return {
        "ev_id": "EV-TEST-002", "evidence_confidence": "low",
        "evidence_strength": 1, "evidence_class": "stated interest",
        "observations": [
            {"evidence_field": "willingness_to_pay_signal", "proposed_score": 4,
             "justification": "anonymous comment: business cards would be useful"},
        ],
    }


SEGMENT_MD = (
    "# SEG-TEST — test segment\n\n"
    "**Created:** 2026-01-01 · **Last verified:** 2026-01-01 · **Confidence:** Low\n\n"
    "> Upgrade condition: Medium only after multiple independent first-person accounts.\n"
)


def build_repo(root):
    kb = Path(root) / "knowledge-base"
    (kb / "opportunity-scores").mkdir(parents=True)
    (kb / "segments").mkdir(parents=True)
    (kb / "opportunity-scores" / "opp-test-scorecard.json").write_text(
        json.dumps(make_scorecard(), indent=2) + "\n", encoding="utf-8")
    (kb / "segments" / "SEG-TEST.md").write_text(SEGMENT_MD, encoding="utf-8")
    paths.set_repo_root(root)
    paths.ensure_dirs()


def write_proposal(prop):
    out = paths.PROPOSALS_DIR / f"{prop['proposal_id']}.json"
    out.write_text(json.dumps(prop, indent=2) + "\n", encoding="utf-8")
    return out


class ImpactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        build_repo(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(lambda: paths.set_repo_root(Path(__file__).resolve().parents[2]))

    def _gen(self, descriptor=None):
        d = descriptor or make_descriptor()
        seg = d.get("segment")
        return proposal.generate(make_scorecard(), d, seg, proposal_id="PROP-TEST-001", today="2026-07-13")

    # 1 — EV-TEST-001 proposes the exact deltas
    def test_ev_test_001_proposal(self):
        prop = self._gen()
        s = prop["payload"]["score_summary"]
        self.assertEqual((s["raw_score_prev"], s["raw_score_new"]), (60, 61))
        self.assertEqual(s["raw_max"], 85)
        self.assertEqual((s["assumption_count_prev"], s["assumption_count_new"]), (8, 6))
        fcs = {f["factor"]: f for f in prop["payload"]["factor_changes"]}
        self.assertEqual(fcs["willingness_to_pay"]["old_score"], 3)
        self.assertEqual(fcs["willingness_to_pay"]["proposed_score"], 4)
        self.assertFalse(fcs["willingness_to_pay"]["proposed_assumption"])
        self.assertEqual(fcs["credit_need"]["change_type"], "deassume-only")
        self.assertEqual(fcs["credit_need"]["old_score"], fcs["credit_need"]["proposed_score"])
        self.assertFalse(fcs["credit_need"]["proposed_assumption"])
        sc = prop["payload"]["segment_changes"][0]
        self.assertEqual((sc["old"], sc["proposed"]), ("Low", "Medium"))
        self.assertEqual(sc["rule_satisfied"], "requires_human_confirmation")

    # 2 — weak/anonymous comment produces no rescore
    def test_weak_comment_no_rescore(self):
        prop = self._gen(weak_descriptor())
        self.assertEqual(prop["payload"]["factor_changes"], [])
        self.assertEqual(prop["payload"]["score_summary"]["raw_score_new"], 60)
        self.assertEqual(prop["payload"]["score_summary"]["alert_tier"], "info")

    # 3 — rejection leaves persistent state unchanged
    def test_reject_no_changes(self):
        prop = self._gen()
        write_proposal(prop)
        card_before = (paths.KB / "opportunity-scores" / "opp-test-scorecard.json").read_text()
        apply_mod.reject_impact("PROP-TEST-001")
        self.assertEqual((paths.KB / "opportunity-scores" / "opp-test-scorecard.json").read_text(), card_before)
        self.assertFalse(paths.SCORE_HISTORY.exists())
        reloaded = json.loads((paths.PROPOSALS_DIR / "PROP-TEST-001.json").read_text())
        self.assertEqual(reloaded["lifecycle"]["status"], "rejected")

    # 4 — approved apply updates all artifacts
    def test_apply_updates_all_artifacts(self):
        write_proposal(self._gen())
        r = apply_mod.apply_impact("PROP-TEST-001", approver="tester", confirm_segment_upgrade=True)
        card = json.loads((paths.KB / "opportunity-scores" / "opp-test-scorecard.json").read_text())
        self.assertEqual(card["scores"]["willingness_to_pay"]["score"], 4)
        self.assertFalse(card["scores"]["willingness_to_pay"]["assumption"])
        self.assertFalse(card["scores"]["credit_need"]["assumption"])
        self.assertIn("**Confidence:** Medium", (paths.KB / "segments" / "SEG-TEST.md").read_text())
        self.assertTrue((paths.ASSUMPTIONS_DIR / "opp-test.json").exists())
        self.assertTrue((paths.MONITORING_DIR / "opp-test-summary.md").exists())
        self.assertTrue((paths.EMAIL_DIR / "PROP-TEST-001.md").exists())
        entries = history.read_all()
        self.assertEqual(len([e for e in entries if e["kind"] == "applied"]), 1)
        self.assertEqual(r["segment_applied"], True)

    # 5 — forced staged-validation failure leaves no partial update
    def test_forced_validation_failure_atomic(self):
        write_proposal(self._gen())
        card_before = (paths.KB / "opportunity-scores" / "opp-test-scorecard.json").read_text()
        seg_before = (paths.KB / "segments" / "SEG-TEST.md").read_text()
        orig = apply_mod._validate_scorecard
        apply_mod._validate_scorecard = lambda c: (_ for _ in ()).throw(ImpactError("forced failure"))
        try:
            with self.assertRaises(ImpactError):
                apply_mod.apply_impact("PROP-TEST-001", approver="tester", confirm_segment_upgrade=True)
        finally:
            apply_mod._validate_scorecard = orig
        self.assertEqual((paths.KB / "opportunity-scores" / "opp-test-scorecard.json").read_text(), card_before)
        self.assertEqual((paths.KB / "segments" / "SEG-TEST.md").read_text(), seg_before)
        self.assertFalse((paths.EMAIL_DIR / "PROP-TEST-001.md").exists())
        self.assertFalse(paths.SCORE_HISTORY.exists() and
                         any(e["kind"] == "applied" for e in history.read_all()))

    # 6 — rollback restores prior values and preserves audit history
    def test_rollback_restores_and_preserves_history(self):
        write_proposal(self._gen())
        r = apply_mod.apply_impact("PROP-TEST-001", approver="tester", confirm_segment_upgrade=True)
        hist_id = r["history_id"]
        rb = rollback.rollback_impact(hist_id, approver="tester")
        card = json.loads((paths.KB / "opportunity-scores" / "opp-test-scorecard.json").read_text())
        self.assertEqual(card["scores"]["willingness_to_pay"]["score"], 3)
        self.assertTrue(card["scores"]["willingness_to_pay"]["assumption"])
        self.assertTrue(card["scores"]["credit_need"]["assumption"])
        self.assertIn("**Confidence:** Low", (paths.KB / "segments" / "SEG-TEST.md").read_text())
        self.assertFalse((paths.ASSUMPTIONS_DIR / "opp-test.json").exists())  # created by apply -> deleted
        kinds = [e["kind"] for e in history.read_all()]
        self.assertIn("applied", kinds)   # original preserved
        self.assertIn("rollback", kinds)  # new entry
        with self.assertRaises(ImpactError):  # cannot roll back twice
            rollback.rollback_impact(hist_id, approver="tester")

    # 7 — email preview: no affirmative overclaim, bounded statement present
    def test_email_no_overclaim(self):
        prop = self._gen()
        text = email.render(prop, segment_applied=True)
        low = text.lower()
        for phrase in email.OVERCLAIMS:
            self.assertNotIn(phrase, low)
        self.assertTrue(any(b in text for b in email.BOUNDED_STATEMENTS))
        with self.assertRaises(ImpactError):
            email._guard("Great news: product validated and build approved.", require_bounded=True)

    # 8 — apply/rollback without approver fail
    def test_approver_required(self):
        write_proposal(self._gen())
        with self.assertRaises(ImpactError):
            apply_mod.apply_impact("PROP-TEST-001", approver="", confirm_segment_upgrade=True)
        # apply properly, then rollback without approver must fail
        r = apply_mod.apply_impact("PROP-TEST-001", approver="tester", confirm_segment_upgrade=True)
        with self.assertRaises(ImpactError):
            rollback.rollback_impact(r["history_id"], approver="")

    # 9 — proposal integrity: tampered payload or stale old-values abort
    def test_proposal_integrity_and_staleness(self):
        prop = self._gen()
        tampered = copy.deepcopy(prop)
        tampered["payload"]["score_summary"]["raw_score_new"] = 99  # edit payload, keep old hash
        with self.assertRaises(ImpactError):
            proposal.verify_integrity(tampered)
        # staleness: live scorecard changes so old_score no longer matches
        write_proposal(prop)
        card = json.loads((paths.KB / "opportunity-scores" / "opp-test-scorecard.json").read_text())
        card["scores"]["willingness_to_pay"]["score"] = 2
        (paths.KB / "opportunity-scores" / "opp-test-scorecard.json").write_text(json.dumps(card, indent=2) + "\n")
        with self.assertRaises(ImpactError):
            apply_mod.apply_impact("PROP-TEST-001", approver="tester", confirm_segment_upgrade=True)

    # 10 — interrupted transaction is auto-recovered; new op refused until re-run
    def test_interruption_recovery(self):
        scpath = str(paths.KB / "opportunity-scores" / "opp-test-scorecard.json")
        original = Path(scpath).read_text()
        # simulate a crash mid-'applying': prepare a txn, mark applying, corrupt the live file
        txn = transaction.Transaction("apply", "PROP-TEST-001", "sha256:x")
        txn.prepare([(scpath, original.replace('"score": 3', '"score": 4'))])
        txn.manifest["status"] = "applying"
        transaction._write_manifest(txn.manifest)
        Path(scpath).write_text("CORRUPTED-PARTIAL-WRITE")  # pretend replace happened then crash
        # a new apply must recover first and refuse
        write_proposal(self._gen())
        with self.assertRaises(ImpactError) as ctx:
            apply_mod.apply_impact("PROP-TEST-001", approver="tester")
        self.assertIn("recovered", str(ctx.exception).lower())
        self.assertEqual(Path(scpath).read_text(), original)  # restored from backup
        self.assertTrue(any(e["kind"] == "recovery" for e in history.read_all()))
        # unresolved cleared -> a re-run now succeeds
        r = apply_mod.apply_impact("PROP-TEST-001", approver="tester")
        self.assertTrue(r["history_id"])

    # 10b — 'preparing' interruption: no live target was changed
    def test_preparing_interruption_no_change(self):
        scpath = str(paths.KB / "opportunity-scores" / "opp-test-scorecard.json")
        original = Path(scpath).read_text()
        txn = transaction.Transaction("apply", "PROP-TEST-001", "sha256:x")
        txn.prepare([(scpath, original.replace('"score": 3', '"score": 4'))])  # status 'preparing'
        recovered = transaction.preflight()
        self.assertTrue(recovered)
        self.assertEqual(Path(scpath).read_text(), original)  # untouched

    # 11 — segment change requires explicit confirmation
    def test_segment_requires_confirmation(self):
        write_proposal(self._gen())
        apply_mod.apply_impact("PROP-TEST-001", approver="tester", confirm_segment_upgrade=False)
        self.assertIn("**Confidence:** Low", (paths.KB / "segments" / "SEG-TEST.md").read_text())
        # scorecard still updated even though segment was not
        card = json.loads((paths.KB / "opportunity-scores" / "opp-test-scorecard.json").read_text())
        self.assertEqual(card["scores"]["willingness_to_pay"]["score"], 4)

    # cross-check: no fan-out allowed
    def test_no_fanout(self):
        from impact import mapping
        with self.assertRaises(ImpactError):
            mapping.assert_no_fanout(["unmapped_field_xyz"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
