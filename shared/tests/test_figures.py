"""Phase C2 / PR1 — verified numeric-figure extraction. The model proposes;
deterministic verification (exact quote + verbatim value + tier) disposes.
Offline (stub provider)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.research import ResearchStore  # noqa: E402
from shared.research.figures import validate_figure, extract_figures  # noqa: E402
from shared.llm.provider import ConversationModel, ModelResponse  # noqa: E402

SRC = {"RSRC-aaaaaaaaaaa1": "The UAE has roughly 557,000 SMEs as of 2024, per the ministry.",
       "RSRC-aaaaaaaaaaa2": "The GCC card market reached 1.2 billion cards in 2023."}
TIERS = {"RSRC-aaaaaaaaaaa1": "T1", "RSRC-aaaaaaaaaaa2": "T2"}


class ValidateFigure(unittest.TestCase):
    def test_accepts_a_verbatim_value(self):
        ok, fig, reason = validate_figure(
            {"quantity": "number of UAE SMEs", "value": 557000, "unit": "SMEs",
             "source_id": "RSRC-aaaaaaaaaaa1",
             "supporting_quote": "roughly 557,000 SMEs"}, SRC, TIERS)
        self.assertTrue(ok, reason)
        self.assertEqual(fig["value"], 557000.0)
        self.assertEqual(fig["tier"], "T1")

    def test_rejects_a_value_absent_from_the_quote(self):
        ok, _, reason = validate_figure(
            {"quantity": "UAE SMEs", "value": 600000, "source_id": "RSRC-aaaaaaaaaaa1",
             "supporting_quote": "roughly 557,000 SMEs"}, SRC, TIERS)
        self.assertFalse(ok)
        self.assertEqual(reason, "value_not_in_source")

    def test_rejects_a_model_expanded_number(self):
        # "1.2 billion" must be reported as 1.2 + unit; expanding to 1200000000
        # is a computation the model may not do.
        ok, _, reason = validate_figure(
            {"quantity": "GCC cards", "value": 1200000000, "source_id": "RSRC-aaaaaaaaaaa2",
             "supporting_quote": "1.2 billion cards in 2023"}, SRC, TIERS)
        self.assertFalse(ok)
        self.assertEqual(reason, "value_not_in_source")

    def test_accepts_the_unexpanded_number_with_unit(self):
        ok, fig, reason = validate_figure(
            {"quantity": "GCC cards", "value": 1.2, "unit": "billion cards",
             "source_id": "RSRC-aaaaaaaaaaa2",
             "supporting_quote": "1.2 billion cards in 2023"}, SRC, TIERS)
        self.assertTrue(ok, reason)
        self.assertEqual(fig["value"], 1.2)
        self.assertEqual(fig["unit"], "billion cards")

    def test_rejects_an_invented_quote(self):
        ok, _, reason = validate_figure(
            {"quantity": "x", "value": 557000, "source_id": "RSRC-aaaaaaaaaaa1",
             "supporting_quote": "the source never said this 557,000"}, SRC, TIERS)
        self.assertFalse(ok)
        self.assertEqual(reason, "unsupported_quote")

    def test_rejects_unknown_source(self):
        ok, _, reason = validate_figure(
            {"quantity": "x", "value": 557000, "source_id": "RSRC-zzzzzzzzzzzz",
             "supporting_quote": "557,000"}, SRC, TIERS)
        self.assertFalse(ok)
        self.assertEqual(reason, "unknown_source_id")

    def test_rejects_a_non_numeric_value(self):
        for bad in ("lots", True, None):
            ok, _, reason = validate_figure(
                {"quantity": "x", "value": bad, "source_id": "RSRC-aaaaaaaaaaa1",
                 "supporting_quote": "557,000 SMEs"}, SRC, TIERS)
            self.assertFalse(ok)
            self.assertEqual(reason, "value_not_a_number")


class _Cfg:
    model = "stub-llm"
    timeout_s = 30


class StubFigures(ConversationModel):
    def __init__(self, figures=None, raw=None):
        self._payload = raw if raw is not None else json.dumps({"figures": figures or []})
        self.model = "stub-llm"

    def generate(self, messages, tools, system_prompt, configuration):
        return ModelResponse(content=self._payload)


def seed_store():
    store = ResearchStore(Path(tempfile.mkdtemp()) / "research.db")
    run = store.create_run({"title": "sizing seed"})
    store.start_run(run["id"])
    q = store.add_query(run["id"], {"query_text": "uae sme count"})
    s1 = store.add_source(run["id"], {"canonical_url": "https://imf.org/r", "query_id": q["id"],
                                      "title": "IMF SME note",
                                      "excerpt": "The UAE has roughly 557,000 SMEs as of 2024."})
    s2 = store.add_source(run["id"], {"canonical_url": "https://worldbank.org/r", "query_id": q["id"],
                                      "title": "World Bank data",
                                      "excerpt": "Small businesses in the UAE number about 560,000."})
    store.finish_run(run["id"], "complete")
    return store, run["id"], s1["id"], s2["id"]


class ExtractFigures(unittest.TestCase):
    def test_accepts_verified_figures_with_tiers(self):
        store, run_id, s1, s2 = seed_store()
        model = StubFigures([
            {"quantity": "UAE SMEs", "value": 557000, "unit": "SMEs",
             "source_id": s1, "supporting_quote": "roughly 557,000 SMEs"},
            {"quantity": "UAE small businesses", "value": 560000, "unit": "SMEs",
             "source_id": s2, "supporting_quote": "number about 560,000"},
        ])
        out = extract_figures(store, run_id, model, _Cfg())
        self.assertEqual(len(out["accepted"]), 2)
        self.assertEqual({f["tier"] for f in out["accepted"]}, {"T1"})   # both registry T1

    def test_rejects_an_invented_figure(self):
        store, run_id, s1, _ = seed_store()
        model = StubFigures([
            {"quantity": "UAE SMEs", "value": 999999, "source_id": s1,
             "supporting_quote": "roughly 557,000 SMEs"},   # value not in quote
        ])
        out = extract_figures(store, run_id, model, _Cfg())
        self.assertEqual(out["accepted"], [])
        self.assertEqual(out["rejected"][0]["reason"], "value_not_in_source")

    def test_malformed_model_output_yields_no_figures(self):
        store, run_id, _, _ = seed_store()
        out = extract_figures(store, run_id, StubFigures(raw="not json"), _Cfg())
        self.assertEqual(out["accepted"], [])


if __name__ == "__main__":
    unittest.main()
