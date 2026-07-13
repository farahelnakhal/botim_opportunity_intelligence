"""The interface must NEVER imply a product has been validated or selected.

This test distinguishes an affirmative claim ("the product has been validated")
from a legitimate negation ("no product has been validated") — a blunt
substring grep would false-positive on the honest negations the UI relies on."""

import re
import sys
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
REPO = UI.parents[0]
sys.path.insert(0, str(UI))

from adapter import collect  # noqa: E402
from render import (assumptions, brief, evidence, feed, opportunity,  # noqa: E402
                    overview, proposal)

NEG = ("no", "not", "never", "none", "without", "un", "awaiting", "pending",
       "yet", "would", "unvalidated", "no product")
# affirmative-claim shapes we must never emit
AFFIRMATIVE = [
    r"has been validated",
    r"product (has been|is|was) selected",
    r"we have selected",
    r"validation (is )?complete",
    r"build (has been )?(approved|decided)",
    r"product is validated",
]


def _window_before(text, idx, n=60):
    return text[max(0, idx - n):idx].lower()


def _affirmative_hits(html):
    low = html.lower()
    hits = []
    for pat in AFFIRMATIVE:
        for m in re.finditer(pat, low):
            before = _window_before(low, m.start())
            # allowed if a negation token sits close before the claim
            if not any(neg in before for neg in NEG):
                hits.append((pat, html[max(0, m.start() - 50): m.start() + 30]))
    return hits


class TestNoValidatedClaims(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        m = collect.build_model(str(REPO))
        cls.pages = {
            "index": overview.render(m), "evidence": evidence.render(m),
            "assumptions": assumptions.render(m), "feed": feed.render(m),
            "proposals": proposal.render(m), "briefs": brief.render(m),
        }
        cls.pages.update(opportunity.render_all(m))

    def test_no_affirmative_validation_claims_anywhere(self):
        for name, html in self.pages.items():
            hits = _affirmative_hits(html)
            self.assertEqual(hits, [], f"{name} contains affirmative validation/selection claim(s): {hits}")

    def test_banner_on_every_page(self):
        for name, html in self.pages.items():
            self.assertIn("No product or build decision has been made", html, name)

    def test_negations_are_allowed(self):
        # sanity: the detector permits legitimate negations (avoids over-blocking)
        self.assertEqual(_affirmative_hits("No product has been validated or selected."), [])
        self.assertEqual(_affirmative_hits("Promising but unvalidated"), [])

    def test_detector_catches_a_real_violation(self):
        # sanity: the detector WOULD catch a genuine affirmative claim
        bad = "The OPP-013 product has been validated and selected for build."
        self.assertTrue(_affirmative_hits(bad))

    def test_promising_never_shown_as_strong_or_validated(self):
        # OPP-013 is 'promising' — its detail page must not label it validated/strong
        html = self.pages["opportunity-OPP-013.html"]
        self.assertIn("Promising", html)
        self.assertNotIn("Strong opportunity", html)


if __name__ == "__main__":
    unittest.main()
