"""Phase R6 (PR6a) — scheduled-monitoring subscription store: opt-in,
multi-recipient support, tokened + self-serve unsubscribe, cadence bounds,
owner requirement, and the enabled-subscription count used by the R6 quota.

Offline, no network. The subscription/recipient model is the consent layer
every later R6 PR (scheduler, diff-to-email, quota) depends on."""

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.workspace import WorkspaceStore, WorkspaceStoreError  # noqa: E402
from shared.workspace import store as ws_store  # noqa: E402

OPP = "UOPP-aaaaaaaaaaa1"
OTHER = "UOPP-bbbbbbbbbbb2"
OWNER = "USER-000000000001"
ALICE = "USER-0000000000a1"
BOB = "USER-0000000000b2"


def make_store():
    return WorkspaceStore(Path(tempfile.mkdtemp()) / "workspace.db")


class SubscriptionStore(unittest.TestCase):
    def test_opt_in_creates_subscription_and_returns_a_token_once(self):
        s = make_store()
        result = s.subscribe(OPP, owner_user_id=OWNER, recipient_user_id=ALICE,
                             recipient_email="alice@example.com")
        self.assertTrue(result["unsubscribe_token"])          # raw token, once
        self.assertTrue(result["recipient_id"].startswith("WSUB-"))
        sub = s.get_subscription(OPP)
        self.assertTrue(sub["enabled"])
        self.assertEqual(sub["owner_user_id"], OWNER)
        self.assertEqual(sub["cadence_hours"], 6)             # default band
        self.assertIsNotNone(sub["next_run_at"])              # scheduled forward
        self.assertEqual(len(sub["recipients"]), 1)
        self.assertEqual(sub["recipients"][0]["recipient_email"], "alice@example.com")
        # the token HASH is never exposed through the read model
        self.assertNotIn("unsubscribe_token_hash", sub)
        self.assertNotIn("unsubscribe_token_hash", sub["recipients"][0])

    def test_multiple_recipients_per_chat_are_supported_now(self):
        s = make_store()
        s.subscribe(OPP, OWNER, ALICE, "alice@example.com")
        s.subscribe(OPP, OWNER, BOB, "bob@example.com")
        sub = s.get_subscription(OPP)
        emails = sorted(r["recipient_email"] for r in sub["recipients"])
        self.assertEqual(emails, ["alice@example.com", "bob@example.com"])

    def test_reopt_in_is_idempotent_and_rotates_the_token(self):
        s = make_store()
        first = s.subscribe(OPP, OWNER, ALICE, "alice@example.com")
        second = s.subscribe(OPP, OWNER, ALICE, "alice@new.example.com")
        self.assertEqual(first["recipient_id"], second["recipient_id"])  # same row
        self.assertNotEqual(first["unsubscribe_token"], second["unsubscribe_token"])
        sub = s.get_subscription(OPP)
        self.assertEqual(len(sub["recipients"]), 1)                      # not duplicated
        self.assertEqual(sub["recipients"][0]["recipient_email"], "alice@new.example.com")
        # the old token no longer resolves; the new one does
        with self.assertRaises(WorkspaceStoreError):
            s.unsubscribe_by_token(first["unsubscribe_token"])
        out = s.unsubscribe_by_token(second["unsubscribe_token"])
        self.assertTrue(out["unsubscribed"])

    def test_self_serve_unsubscribe_disables_only_that_recipient(self):
        s = make_store()
        s.subscribe(OPP, OWNER, ALICE, "alice@example.com")
        s.subscribe(OPP, OWNER, BOB, "bob@example.com")
        out = s.unsubscribe_recipient(OPP, ALICE)
        self.assertTrue(out["unsubscribed"])
        self.assertEqual(out["active_recipients"], 1)
        sub = s.get_subscription(OPP)
        self.assertTrue(sub["enabled"])                        # Bob remains
        by_user = {r["recipient_user_id"]: r["enabled"] for r in sub["recipients"]}
        self.assertEqual(by_user, {ALICE: False, BOB: True})

    def test_last_recipient_leaving_disables_the_subscription(self):
        s = make_store()
        s.subscribe(OPP, OWNER, ALICE, "alice@example.com")
        out = s.unsubscribe_recipient(OPP, ALICE)
        self.assertEqual(out["active_recipients"], 0)
        self.assertFalse(s.get_subscription(OPP)["enabled"])

    def test_tokened_unsubscribe_targets_exactly_one_recipient(self):
        s = make_store()
        a = s.subscribe(OPP, OWNER, ALICE, "alice@example.com")
        s.subscribe(OPP, OWNER, BOB, "bob@example.com")
        out = s.unsubscribe_by_token(a["unsubscribe_token"])
        self.assertEqual(out["recipient_email"], "alice@example.com")
        by_user = {r["recipient_user_id"]: r["enabled"]
                   for r in s.get_subscription(OPP)["recipients"]}
        self.assertEqual(by_user, {ALICE: False, BOB: True})

    def test_unknown_token_is_a_404_not_a_silent_noop(self):
        s = make_store()
        with self.assertRaises(WorkspaceStoreError) as cm:
            s.unsubscribe_by_token("nope-not-a-real-token")
        self.assertEqual(cm.exception.status, 404)

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

    def test_count_enabled_subscriptions_powers_quota_scaling(self):
        s = make_store()
        self.assertEqual(s.count_enabled_subscriptions(OWNER), 0)
        s.subscribe(OPP, OWNER, ALICE, "alice@example.com")
        s.subscribe(OTHER, OWNER, ALICE, "alice@example.com")
        self.assertEqual(s.count_enabled_subscriptions(OWNER), 2)
        s.unsubscribe_recipient(OTHER, ALICE)                  # disables OTHER
        self.assertEqual(s.count_enabled_subscriptions(OWNER), 1)

    def test_get_subscription_none_when_absent(self):
        self.assertIsNone(make_store().get_subscription(OPP))

    def test_subscription_survives_store_reopen(self):
        # re-instantiating the store re-runs the idempotent PRAGMA-guarded
        # schema init; the subscription must persist across a restart
        tmp = Path(tempfile.mkdtemp()) / "workspace.db"
        WorkspaceStore(tmp).subscribe(OPP, OWNER, ALICE, "alice@example.com")
        reopened = WorkspaceStore(tmp)
        self.assertEqual(len(reopened.get_subscription(OPP)["recipients"]), 1)


