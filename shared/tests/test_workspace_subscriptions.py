"""Phase R6 — scheduled-monitoring subscription store: opt-in, DOUBLE OPT-IN
confirmation, multi-recipient support, tokened + self-serve unsubscribe,
cadence bounds, the enabled-subscription count used by the R6 quota, and the
scheduler-facing due/claim surface.

Offline, no network. The subscription/recipient model is the consent layer
every later R6 PR (scheduler, diff-to-email, quota) depends on."""

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.workspace import (WorkspaceStore, WorkspaceStoreError,  # noqa: E402
                              sign_unsubscribe_token)
from shared.workspace import store as ws_store  # noqa: E402

KEY = "test-unsubscribe-signing-key"
OPP = "UOPP-aaaaaaaaaaa1"
OTHER = "UOPP-bbbbbbbbbbb2"
OWNER = "USER-000000000001"
ALICE = "USER-0000000000a1"
BOB = "USER-0000000000b2"


def make_store():
    return WorkspaceStore(Path(tempfile.mkdtemp()) / "workspace.db")


def sub_confirmed(s, opp, owner, user, email, cadence_hours=None):
    """Subscribe and immediately confirm — the common 'eligible recipient'
    setup. Returns the subscribe result (carries the unsubscribe token)."""
    r = s.subscribe(opp, owner, user, email, cadence_hours=cadence_hours)
    if r["confirm_token"]:
        s.confirm_recipient(r["confirm_token"])
    return r


