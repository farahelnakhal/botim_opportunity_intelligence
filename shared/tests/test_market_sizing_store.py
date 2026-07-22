"""Phase C2 / PR2 — candidate market-sizing store (persistence, review-once,
ownership). Offline, pure."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from shared.market_sizing import MarketSizingStore, MarketSizingStoreError


def make_store():
    return MarketSizingStore(Path(tempfile.mkdtemp()) / "m.db")


def sizing_blob():
    return {"method": "top_down", "calculator": "market_sizing",
            "envelope": {"outputs": {"tam": {"value": 6.7e9}}}, "inputs_meta": {}}


class CreateReadTests(unittest.TestCase):
    def test_create_defaults_pending(self):
        s = make_store()
        row = s.create("OPP-001", calculator="market_sizing", confidence="verified",
                       sizing=sizing_blob(), run_id="RRUN-aaaaaaaaaaaa")
        self.assertRegex(row["id"], r"^MSZ-[0-9a-f]{12}$")
        self.assertEqual(row["status"], "pending_review")
        self.assertEqual(row["confidence"], "verified")
        self.assertEqual(row["sizing"]["calculator"], "market_sizing")

    def test_list_filter_by_opportunity(self):
        s = make_store()
        s.create("OPP-001", calculator="market_sizing", confidence="low_confidence", sizing=sizing_blob())
        s.create("OPP-002", calculator="market_sizing", confidence="verified", sizing=sizing_blob())
        self.assertEqual(len(s.list()), 2)
        self.assertEqual(len(s.list(opportunity_id="OPP-001")), 1)

    def test_bad_confidence_rejected(self):
        s = make_store()
        with self.assertRaises(MarketSizingStoreError):
            s.create("OPP-001", calculator="market_sizing", confidence="great", sizing=sizing_blob())


class ReviewTests(unittest.TestCase):
    def test_review_once_only(self):
        s = make_store()
        cid = s.create("OPP-001", calculator="market_sizing", confidence="verified", sizing=sizing_blob())["id"]
        approved = s.review(cid, "approve", reviewer="USER-a", note="looks solid")
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["reviewer"], "USER-a")
        with self.assertRaises(MarketSizingStoreError) as cm:
            s.review(cid, "reject")
        self.assertEqual(cm.exception.status, 409)     # already reviewed

    def test_reject(self):
        s = make_store()
        cid = s.create("OPP-001", calculator="market_sizing", confidence="low_confidence", sizing=sizing_blob())["id"]
        self.assertEqual(s.review(cid, "reject")["status"], "rejected")

    def test_bad_action(self):
        s = make_store()
        cid = s.create("OPP-001", calculator="market_sizing", confidence="verified", sizing=sizing_blob())["id"]
        with self.assertRaises(MarketSizingStoreError):
            s.review(cid, "maybe")


class OwnershipTests(unittest.TestCase):
    def test_foreign_row_404(self):
        s = make_store()
        cid = s.create("OPP-001", calculator="market_sizing", confidence="verified",
                       sizing=sizing_blob(), owner_user_id="USER-a")["id"]
        with self.assertRaises(MarketSizingStoreError) as cm:
            s.get(cid, visible_to="USER-b")
        self.assertEqual(cm.exception.status, 404)
        self.assertEqual(s.get(cid, visible_to="USER-a")["id"], cid)

    def test_legacy_null_owner_shared(self):
        s = make_store()
        cid = s.create("OPP-001", calculator="market_sizing", confidence="verified",
                       sizing=sizing_blob(), owner_user_id=None)["id"]
        self.assertEqual(s.get(cid, visible_to="USER-b")["id"], cid)

    def test_foreign_review_404(self):
        s = make_store()
        cid = s.create("OPP-001", calculator="market_sizing", confidence="verified",
                       sizing=sizing_blob(), owner_user_id="USER-a")["id"]
        with self.assertRaises(MarketSizingStoreError) as cm:
            s.review(cid, "approve", owner_user_id="USER-b")
        self.assertEqual(cm.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
