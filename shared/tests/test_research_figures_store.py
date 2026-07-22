"""Phase C2 / PR2 — verified-figure persistence on the research store
(add_figure / list_figures). A figure is already exact-substring +
verbatim-value verified (shared/research/figures.py) before it lands here; the
store only persists it, enforces that the cited source belongs to the run, and
keeps the tier as given. Offline, pure."""

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.research import ResearchStore, ResearchStoreError  # noqa: E402


def make_store(path=None):
    return ResearchStore(path or Path(tempfile.mkdtemp()) / "research.db")


def seeded_run(store, **overrides):
    payload = {"title": "UAE SME card market sizing",
               "objective": "Size the UAE/GCC SME corporate-card opportunity",
               "profile": "sme-financial-product", **overrides}
    return store.create_run(payload)


def a_source(store, run_id, url="https://www.centralbank.ae/report"):
    return store.add_source(run_id, {"canonical_url": url, "title": "A report"})


def a_figure(source_id, **overrides):
    payload = {"quantity": "sme_count", "value": 557000, "unit": "businesses",
               "tier": "T1", "supporting_quote": "There are 557,000 SMEs in the UAE.",
               "source_id": source_id}
    payload.update(overrides)
    return payload


class AddFigureTests(unittest.TestCase):
    def setUp(self):
        self.store = make_store()
        self.run = seeded_run(self.store)
        self.src = a_source(self.store, self.run["id"])

    def test_add_and_read_back(self):
        fig = self.store.add_figure(self.run["id"], a_figure(self.src["id"]))
        self.assertRegex(fig["id"], r"^RFIG-[0-9a-f]{12}$")
        self.assertEqual(fig["run_id"], self.run["id"])
        self.assertEqual(fig["source_id"], self.src["id"])
        self.assertEqual(fig["quantity"], "sme_count")
        self.assertEqual(fig["value"], 557000.0)
        self.assertEqual(fig["unit"], "businesses")
        self.assertEqual(fig["tier"], "T1")

    def test_value_must_be_a_number(self):
        with self.assertRaises(ResearchStoreError):
            self.store.add_figure(self.run["id"], a_figure(self.src["id"], value="lots"))
        with self.assertRaises(ResearchStoreError):
            self.store.add_figure(self.run["id"], a_figure(self.src["id"], value=True))

    def test_quantity_required(self):
        payload = a_figure(self.src["id"])
        del payload["quantity"]
        with self.assertRaises(ResearchStoreError):
            self.store.add_figure(self.run["id"], payload)

    def test_source_must_belong_to_the_run(self):
        other = seeded_run(self.store, title="other run")
        foreign = a_source(self.store, other["id"], url="https://example.org/other")
        with self.assertRaises(ResearchStoreError) as cm:
            self.store.add_figure(self.run["id"], a_figure(foreign["id"]))
        self.assertIn("same run", str(cm.exception))

    def test_unknown_source_rejected(self):
        with self.assertRaises(ResearchStoreError):
            self.store.add_figure(self.run["id"], a_figure("RSRC-000000000000"))

    def test_bad_source_id_shape_rejected(self):
        with self.assertRaises(ResearchStoreError):
            self.store.add_figure(self.run["id"], a_figure("not-an-id"))


class ListFigureTests(unittest.TestCase):
    def setUp(self):
        self.store = make_store()
        self.run = seeded_run(self.store)
        self.s1 = a_source(self.store, self.run["id"], url="https://www.centralbank.ae/a")
        self.s2 = a_source(self.store, self.run["id"], url="https://www.imf.org/b")

    def test_filter_by_quantity(self):
        self.store.add_figure(self.run["id"], a_figure(self.s1["id"], quantity="sme_count", value=557000))
        self.store.add_figure(self.run["id"], a_figure(self.s2["id"], quantity="sme_count", value=560000))
        self.store.add_figure(self.run["id"], a_figure(self.s1["id"], quantity="avg_spend", value=12000))
        self.assertEqual(len(self.store.list_figures(self.run["id"])), 3)
        self.assertEqual(len(self.store.list_figures(self.run["id"], quantity="sme_count")), 2)
        self.assertEqual(len(self.store.list_figures(self.run["id"], quantity="avg_spend")), 1)
        self.assertEqual(self.store.list_figures(self.run["id"], quantity="nope"), [])

    def test_bad_run_id_rejected(self):
        with self.assertRaises(ResearchStoreError):
            self.store.list_figures("not-a-run")

    def test_survives_restart(self):
        db = Path(tempfile.mkdtemp()) / "research.db"
        store = make_store(db)
        run = seeded_run(store)
        src = a_source(store, run["id"])
        store.add_figure(run["id"], a_figure(src["id"]))
        reopened = ResearchStore(db)
        figs = reopened.list_figures(run["id"])
        self.assertEqual(len(figs), 1)
        self.assertEqual(figs[0]["value"], 557000.0)


if __name__ == "__main__":
    unittest.main()
