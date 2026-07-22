"""Phase H2 (PR-H2c) — per-adapter ToS/rate-limit conformance for R9a's social
adapters, under rapid-fire (not just happy-path). Proves:

- the inter-call politeness delay the hardening pass FOUND MISSING now fires
  BETWEEN a single search()'s internal HTTP calls (App Store resolve→reviews,
  Reddit token→search) and before the single retry — with an injected clock, so
  no test actually sleeps;
- retries stay bounded (one retry, no storm);
- result caps hold, including the MAX_RESULTS_CAP ceiling when a caller asks for
  more;
- the production builders (from_env / build_provider) wire the real delay on,
  while bare construction stays delay-free (the composition-root design that
  keeps existing injected-clock tests fast).

Offline: network injected via fetch_fn; clock injected via sleep_fn."""

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.research import providers  # noqa: E402
from shared.research.providers import (AppStoreReviewsProvider,  # noqa: E402
                                        RedditProvider, build_provider)

DELAY = providers.DEFAULT_REQUEST_DELAY_S


def appstore_fetch(n_reviews=2):
    reviews = [{"im:rating": {"label": "4"}, "id": {"label": str(i)},
                "title": {"label": f"t{i}"}, "content": {"label": f"body {i}"},
                "updated": {"label": "2026-06-01T10:00:00-07:00"}} for i in range(n_reviews)]
    feed = {"feed": {"entry": [{"im:name": {"label": "A"}, "id": {"label": "12345"}}, *reviews]}}
    search = {"results": [{"trackId": 12345, "trackName": "A"}]}

    def fetch(url, headers):
        if "/search?" in url:
            return json.dumps(search).encode("utf-8")
        if "customerreviews" in url:
            return json.dumps(feed).encode("utf-8")
        raise AssertionError(url)
    return fetch


def reddit_fetch(n_posts=2):
    posts = [{"data": {"title": f"t{i}", "selftext": f"body {i}",
                       "permalink": f"/r/x/comments/{i}/y/", "created_utc": 1748736000}}
             for i in range(n_posts)]
    listing = {"data": {"children": posts}}

    def fetch(url, headers, data=None):
        if "access_token" in url:
            return json.dumps({"access_token": "tok", "token_type": "bearer"}).encode("utf-8")
        if "/search" in url:
            return json.dumps(listing).encode("utf-8")
        raise AssertionError(url)
    return fetch


class InterCallThrottle(unittest.TestCase):
    def test_appstore_delays_between_resolve_and_reviews_only_when_resolving(self):
        sleeps = []
        p = AppStoreReviewsProvider(fetch_fn=appstore_fetch(), country="ae",
                                    request_delay_s=DELAY, sleep_fn=sleeps.append)
        p.search("Some App Name")                 # non-numeric → resolve + reviews = 2 calls
        self.assertEqual(sleeps, [DELAY])          # exactly one polite gap
        sleeps.clear()
        p.search("12345")                          # numeric → reviews only = 1 call
        self.assertEqual(sleeps, [])               # no needless initial delay

    def test_reddit_delays_between_token_and_search(self):
        sleeps = []
        p = RedditProvider("id", "secret", fetch_fn=reddit_fetch(),
                           request_delay_s=DELAY, sleep_fn=sleeps.append)
        p.search("dubai sme")
        self.assertEqual(sleeps, [DELAY])          # token → gap → search


class BoundedRetry(unittest.TestCase):
    def test_one_retry_with_backoff_no_storm(self):
        calls, sleeps = [], []

        def flaky(url, headers):
            calls.append(url)
            if len(calls) == 1:
                raise TimeoutError("first attempt times out")
            return json.dumps({"feed": {"entry": [
                {"im:rating": {"label": "4"}, "id": {"label": "1"},
                 "title": {"label": "t"}, "content": {"label": "b"},
                 "updated": {"label": "2026-06-01T10:00:00-07:00"}}]}}).encode("utf-8")
        p = AppStoreReviewsProvider(fetch_fn=flaky, country="ae",
                                    request_delay_s=DELAY, sleep_fn=sleeps.append)
        out = p.search("12345")                    # numeric → single logical call, retried once
        self.assertEqual(len(calls), 2)            # exactly one retry — no storm
        self.assertEqual(sleeps, [DELAY])          # bounded backoff before the retry
        self.assertEqual(len(out), 1)


class ResultCaps(unittest.TestCase):
    def test_appstore_respects_requested_and_ceiling_caps(self):
        p = AppStoreReviewsProvider(fetch_fn=appstore_fetch(n_reviews=25), country="ae")
        self.assertEqual(len(p.search("12345", max_results=8)), 8)      # requested cap
        self.assertEqual(len(p.search("12345", max_results=999)),
                         providers.MAX_RESULTS_CAP)                     # hard ceiling

    def test_reddit_respects_requested_and_ceiling_caps(self):
        p = RedditProvider("id", "secret", fetch_fn=reddit_fetch(n_posts=25))
        self.assertEqual(len(p.search("q", max_results=5)), 5)
        self.assertEqual(len(p.search("q", max_results=999)), providers.MAX_RESULTS_CAP)


class BuildersWireTheDelay(unittest.TestCase):
    def test_appstore_builder_sets_polite_delay(self):
        p = build_provider("appstore", env={}, fetch_fn=appstore_fetch())
        self.assertEqual(p._delay, DELAY)

    def test_reddit_builder_sets_polite_delay(self):
        p = build_provider("reddit",
                           env={"REDDIT_CLIENT_ID": "id", "REDDIT_CLIENT_SECRET": "s"},
                           fetch_fn=reddit_fetch())
        self.assertEqual(p._delay, DELAY)

    def test_bare_construction_is_delay_free(self):
        # keeps the existing injected-clock adapter tests fast — the delay is a
        # composition-root concern wired by the builders, not bare construction
        sleeps = []
        AppStoreReviewsProvider(fetch_fn=appstore_fetch(), country="ae",
                                sleep_fn=sleeps.append).search("Some App Name")
        self.assertEqual(sleeps, [])


if __name__ == "__main__":
    unittest.main()
