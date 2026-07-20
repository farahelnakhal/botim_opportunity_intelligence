"""Phase R6 (PR6c) — the diff-to-email materiality gate and digest renderer.
Pure and offline: no store, no network, no send. The critical behaviours are
the id-churn dedup (same claim text, new ids -> NOT material) and the honesty
of the rendered copy (labelled preliminary; overclaim guard fails safe)."""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.email import monitoring_digest as md  # noqa: E402

OPP = {"id": "UOPP-aaaaaaaaaaa1", "title": "Cross-border payroll tool"}


def V(version, composite, gaps=None, completed="2026-07-19T10:00:00Z"):
    return {"version": version, "status": "complete", "completed_at": completed,
            "preliminary_score": {"composite": composite}, "gaps": gaps or [],
            "claim_ids": []}


def claim(cid, text, status="pending_review"):
    return {"id": cid, "claim": text, "status": status}


class Materiality(unittest.TestCase):
    def test_a_genuinely_new_claim_is_material(self):
        ev = md.evaluate(V(1, 50), V(2, 50), [],
                         [claim("RCAND-1", "The market grew 12% in 2024")])
        self.assertTrue(ev["material"])
        self.assertEqual(ev["reason"], "new_claims")
        self.assertEqual(len(ev["new_claims"]), 1)

    def test_id_churn_with_identical_text_is_not_material(self):
        # a re-extraction mints a NEW id for the SAME fact — must NOT spam
        base = [claim("RCAND-a", "The market grew 12% in 2024")]
        new = [claim("RCAND-b", "  the MARKET grew 12% in 2024 ")]  # new id, same text
        ev = md.evaluate(V(1, 50), V(2, 50), base, new)
        self.assertFalse(ev["material"])
        self.assertEqual(ev["reason"], "no_change")

    def test_gap_only_change_is_not_material(self):
        ev = md.evaluate(V(1, 50, gaps=["no uploaded documents are attached"]),
                         V(2, 50, gaps=["no related internal evidence records matched"]),
                         [], [])
        self.assertFalse(ev["material"])

    def test_a_degraded_run_is_never_material_even_with_new_claims(self):
        ev = md.evaluate(V(1, 50), V(2, 50, gaps=["external research failed: timeout"]),
                         [], [claim("RCAND-1", "A brand new finding")])
        self.assertFalse(ev["material"])
        self.assertTrue(ev["degraded"])
        self.assertEqual(ev["reason"], "partial")

    def test_composite_move_at_or_above_threshold_is_material(self):
        ev = md.evaluate(V(1, 50.0), V(2, 50.5), [], [])
        self.assertTrue(ev["material"])
        self.assertEqual(ev["reason"], "composite_move")

    def test_composite_move_below_threshold_is_noise(self):
        ev = md.evaluate(V(1, 50.0), V(2, 50.004), [], [])   # rounds to 0.0 delta
        self.assertFalse(ev["material"])

    def test_rejected_claims_are_not_counted_as_new(self):
        ev = md.evaluate(V(1, 50), V(2, 50), [],
                         [claim("RCAND-1", "A rejected claim", status="rejected")])
        self.assertFalse(ev["material"])


class Rendering(unittest.TestCase):
    def _material_ev(self, **kw):
        return md.evaluate(V(1, 50), V(2, 50), [],
                           [claim("RCAND-1", "The market grew 12% in 2024", **kw)])

    def test_body_is_labelled_preliminary_and_carries_links(self):
        ev = self._material_ev()
        out = md.render(OPP, V(1, 50), V(2, 50), ev,
                        "https://app/report/UOPP-aaaaaaaaaaa1",
                        "https://app/api/monitoring/unsubscribe?token=t.sig")
        body = out["text_body"]
        self.assertTrue(out["subject"].startswith("[Monitoring]"))
        self.assertIn("PRELIMINARY", body)
        self.assertIn("notification, not an approval", body)
        self.assertIn("The market grew 12% in 2024", body)
        self.assertIn("[pending review — not confirmed]", body)
        self.assertIn("https://app/report/UOPP-aaaaaaaaaaa1", body)
        self.assertIn("Unsubscribe: https://app/api/monitoring/unsubscribe?token=t.sig", body)

    def test_approved_claims_are_labelled_as_such(self):
        ev = self._material_ev(status="approved")
        body = md.render(OPP, V(1, 50), V(2, 50), ev, "u", "x")["text_body"]
        self.assertIn("[approved by a reviewer — still preliminary evidence]", body)

    def test_score_line_omitted_when_the_number_did_not_move(self):
        ev = self._material_ev()   # material via new claim, composite delta 0
        body = md.render(OPP, V(1, 50), V(2, 50), ev, "u", "x")["text_body"]
        self.assertNotIn("Preliminary machine score", body)

    def test_score_line_present_when_the_number_moved(self):
        ev = md.evaluate(V(1, 50.0), V(2, 51.0), [], [])
        body = md.render(OPP, V(1, 50.0), V(2, 51.0), ev, "u", "x")["text_body"]
        self.assertIn("Preliminary machine score: 50.0 → 51.0", body)
        self.assertIn("not a validated score", body)

    def test_gaps_section_omitted_when_there_are_none(self):
        ev = self._material_ev()
        body = md.render(OPP, V(1, 50), V(2, 50), ev, "u", "x")["text_body"]
        self.assertNotIn("Open gaps", body)

    def test_overclaim_guard_fails_safe(self):
        # a claim text that smuggles an overclaim must ABORT the render, never
        # produce an email that reads as validated
        ev = md.evaluate(V(1, 50), V(2, 50), [],
                         [claim("RCAND-1", "This opportunity validated by the data")])
        with self.assertRaises(md.DigestError):
            md.render(OPP, V(1, 50), V(2, 50), ev, "u", "x")


if __name__ == "__main__":
    unittest.main()