class TickScheduling(unittest.TestCase):
    """The scheduler-facing store surface: due-selection and the atomic
    claim-and-advance that makes an at-least-once cron idempotent."""

    def _due_store(self):
        s = make_store()
        s.subscribe(OPP, OWNER, ALICE, "alice@example.com", cadence_hours=6)
        # force the subscription due (opt-in schedules it one cadence forward)
        import sqlite3
        conn = sqlite3.connect(s.db_path)
        conn.execute("UPDATE workspace_subscriptions SET next_run_at=? "
                     "WHERE opportunity_id=?", ("2000-01-01T00:00:00Z", OPP))
        conn.commit()
        conn.close()
        return s

    def test_freshly_subscribed_is_not_immediately_due(self):
        s = make_store()
        s.subscribe(OPP, OWNER, ALICE, "alice@example.com", cadence_hours=6)
        self.assertEqual(s.due_subscriptions(), [])

    def test_due_subscriptions_lists_a_past_due_row(self):
        s = self._due_store()
        due = s.due_subscriptions()
        self.assertEqual([d["opportunity_id"] for d in due], [OPP])
        self.assertEqual(due[0]["owner_user_id"], OWNER)

    def test_claim_due_is_idempotent_a_second_claim_returns_none(self):
        s = self._due_store()
        claimed = s.claim_due(OPP)
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["owner_user_id"], OWNER)
        # the advance moved next_run_at into the future -> no longer due
        self.assertIsNone(s.claim_due(OPP))
        self.assertEqual(s.due_subscriptions(), [])

    def test_claim_due_none_when_not_due_or_disabled(self):
        s = make_store()
        s.subscribe(OPP, OWNER, ALICE, "alice@example.com")   # scheduled forward
        self.assertIsNone(s.claim_due(OPP))                   # not due yet
        s2 = self._due_store()
        s2.unsubscribe_recipient(OPP, ALICE)                  # disables the sub
        self.assertIsNone(s2.claim_due(OPP))                  # due but disabled

    def test_record_run_result_advances_last_run_only_when_a_build_ran(self):
        s = self._due_store()
        s.claim_due(OPP)
        # a skip records the outcome but NEVER advances last_run_at
        s.record_run_result(OPP, "skipped_in_progress")
        sub = s.get_subscription(OPP)
        self.assertEqual(sub["last_outcome"], "skipped_in_progress")
        self.assertIsNone(sub["last_run_at"])
        # a real build advances last_run_at and can set last_notified_version
        s.record_run_result(OPP, "built", ran_at="2026-07-19T10:00:00Z",
                            last_notified_version=4)
        sub = s.get_subscription(OPP)
        self.assertEqual(sub["last_outcome"], "built")
        self.assertEqual(sub["last_run_at"], "2026-07-19T10:00:00Z")
        self.assertEqual(sub["last_notified_version"], 4)


if __name__ == "__main__":
    unittest.main()