class SubscriptionStore(unittest.TestCase):
    def test_opt_in_is_pending_until_confirmed(self):
        s = make_store()
        result = s.subscribe(OPP, owner_user_id=OWNER, recipient_user_id=ALICE,
                             recipient_email="alice@example.com")
        self.assertTrue(result["confirm_token"])              # raw token, once
        self.assertNotIn("unsubscribe_token", result)         # minted at send time now
        self.assertFalse(result["confirmed"])
        self.assertTrue(result["recipient_id"].startswith("WSUB-"))
        sub = s.get_subscription(OPP)
        # NOT eligible yet: the parent stays disabled until a recipient confirms
        self.assertFalse(sub["enabled"])
        self.assertEqual(sub["cadence_hours"], 6)
        rec = sub["recipients"][0]
        self.assertFalse(rec["confirmed"])
        self.assertTrue(rec["pending_confirmation"])
        # no token hashes ever leak through the read model
        self.assertNotIn("unsubscribe_token_hash", str(sub))
        self.assertNotIn("confirm_token_hash", str(sub))

    def test_confirmation_makes_the_recipient_eligible(self):
        s = make_store()
        r = s.subscribe(OPP, OWNER, ALICE, "alice@example.com")
        out = s.confirm_recipient(r["confirm_token"])
        self.assertTrue(out["confirmed"])
        self.assertEqual(out["recipient_email"], "alice@example.com")
        sub = s.get_subscription(OPP)
        self.assertTrue(sub["enabled"])                       # now eligible
        self.assertTrue(sub["recipients"][0]["confirmed"])
        self.assertFalse(sub["recipients"][0]["pending_confirmation"])

    def test_confirm_token_is_single_use_and_unknown_is_404(self):
        s = make_store()
        r = s.subscribe(OPP, OWNER, ALICE, "alice@example.com")
        s.confirm_recipient(r["confirm_token"])
        # the token was cleared on use -> a second confirm is a 404
        with self.assertRaises(WorkspaceStoreError) as cm:
            s.confirm_recipient(r["confirm_token"])
        self.assertEqual(cm.exception.status, 404)
        with self.assertRaises(WorkspaceStoreError):
            s.confirm_recipient("never-issued")

    def test_expired_confirmation_link_is_refused(self):
        s = make_store()
        r = s.subscribe(OPP, OWNER, ALICE, "alice@example.com")
        # force the stored expiry into the past
        import sqlite3
        conn = sqlite3.connect(s.db_path)
        conn.execute("UPDATE workspace_subscription_recipients "
                     "SET confirm_expires_at='2000-01-01T00:00:00Z'")
        conn.commit()
        conn.close()
        with self.assertRaises(WorkspaceStoreError) as cm:
            s.confirm_recipient(r["confirm_token"])
        self.assertEqual(cm.exception.status, 410)
        self.assertFalse(s.get_subscription(OPP)["enabled"])

    def test_already_confirmed_reopt_in_needs_no_new_confirmation(self):
        s = make_store()
        sub_confirmed(s, OPP, OWNER, ALICE, "alice@example.com")
        again = s.subscribe(OPP, OWNER, ALICE, "alice@example.com", cadence_hours=12)
        self.assertIsNone(again["confirm_token"])             # nothing to confirm
        self.assertTrue(again["confirmed"])
        sub = s.get_subscription(OPP)
        self.assertTrue(sub["enabled"])                       # stays eligible
        self.assertEqual(sub["cadence_hours"], 12)            # cadence still updates

    def test_changing_email_forces_reconfirmation(self):
        s = make_store()
        sub_confirmed(s, OPP, OWNER, ALICE, "alice@example.com")
        changed = s.subscribe(OPP, OWNER, ALICE, "alice@new.example.com")
        self.assertTrue(changed["confirm_token"])             # must re-confirm
        self.assertFalse(changed["confirmed"])
        self.assertFalse(s.get_subscription(OPP)["enabled"])  # ineligible until re-confirmed

    def test_multiple_recipients_per_chat_are_supported_now(self):
        s = make_store()
        sub_confirmed(s, OPP, OWNER, ALICE, "alice@example.com")
        sub_confirmed(s, OPP, OWNER, BOB, "bob@example.com")
        emails = sorted(r["recipient_email"] for r in s.get_subscription(OPP)["recipients"])
        self.assertEqual(emails, ["alice@example.com", "bob@example.com"])

    def test_signed_unsubscribe_token_is_stable_and_works(self):
        s = make_store()
        first = s.subscribe(OPP, OWNER, ALICE, "alice@example.com")
        second = s.subscribe(OPP, OWNER, ALICE, "alice@example.com")
        self.assertEqual(first["recipient_id"], second["recipient_id"])  # same row
        self.assertEqual(len(s.get_subscription(OPP)["recipients"]), 1)  # not duplicated
        # the deterministic token is stable across every email (no rotation)
        tok = sign_unsubscribe_token(first["recipient_id"], KEY)
        self.assertEqual(tok, sign_unsubscribe_token(second["recipient_id"], KEY))
        self.assertTrue(s.unsubscribe_by_token(tok, KEY)["unsubscribed"])

    def test_self_serve_unsubscribe_disables_only_that_recipient(self):
        s = make_store()
        sub_confirmed(s, OPP, OWNER, ALICE, "alice@example.com")
        sub_confirmed(s, OPP, OWNER, BOB, "bob@example.com")
        out = s.unsubscribe_recipient(OPP, ALICE)
        self.assertTrue(out["unsubscribed"])
        self.assertEqual(out["active_recipients"], 1)         # Bob still eligible
        sub = s.get_subscription(OPP)
        self.assertTrue(sub["enabled"])
        by_user = {r["recipient_user_id"]: r["enabled"] for r in sub["recipients"]}
        self.assertEqual(by_user, {ALICE: False, BOB: True})

    def test_last_eligible_recipient_leaving_disables_the_subscription(self):
        s = make_store()
        sub_confirmed(s, OPP, OWNER, ALICE, "alice@example.com")
        self.assertEqual(s.unsubscribe_recipient(OPP, ALICE)["active_recipients"], 0)
        self.assertFalse(s.get_subscription(OPP)["enabled"])

    def test_tokened_unsubscribe_targets_exactly_one_recipient(self):
        s = make_store()
        a = sub_confirmed(s, OPP, OWNER, ALICE, "alice@example.com")
        sub_confirmed(s, OPP, OWNER, BOB, "bob@example.com")
        out = s.unsubscribe_by_token(sign_unsubscribe_token(a["recipient_id"], KEY), KEY)
        self.assertEqual(out["recipient_email"], "alice@example.com")
        by_user = {r["recipient_user_id"]: r["enabled"]
                   for r in s.get_subscription(OPP)["recipients"]}
        self.assertEqual(by_user, {ALICE: False, BOB: True})

    def test_unknown_or_tampered_unsubscribe_token_is_a_404(self):
        s = make_store()
        r = s.subscribe(OPP, OWNER, ALICE, "alice@example.com")
        for bad in ("nope-not-a-real-token", "WSUB-000000000000.badsig",
                    sign_unsubscribe_token(r["recipient_id"], KEY) + "x"):
            with self.assertRaises(WorkspaceStoreError) as cm:
                s.unsubscribe_by_token(bad, KEY)
            self.assertEqual(cm.exception.status, 404)

    def test_unsubscribe_token_from_a_rotated_key_is_rejected(self):
        # rotating the signing key silently invalidates old links (documented)
        s = make_store()
        r = s.subscribe(OPP, OWNER, ALICE, "alice@example.com")
        good = sign_unsubscribe_token(r["recipient_id"], KEY)
        with self.assertRaises(WorkspaceStoreError):
            s.unsubscribe_by_token(good, "a-different-rotated-key")

    def test_cadence_is_bounded_and_defaulted(self):
        s = make_store()
        s.subscribe(OPP, OWNER, ALICE, "alice@example.com", cadence_hours=12)
        self.assertEqual(s.get_subscription(OPP)["cadence_hours"], 12)
        for bad in (0, 1, ws_store.MAX_CADENCE_HOURS + 1, "6", 6.0, True):
            with self.assertRaises(WorkspaceStoreError):
                s.subscribe(OTHER, OWNER, ALICE, "alice@example.com", cadence_hours=bad)

    def test_owner_and_valid_email_are_required(self):
        s = make_store()
        with self.assertRaises(WorkspaceStoreError):
            s.subscribe(OPP, owner_user_id="", recipient_user_id=ALICE,
                        recipient_email="alice@example.com")
        with self.assertRaises(WorkspaceStoreError):
            s.subscribe(OPP, OWNER, ALICE, "not-an-email")
        with self.assertRaises(WorkspaceStoreError):
            s.subscribe(OPP, OWNER, ALICE, "")

    def test_count_enabled_subscriptions_counts_only_eligible(self):
        s = make_store()
        self.assertEqual(s.count_enabled_subscriptions(OWNER), 0)
        s.subscribe(OPP, OWNER, ALICE, "alice@example.com")   # pending -> not counted
        self.assertEqual(s.count_enabled_subscriptions(OWNER), 0)
        s.confirm_recipient(s.subscribe(OTHER, OWNER, ALICE, "alice@example.com")["confirm_token"])
        self.assertEqual(s.count_enabled_subscriptions(OWNER), 1)

    def test_dormancy_reason_is_recorded_and_distinct(self):
        s = make_store()
        r = s.subscribe(OPP, OWNER, ALICE, "alice@example.com")
        # pending confirmation is a distinct, honest dormancy reason
        self.assertEqual(s.get_subscription(OPP)["last_outcome"],
                         "dormant_pending_confirmation")
        # becoming eligible clears the dormancy marker (no run has happened yet)
        s.confirm_recipient(r["confirm_token"])
        self.assertIsNone(s.get_subscription(OPP)["last_outcome"])
        # everyone unsubscribing is a DIFFERENT reason from never-confirmed
        s.unsubscribe_recipient(OPP, ALICE)
        self.assertEqual(s.get_subscription(OPP)["last_outcome"],
                         "dormant_all_unsubscribed")

    def test_real_run_outcome_is_not_clobbered_while_still_eligible(self):
        s = make_store()
        s.confirm_recipient(s.subscribe(OPP, OWNER, ALICE, "a@example.com")["confirm_token"])
        s.record_run_result(OPP, "built", ran_at="2026-07-19T10:00:00Z")
        # a second recipient opting in recomputes eligibility but must NOT wipe
        # the real run outcome (still eligible, so no dormancy marker applies)
        s.subscribe(OPP, OWNER, BOB, "b@example.com")
        self.assertEqual(s.get_subscription(OPP)["last_outcome"], "built")

    def test_get_subscription_none_when_absent(self):
        self.assertIsNone(make_store().get_subscription(OPP))

    def test_subscription_survives_store_reopen(self):
        tmp = Path(tempfile.mkdtemp()) / "workspace.db"
        WorkspaceStore(tmp).subscribe(OPP, OWNER, ALICE, "alice@example.com")
        reopened = WorkspaceStore(tmp)
        self.assertEqual(len(reopened.get_subscription(OPP)["recipients"]), 1)


