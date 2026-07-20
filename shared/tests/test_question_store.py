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


if __name__ == "__main__":
    unittest.main()
