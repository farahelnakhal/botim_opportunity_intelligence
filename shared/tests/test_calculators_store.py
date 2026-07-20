"""Phase C1 — CALC- store tests (persistence, ownership, re-derivability)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from shared.calculators import compute, CalculatorStore, CalculatorError
from shared.calculators.calculators import REGISTRY


def make_store(path=None):
    return CalculatorStore(path or Path(tempfile.mkdtemp()) / "calculators.db")


def sample_envelope():
    return compute("market_sizing", {"population": 500000, "annual_value_per_unit": 12000,
                                     "serviceable_fraction": 0.4, "obtainable_share": 0.1})


class SaveReadTests(unittest.TestCase):
    def test_save_and_get(self):
        s = make_store()
        saved = s.save(sample_envelope(), opportunity_ref="UOPP-0123456789ab", label="UAE sizing")
        self.assertRegex(saved["id"], r"^CALC-[0-9a-f]{12}$")
        self.assertEqual(saved["calculator"], "market_sizing")
        self.assertEqual(saved["calculator_version"], 1)
        self.assertEqual(saved["label"], "UAE sizing")
        got = s.get(saved["id"])
        self.assertEqual(got["envelope"]["outputs"]["tam"]["value"], 6_000_000_000)

    def test_persists_across_reopen(self):
        d = Path(tempfile.mkdtemp()) / "c.db"
        s1 = make_store(d)
        cid = s1.save(sample_envelope())["id"]
        s2 = make_store(d)
        self.assertEqual(s2.get(cid)["id"], cid)

    def test_stored_result_is_rederivable(self):
        # the saved envelope carries calculator_version + inputs, so re-running
        # the same calculator on the same inputs reproduces the stored outputs.
        s = make_store()
        saved = s.save(sample_envelope())
        env = saved["envelope"]
        inputs = {k: {"value": n["value"], "label": n["label"]}
                  for k, n in env["normalized_inputs"].items()}
        rederived = REGISTRY[env["calculator_id"]].compute(inputs)
        self.assertEqual(rederived["outputs"]["som"]["value"],
                         env["outputs"]["som"]["value"])

    def test_list_and_filter_by_opportunity(self):
        s = make_store()
        s.save(sample_envelope(), opportunity_ref="UOPP-aaaaaaaaaaaa")
        s.save(sample_envelope(), opportunity_ref="UOPP-bbbbbbbbbbbb")
        self.assertEqual(len(s.list()), 2)
        self.assertEqual(len(s.list(opportunity_ref="UOPP-aaaaaaaaaaaa")), 1)

    def test_delete(self):
        s = make_store()
        cid = s.save(sample_envelope())["id"]
        s.delete(cid)
        with self.assertRaises(CalculatorError) as cm:
            s.get(cid)
        self.assertEqual(cm.exception.status, 404)


class OwnershipTests(unittest.TestCase):
    def test_foreign_row_is_indistinguishable_404(self):
        s = make_store()
        cid = s.save(sample_envelope(), owner_user_id="USER-a")["id"]
        with self.assertRaises(CalculatorError) as cm:
            s.get(cid, visible_to="USER-b")
        self.assertEqual(cm.exception.status, 404)
        # owner still sees it
        self.assertEqual(s.get(cid, visible_to="USER-a")["id"], cid)

    def test_legacy_null_owner_shared(self):
        s = make_store()
        cid = s.save(sample_envelope(), owner_user_id=None)["id"]
        self.assertEqual(s.get(cid, visible_to="USER-b")["id"], cid)

    def test_list_scopes_to_owner_plus_shared(self):
        s = make_store()
        s.save(sample_envelope(), owner_user_id="USER-a")
        s.save(sample_envelope(), owner_user_id="USER-b")
        s.save(sample_envelope(), owner_user_id=None)
        self.assertEqual(len(s.list(visible_to="USER-a")), 2)   # own + shared
        self.assertEqual(len(s.list(visible_to=None)), 3)       # auth off sees all

    def test_delete_foreign_row_404(self):
        s = make_store()
        cid = s.save(sample_envelope(), owner_user_id="USER-a")["id"]
        with self.assertRaises(CalculatorError) as cm:
            s.delete(cid, owner_user_id="USER-b")
        self.assertEqual(cm.exception.status, 404)


class ValidationTests(unittest.TestCase):
    def test_bad_opportunity_ref_rejected(self):
        s = make_store()
        with self.assertRaises(CalculatorError):
            s.save(sample_envelope(), opportunity_ref="not-an-id")

    def test_bad_calc_id_404(self):
        s = make_store()
        with self.assertRaises(CalculatorError) as cm:
            s.get("CALC-zzz")
        self.assertEqual(cm.exception.status, 400)

    def test_envelope_must_carry_version(self):
        s = make_store()
        with self.assertRaises(CalculatorError):
            s.save({"calculator_id": "market_sizing"})


if __name__ == "__main__":
    unittest.main()
