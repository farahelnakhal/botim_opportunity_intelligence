"""Phase R9a (PR9a-2) — Apple App Store reviews adapter, the provider registry,
and the from_env gate for real-content social adapters. Fully offline: the
network is injected, so no live App Store call is ever made."""

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.research.providers import (  # noqa: E402
    AppStoreReviewsProvider, BraveSearchProvider, SearchProviderError,
    build_provider, from_env)

# a reviews feed: first entry is app metadata (no im:rating -> skipped),
# then two real reviews
_APP_META = {"im:name": {"label": "Settlement App"}, "id": {"label": "12345"}}
_REVIEW_1 = {
    "author": {"name": {"label": "trader_ae"}},
    "im:rating": {"label": "2"}, "id": {"label": "111"},
    "title": {"label": "Payouts are slow"},
    "content": {"label": "Settlement takes four days and it hurts cash flow."},
    "updated": {"label": "2026-06-01T10:00:00-07:00"}}
_REVIEW_2 = {
    "author": {"name": {"label": "shop_owner"}},
    "im:rating": {"label": "5"}, "id": {"label": "222"},
    "title": {"label": "Reliable"},
    "content": {"label": "Onboarding was quick."},
    "updated": {"label": "2026-06-02T09:00:00-07:00"}}

REVIEWS = {"feed": {"entry": [_APP_META, _REVIEW_1, _REVIEW_2]}}
SEARCH = {"results": [{"trackId": 12345, "trackName": "Settlement App"}]}


def make_fetch(reviews=REVIEWS, search=SEARCH):
    def fetch(url, headers):
        if "/search?" in url:
            return json.dumps(search).encode("utf-8")
        if "customerreviews" in url:
            return json.dumps(reviews).encode("utf-8")
        raise AssertionError(f"unexpected url: {url}")
    return fetch


class AppStoreAdapter(unittest.TestCase):
    def test_numeric_app_id_returns_reviews_skipping_metadata(self):
        p = AppStoreReviewsProvider(fetch_fn=make_fetch(), country="ae")
        out = p.search("12345")
        self.assertEqual(len(out), 2)                      # app-meta row skipped
        self.assertEqual(out[0]["provider"], "appstore")
        self.assertEqual(out[0]["title"], "Payouts are slow")
        self.assertIn("Settlement takes four days", out[0]["snippet"])
        self.assertEqual(out[0]["published_at"], "2026-06-01T10:00:00-07:00")
        # synthesized, unique, honest per-review app-store URL
        self.assertIn("apps.apple.com/ae/app/id12345?reviewId=111", out[0]["url"])
        self.assertNotEqual(out[0]["url"], out[1]["url"])

    def test_app_name_is_resolved_then_reviews_fetched(self):
        p = AppStoreReviewsProvider(fetch_fn=make_fetch())
        out = p.search("Settlement App")                   # non-numeric -> resolve
        self.assertEqual(len(out), 2)
        self.assertEqual(out[1]["title"], "Reliable")

    def test_single_review_feed_object_is_normalized(self):
        p = AppStoreReviewsProvider(fetch_fn=make_fetch(
            reviews={"feed": {"entry": _REVIEW_1}}))
        out = p.search("12345")
        self.assertEqual(len(out), 1)

    def test_empty_feed_returns_empty(self):
        p = AppStoreReviewsProvider(fetch_fn=make_fetch(reviews={"feed": {"entry": []}}))
        self.assertEqual(p.search("12345"), [])

    def test_max_results_cap(self):
        many = {"feed": {"entry": [_REVIEW_1, _REVIEW_2, _REVIEW_1]}}
        p = AppStoreReviewsProvider(fetch_fn=make_fetch(reviews=many))
        self.assertEqual(len(p.search("12345", max_results=1)), 1)

    def test_malformed_json_raises(self):
        p = AppStoreReviewsProvider(fetch_fn=lambda url, h: b"<<not json>>")
        with self.assertRaises(SearchProviderError):
            p.search("12345")

    def test_no_matching_app_raises(self):
        p = AppStoreReviewsProvider(fetch_fn=make_fetch(search={"results": []}))
        with self.assertRaises(SearchProviderError):
            p.search("Nonexistent App")

    def test_empty_query_raises(self):
        with self.assertRaises(SearchProviderError):
            AppStoreReviewsProvider(fetch_fn=make_fetch()).search("  ")


class RegistryAndGate(unittest.TestCase):
    def test_build_provider_constructs_registered_adapters(self):
        self.assertIsInstance(build_provider("appstore", env={}, fetch_fn=make_fetch()),
                              AppStoreReviewsProvider)
        self.assertIsInstance(
            build_provider("brave", env={"BRAVE_SEARCH_API_KEY": "k"}),
            BraveSearchProvider)

    def test_build_provider_unknown_raises(self):
        with self.assertRaises(SearchProviderError):
            build_provider("tiktok", env={})

    def test_from_env_refuses_gated_appstore_until_privacy_review(self):
        with self.assertRaises(SearchProviderError) as cm:
            from_env(env={"RESEARCH_SEARCH_PROVIDER": "appstore"})
        self.assertIn("pending", str(cm.exception).lower())

    def test_from_env_still_serves_brave_and_none(self):
        self.assertIsNone(from_env(env={}))
        prov = from_env(env={"RESEARCH_SEARCH_PROVIDER": "brave",
                             "BRAVE_SEARCH_API_KEY": "k"})
        self.assertEqual(prov.name, "brave")

    def test_from_env_unknown_provider_raises(self):
        with self.assertRaises(SearchProviderError):
            from_env(env={"RESEARCH_SEARCH_PROVIDER": "facebook"})


if __name__ == "__main__":
    unittest.main()