class TickScheduling(unittest.TestCase):
    """The scheduler-facing store surface: due-selection and the atomic
    claim-and-advance that makes an at-least-once cron idempotent. A chat is
    only schedulable once it has a CONFIRMED recipient."""

    def _due_store(self):
        s = make_store()
        sub_confirmed(s, OPP, OWNER, ALICE, "alice@example.com", cadence_hours=6)
        import sqlite3
        conn = sqlite3.connect(s.db_path)
        conn.execute("UPDATE workspace_subscriptions SET next_run_at=? "
                     "WHERE opportunity_id=?", ("2000-01-01T00:00:00Z", OPP))
        conn.commit()
        conn.close()
        return s

    def test_unconfirmed_subscription_is_never_due(self):
        s = make_store()
        s.subscribe(OPP, OWNER, ALICE, "alice@example.com")   # pending confirmation
        import sqlite3
        conn = sqlite3.connect(s.db_path)
        conn.execute("UPDATE workspace_subscriptions SET next_run_at='2000-01-01T00:00:00Z'")
        conn.commit()
        conn.close()
        # past-due on the clock, but ineligible (unconfirmed) -> not scheduled
        self.assertEqual(s.due_subscriptions(), [])
        self.assertIsNone(s.claim_due(OPP))

    def test_freshly_confirmed_is_not_immediately_due(self):
        s = make_store()
        sub_confirmed(s, OPP, OWNER, ALICE, "alice@example.com", cadence_hours=6)
        self.assertEqual(s.due_subscriptions(), [])

    def test_due_subscriptions_lists_a_past_due_confirmed_row(self):
        s = self._due_store()
        due = s.due_subscriptions()
        self.assertEqual([d["opportunity_id"] for d in due], [OPP])
        self.assertEqual(due[0]["owner_user_id"], OWNER)

    def test_claim_due_is_idempotent_a_second_claim_returns_none(self):
        s = self._due_store()
        claimed = s.claim_due(OPP)
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["owner_user_id"], OWNER)
        self.assertIsNone(s.claim_due(OPP))                   # advanced -> not due
        self.assertEqual(s.due_subscriptions(), [])

    def test_record_run_result_advances_last_run_only_when_a_build_ran(self):
        s = self._due_store()
        s.claim_due(OPP)
        s.record_run_result(OPP, "skipped_in_progress")
        sub = s.get_subscription(OPP)
        self.assertEqual(sub["last_outcome"], "skipped_in_progress")
        self.assertIsNone(sub["last_run_at"])
        s.record_run_result(OPP, "built", ran_at="2026-07-19T10:00:00Z",
                            last_notified_version=4)
        sub = s.get_subscription(OPP)
        self.assertEqual(sub["last_outcome"], "built")
        self.assertEqual(sub["last_run_at"], "2026-07-19T10:00:00Z")
        self.assertEqual(sub["last_notified_version"], 4)


if __name__ == "__main__":
    unittest.main()
