"""Phase R9a (PR9a-1) — the shared source-tier registry and its storage on
research sources. Registry lookup is deterministic, domain-only, and unknown
domains fall to T4 (never silently authoritative). Offline."""

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.research import ResearchStore  # noqa: E402
from shared.research.source_tier import DEFAULT_TIER, TIERS, tier_for  # noqa: E402


class Registry(unittest.TestCase):
    def test_each_tier_resolves_from_a_full_url(self):
        self.assertEqual(tier_for("https://www.centralbank.ae/en/report"), "T1")
        self.assertEqual(tier_for("https://mckinsey.com/insights/x"), "T2")
        self.assertEqual(tier_for("https://www.reuters.com/markets/y"), "T3")
        self.assertEqual(tier_for("https://reddit.com/r/dubai/comments/z"), "T4")

    def test_parent_domain_resolution(self):
        # a subdomain resolves via its registrable parent
        self.assertEqual(tier_for("https://data.worldbank.org/indicator/abc"), "T1")
        self.assertEqual(tier_for("https://apps.apple.com/ae/app/id123"), "T4")

    def test_bare_domain_and_www_and_case(self):
        self.assertEqual(tier_for("WWW.IMF.ORG"), "T1")
        self.assertEqual(tier_for("statista.com"), "T2")

    def test_government_tld_suffix_is_t1(self):
        self.assertEqual(tier_for("https://example.gov/report"), "T1")
        self.assertEqual(tier_for("https://sca.gov.ae/en"), "T1")

    def test_unknown_domain_falls_to_t4_never_authoritative(self):
        self.assertEqual(tier_for("https://some-random-blog.example/post"), DEFAULT_TIER)
        self.assertEqual(DEFAULT_TIER, "T4")

    def test_empty_or_garbage_is_default(self):
        self.assertEqual(tier_for(""), DEFAULT_TIER)
        self.assertEqual(tier_for(None), DEFAULT_TIER)

    def test_tier_is_always_one_of_the_known_set(self):
        for url in ("https://x.com/a", "https://worldbank.org", "ft.com",
                    "https://nope.example"):
            self.assertIn(tier_for(url), TIERS)


class StoredOnSources(unittest.TestCase):
    def _store(self):
        return ResearchStore(Path(tempfile.mkdtemp()) / "research.db")

    def test_add_source_derives_and_stores_the_tier(self):
        s = self._store()
        run = s.create_run({"title": "tier test"})
        s.start_run(run["id"])
        t1 = s.add_source(run["id"], {"canonical_url": "https://data.worldbank.org/x"})
        t4 = s.add_source(run["id"], {"canonical_url": "https://reddit.com/r/y"})
        self.assertEqual(t1["source_tier"], "T1")
        self.assertEqual(t4["source_tier"], "T4")

    def test_tier_is_registry_derived_not_caller_supplied(self):
        # a caller cannot assert its own authority — a bogus payload tier is
        # ignored; the domain registry decides
        s = self._store()
        run = s.create_run({"title": "no spoof"})
        s.start_run(run["id"])
        src = s.add_source(run["id"], {"canonical_url": "https://reddit.com/r/z",
                                       "source_tier": "T1"})  # attempted override
        self.assertEqual(src["source_tier"], "T4")

    def test_tier_persists_across_reopen(self):
        tmp = Path(tempfile.mkdtemp()) / "research.db"
        s = ResearchStore(tmp)
        run = s.create_run({"title": "persist"})
        s.start_run(run["id"])
        sid = s.add_source(run["id"], {"canonical_url": "https://mckinsey.com/i"})["id"]
        reopened = ResearchStore(tmp)
        detail = reopened.get_run(run["id"], include_children=True)
        got = next(x for x in detail["sources"] if x["id"] == sid)
        self.assertEqual(got["source_tier"], "T2")


if __name__ == "__main__":
    unittest.main()
