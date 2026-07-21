"""Phase R10 / PR10b — draft question-set store tests (persistence, bounds,
ownership). Offline, pure."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from shared.questions import QuestionSetStore, QuestionStoreError


def make_store(path=None):
    return QuestionSetStore(path or Path(tempfile.mkdtemp()) / "question-sets.db")


def q(text="What do you do today when a supplier payment is late?",
      purpose="behaviour", asm="ASM-OPP-001-workaround_cost"):
    return {"text": text, "purpose": purpose, "question_type": "open_text",
            "follow_up_prompts": ["How often?"], "linked_assumption": asm,
            "signals": ["open_gap", "no_supporting_evidence"], "source_weak_link_rank": 1}


class CreateReadTests(unittest.TestCase):
    def test_create_assigns_ids_and_defaults_draft(self):
        s = make_store()
        st = s.create("OPP-001", [q(), q(text="Would you pay for faster settlement?", purpose="willingness_to_pay")],
                      provenance={"model": "stub"}, rejected_count=1)
        self.assertRegex(st["id"], r"^RQSET-[0-9a-f]{12}$")
        self.assertEqual(st["status"], "draft")
        self.assertEqual(st["rejected_count"], 1)
        self.assertEqual([qq["question_id"] for qq in st["questions"]],
                         [f"{st['id']}-Q1", f"{st['id']}-Q2"])
        self.assertEqual(st["questions"][0]["linked_assumption"], "ASM-OPP-001-workaround_cost")

    def test_persists_across_reopen(self):
        d = Path(tempfile.mkdtemp()) / "qs.db"
        s1 = make_store(d)
        sid = s1.create("OPP-001", [q()])["id"]
        self.assertEqual(make_store(d).get(sid)["id"], sid)

    def test_list_filter_by_opportunity(self):
        s = make_store()
        s.create("OPP-001", [q()])
        s.create("OPP-002", [q()])
        self.assertEqual(len(s.list()), 2)
        self.assertEqual(len(s.list(opportunity_id="OPP-001")), 1)


class OwnershipTests(unittest.TestCase):
    def test_foreign_row_is_404(self):
        s = make_store()
        sid = s.create("OPP-001", [q()], owner_user_id="USER-a")["id"]
        with self.assertRaises(QuestionStoreError) as cm:
            s.get(sid, visible_to="USER-b")
        self.assertEqual(cm.exception.status, 404)
        self.assertEqual(s.get(sid, visible_to="USER-a")["id"], sid)

    def test_legacy_null_owner_shared(self):
        s = make_store()
        sid = s.create("OPP-001", [q()], owner_user_id=None)["id"]
        self.assertEqual(s.get(sid, visible_to="USER-b")["id"], sid)

    def test_list_scopes_to_owner_plus_shared(self):
        s = make_store()
        s.create("OPP-001", [q()], owner_user_id="USER-a")
        s.create("OPP-001", [q()], owner_user_id="USER-b")
        s.create("OPP-001", [q()], owner_user_id=None)
        self.assertEqual(len(s.list(visible_to="USER-a")), 2)
        self.assertEqual(len(s.list(visible_to=None)), 3)


class ValidationTests(unittest.TestCase):
    def test_bad_opportunity_rejected(self):
        s = make_store()
        with self.assertRaises(QuestionStoreError):
            s.create("UOPP-0123456789ab", [q()])   # R10 targets committed OPP-nnn
        with self.assertRaises(QuestionStoreError):
            s.create("not-an-id", [q()])

    def test_empty_text_rejected(self):
        s = make_store()
        with self.assertRaises(QuestionStoreError):
            s.create("OPP-001", [{"text": "  ", "purpose": "behaviour"}])

    def test_bad_id_shape_400(self):
        s = make_store()
        with self.assertRaises(QuestionStoreError) as cm:
            s.get("RQSET-zzz")
        self.assertEqual(cm.exception.status, 400)

    def test_too_many_questions_rejected(self):
        s = make_store()
        with self.assertRaises(QuestionStoreError):
            s.create("OPP-001", [q() for _ in range(41)])


class ReviewTests(unittest.TestCase):
    """PR10c — draft -> approved|rejected exactly once, optional reviewer edits."""

    def test_approve_transitions_once_and_records_reviewer(self):
        s = make_store()
        sid = s.create("OPP-001", [q()])["id"]
        out = s.review(sid, "approve", reviewer="USER-a", note="looks good")
        self.assertEqual(out["status"], "approved")
        self.assertEqual(out["reviewer"], "USER-a")
        self.assertEqual(out["review_note"], "looks good")
        self.assertIsNotNone(out["reviewed_at"])
        # immutable afterwards
        with self.assertRaises(QuestionStoreError) as cm:
            s.review(sid, "reject")
        self.assertEqual(cm.exception.status, 409)

    def test_reject_transitions(self):
        s = make_store()
        sid = s.create("OPP-001", [q()])["id"]
        self.assertEqual(s.review(sid, "reject")["status"], "rejected")

    def test_approve_with_edits_replaces_and_reids_questions(self):
        s = make_store()
        sid = s.create("OPP-001", [q()])["id"]
        edited = [q(text="Edited question one?"), q(text="Edited question two?")]
        out = s.review(sid, "approve", questions=edited)
        self.assertEqual([qq["text"] for qq in out["questions"]],
                         ["Edited question one?", "Edited question two?"])
        self.assertEqual([qq["question_id"] for qq in out["questions"]],
                         [f"{sid}-Q1", f"{sid}-Q2"])

    def test_edited_question_still_structurally_bounded(self):
        s = make_store()
        sid = s.create("OPP-001", [q()])["id"]
        with self.assertRaises(QuestionStoreError):
            s.review(sid, "approve", questions=[{"text": "   "}])  # empty text

    def test_review_owner_scoped_404(self):
        s = make_store()
        sid = s.create("OPP-001", [q()], owner_user_id="USER-a")["id"]
        with self.assertRaises(QuestionStoreError) as cm:
            s.review(sid, "approve", visible_to="USER-b")
        self.assertEqual(cm.exception.status, 404)

    def test_bad_action_rejected(self):
        s = make_store()
        sid = s.create("OPP-001", [q()])["id"]
        with self.assertRaises(QuestionStoreError):
            s.review(sid, "maybe")


class DeleteTests(unittest.TestCase):
    def test_delete_then_gone(self):
        s = make_store()
        sid = s.create("OPP-001", [q()])["id"]
        self.assertTrue(s.delete(sid)["deleted"])
        with self.assertRaises(QuestionStoreError) as cm:
            s.get(sid)
        self.assertEqual(cm.exception.status, 404)

    def test_delete_foreign_is_404(self):
        s = make_store()
        sid = s.create("OPP-001", [q()], owner_user_id="USER-a")["id"]
        with self.assertRaises(QuestionStoreError) as cm:
            s.delete(sid, visible_to="USER-b")
        self.assertEqual(cm.exception.status, 404)
        self.assertEqual(s.get(sid, visible_to="USER-a")["id"], sid)  # untouched


class MigrationTests(unittest.TestCase):
    def test_v1_db_migrates_to_v2_in_place(self):
        import sqlite3
        d = Path(tempfile.mkdtemp()) / "old.db"
        # simulate a v1 database (no review columns)
        conn = sqlite3.connect(d)
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO meta VALUES ('schema_version','1')")
        conn.execute("""CREATE TABLE question_sets (id TEXT PRIMARY KEY,
            opportunity_id TEXT NOT NULL, status TEXT NOT NULL, questions TEXT NOT NULL,
            provenance TEXT, rejected_count INTEGER NOT NULL DEFAULT 0, note TEXT,
            owner_user_id TEXT, created_at TEXT NOT NULL)""")
        conn.commit()
        conn.close()
        s = make_store(d)   # opening runs the v1->v2 migration
        sid = s.create("OPP-001", [q()])["id"]
        self.assertEqual(s.review(sid, "approve")["status"], "approved")


if __name__ == "__main__":
    unittest.main()
