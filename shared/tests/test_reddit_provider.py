"""Phase R9a (PR9a-3) — the Reddit adapter and the real fail-closed
privacy/security gate. Fully offline: the network (token exchange + search) is
injected, so no live Reddit call is ever made and no real credentials exist."""

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.research.providers import (  # noqa: E402
    LIVE_SOCIAL_ENV, RedditProvider, SearchProviderError, build_provider,
    from_env)

TOKEN = {"access_token": "tok-abc", "token_type": "bearer", "expires_in": 3600}
_POST_1 = {"data": {
    "title": "Corporate card onboarding is painful",
    "selftext": "Took two weeks to get a card for my LLC in Dubai.",
    "permalink": "/r/dubai/comments/aaa/corporate_card/",
    "created_utc": 1748736000}}
_POST_2 = {"data": {
    "title": "Best SME bank account?",
    "selftext": "",   # empty selftext -> title used as snippet
    "permalink": "/r/UAE/comments/bbb/best_sme/",
    "created_utc": 1748822400}}
LISTING = {"data": {"children": [_POST_1, _POST_2]}}


def make_fetch(token=TOKEN, listing=LISTING, capture=None):
    def fetch(url, headers, data=None):
        if "access_token" in url:
            assert data is not None                    # token exchange is a POST
            assert headers.get("Authorization", "").startswith("Basic ")
            return json.dumps(token).encode("utf-8")
        if "/search" in url:
            assert data is None                        # search is a GET
            assert headers.get("Authorization") == "Bearer tok-abc"
            if capture is not None:
                capture.append(url)
            return json.dumps(listing).encode("utf-8")
        raise AssertionError(f"unexpected url: {url}")
    return fetch


class RedditAdapter(unittest.TestCase):
    def test_global_search_maps_posts_to_real_permalinks(self):
        p = RedditProvider("id", "secret", fetch_fn=make_fetch())
        out = p.search("sme corporate card")
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["provider"], "reddit")
        self.assertEqual(out[0]["title"], "Corporate card onboarding is painful")
        self.assertIn("Took two weeks", out[0]["snippet"])
        # a real dereferenceable permalink -> NOT synthesized
        self.assertEqual(out[0]["url"],
                         "https://www.reddit.com/r/dubai/comments/aaa/corporate_card/")
        self.assertFalse(out[0]["url_synthesized"])
        self.assertIsNone(out[0]["rating"])            # score is not a rating
        self.assertEqual(out[0]["published_at"], "2025-06-01T00:00:00Z")

    def test_empty_selftext_falls_back_to_title_as_snippet(self):
        out = RedditProvider("id", "secret", fetch_fn=make_fetch()).search("q")
        self.assertEqual(out[1]["snippet"], "Best SME bank account?")

    def test_subreddit_prefix_restricts_the_search(self):
        captured = []
        p = RedditProvider("id", "secret", fetch_fn=make_fetch(capture=captured))
        p.search("r/dubai corporate cards")
        self.assertEqual(len(captured), 1)
        self.assertIn("/r/dubai/search", captured[0])
        self.assertIn("restrict_sr=true", captured[0])

    def test_missing_credentials_raise(self):
        with self.assertRaises(SearchProviderError):
            RedditProvider("", "secret")
        with self.assertRaises(SearchProviderError):
            RedditProvider("id", "")

    def test_failed_auth_raises_without_leaking_secret(self):
        p = RedditProvider("id", "s3cr3t-value", fetch_fn=make_fetch(token={"error": "bad"}))
        with self.assertRaises(SearchProviderError) as cm:
            p.search("q")
        self.assertNotIn("s3cr3t-value", str(cm.exception))

    def test_malformed_listing_raises(self):
        def fetch(url, headers, data=None):
            if "access_token" in url:
                return json.dumps(TOKEN).encode("utf-8")
            return b"<<not json>>"
        with self.assertRaises(SearchProviderError):
            RedditProvider("id", "secret", fetch_fn=fetch).search("q")

    def test_post_without_permalink_is_skipped_never_invented(self):
        listing = {"data": {"children": [{"data": {"title": "no link"}}, _POST_1]}}
        out = RedditProvider("id", "secret",
                             fetch_fn=make_fetch(listing=listing)).search("q")
        self.assertEqual([r["url"] for r in out],
                         ["https://www.reddit.com/r/dubai/comments/aaa/corporate_card/"])

    def test_empty_query_raises(self):
        with self.assertRaises(SearchProviderError):
            RedditProvider("id", "secret", fetch_fn=make_fetch()).search("   ")

    def test_max_results_cap(self):
        out = RedditProvider("id", "secret",
                             fetch_fn=make_fetch()).search("q", max_results=1)
        self.assertEqual(len(out), 1)


class RegistryAndGate(unittest.TestCase):
    def test_build_provider_constructs_reddit(self):
        prov = build_provider("reddit",
                              env={"REDDIT_CLIENT_ID": "id",
                                   "REDDIT_CLIENT_SECRET": "s"},
                              fetch_fn=make_fetch())
        self.assertIsInstance(prov, RedditProvider)

    def test_from_env_refuses_reddit_when_gate_closed(self):
        with self.assertRaises(SearchProviderError) as cm:
            from_env(env={"RESEARCH_SEARCH_PROVIDER": "reddit",
                          "REDDIT_CLIENT_ID": "id", "REDDIT_CLIENT_SECRET": "s"})
        self.assertIn("privacy/security review", str(cm.exception))

    def test_from_env_serves_reddit_when_gate_opted_in(self):
        prov = from_env(env={"RESEARCH_SEARCH_PROVIDER": "reddit",
                             "REDDIT_CLIENT_ID": "id", "REDDIT_CLIENT_SECRET": "s",
                             LIVE_SOCIAL_ENV: "1"}, fetch_fn=make_fetch())
        self.assertEqual(prov.name, "reddit")


if __name__ == "__main__":
    unittest.main()
