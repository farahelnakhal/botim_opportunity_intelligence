"""Render tests — each screen produces valid, expected HTML from the live model."""

import sys
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
REPO = UI.parents[0]
sys.path.insert(0, str(UI))

from adapter import collect  # noqa: E402
from render import (assumptions, brief, evidence, feed, opportunity,  # noqa: E402
                    overview, proposal)


class TestRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = collect.build_model(str(REPO))

    def _common(self, html):
        self.assertIn("<!doctype html>", html)
        self.assertIn("No product or build decision has been made", html)  # banner
        self.assertIn("app.css", html)

    def test_overview_ranks_and_links(self):
        html = overview.render(self.m)
        self._common(html)
        self.assertLess(html.index("OPP-010"), html.index("OPP-013"))  # ranked
        self.assertIn("Archived / rejected", html)
        self.assertIn("opportunity-OPP-010.html", html)

    def test_opportunity_shows_all_17_factors(self):
        pages = opportunity.render_all(self.m)
        html = pages["opportunity-OPP-013.html"]
        self._common(html)
        for key in ("pain_severity", "willingness_to_pay", "mvp_feasibility_7wk"):
            self.assertIn(key, html)
        self.assertEqual(html.count('class="factor '), 17)  # every factor row present (not the table)
        self.assertIn("Composite", html)
        self.assertIn("the real picture", html)  # composite explicitly de-emphasised

    def test_opportunity_second_opp_also_renders(self):
        pages = opportunity.render_all(self.m)
        self.assertIn("opportunity-OPP-010.html", pages)
        self.assertEqual(pages["opportunity-OPP-010.html"].count('class="factor '), 17)

    def test_archived_opp_has_no_factor_table(self):
        pages = opportunity.render_all(self.m)
        html = pages["opportunity-OPP-003.html"]
        self.assertIn("archived", html.lower())
        self.assertEqual(html.count('class="factor '), 0)

    def test_evidence_separates_weak(self):
        html = evidence.render(self.m)
        self._common(html)
        self.assertIn("Weak evidence", html)
        self.assertIn("Score-driving evidence", html)
        self.assertIn("lead, not a finding", html)

    def test_assumptions_filters_present(self):
        html = assumptions.render(self.m)
        self._common(html)
        self.assertIn('id="f-opp"', html)
        self.assertIn('id="f-status"', html)
        self.assertIn("not yet structured fields", html)  # honesty note

    def test_feed_has_typed_items(self):
        html = feed.render(self.m)
        self._common(html)
        self.assertIn("No impact-approval or rollback workflow exists", html)

    def test_proposal_is_readonly_no_fake_button(self):
        html = proposal.render(self.m)
        self._common(html)
        self.assertIn("intentionally read-only", html)
        self.assertNotIn("<button", html.lower())  # no fake approval control
        self.assertNotIn("<form", html.lower())

    def test_brief_consumes_recommendation(self):
        html = brief.render(self.m)
        self._common(html)
        self.assertIn("OPP-001", html)              # the real recommendation
        self.assertIn("awaiting a brief", html)     # honest coverage of the rest


class TestEmptyStates(unittest.TestCase):
    """Empty inputs render honest empty states, never crashes or fabrication."""

    def setUp(self):
        from adapter import model as M
        self.empty = M.UIModel(generated_note="empty fixture")

    def test_all_screens_handle_empty(self):
        self.assertIn("No opportunities", overview.render(self.empty))
        self.assertIn("No evidence records", evidence.render(self.empty))
        self.assertIn("No monitoring events", feed.render(self.empty))
        self.assertIn("No executive brief", brief.render(self.empty))
        # proposal + assumptions still render a valid page
        self.assertIn("<!doctype html>", proposal.render(self.empty))
        self.assertIn("<!doctype html>", assumptions.render(self.empty))


if __name__ == "__main__":
    unittest.main()
