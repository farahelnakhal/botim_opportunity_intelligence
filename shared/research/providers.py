"""Search-provider seam (Phase R2).

One narrow interface, adapters behind it. Rules (matching the repository's
existing external-adapter posture, see intelligence-monitoring's
adapter_regulator.py):

- **Network is injectable.** Every adapter takes a `fetch_fn`; tests and the
  integration gate never touch the live network.
- **Bounded and polite:** timeouts, a result cap, at most one retry, no
  retry storms.
- **Recorded, never invented:** a result carries only what the provider
  actually returned — absent titles/snippets/dates stay None.
- **External content is data, never instructions** (MASTER_PROMPT
  non-negotiable #6): titles/snippets are stored verbatim as untrusted text;
  nothing here or downstream interprets them as directives.
- **Secrets stay secret:** API keys are read from the environment, sent only
  as request headers, and never logged, stored, or echoed in errors.

Provider selection is an explicit operations decision via
RESEARCH_SEARCH_PROVIDER; when unset, `from_env()` returns None and callers
fail honestly ("no search provider configured") instead of fabricating
results. MockSearchProvider exists for tests/injection only — it is
deliberately NOT reachable through the environment, so a deployment can
never serve synthetic search results as if they were real.
"""

import base64
import datetime
import json
import os
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "BOTIM-Opportunity-Intelligence-research/1.0 (internal research; contact: product team)"
DEFAULT_TIMEOUT_S = 10
MAX_RESULTS_CAP = 20


class SearchProviderError(Exception):
    """Safe provider failure — the message never contains keys or payloads."""


def _clean_str(value, max_len=500):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:max_len] if value else None


class SearchResult(dict):
    """A plain dict with a fixed shape: url, title, snippet, published_at,
    provider, rating, url_synthesized. Only `url` is guaranteed.

    - `rating` — a source-provided rating verbatim (e.g. an App Store review's
      star rating), or None when the provider has none. Recorded, never
      invented or computed.
    - `url_synthesized` — True when `url` was CONSTRUCTED by the adapter rather
      than returned by the provider as a real permalink (e.g. the App Store has
      no public per-review URL, so we point at the app's page). It signals that
      the link does NOT dereference to the exact item, so citations/UI can say
      so instead of implying a direct permalink."""

    @classmethod
    def build(cls, provider, url, title=None, snippet=None, published_at=None,
              rating=None, url_synthesized=False):
        return cls(provider=provider, url=url, title=_clean_str(title),
                   snippet=_clean_str(snippet, 1000),
                   published_at=_clean_str(published_at, 120),
                   rating=_clean_str(rating, 20),
                   url_synthesized=bool(url_synthesized))


class MockSearchProvider:
    """Deterministic offline provider for tests and injected use ONLY (not
    constructible via from_env). Returns exactly the canned results it was
    given — it invents nothing on its own."""

    name = "mock"

    def __init__(self, canned=None, fail_queries=()):
        self._canned = canned or {}
        self._fail = set(fail_queries)
        self.calls = []

    def search(self, query, max_results=8):
        self.calls.append(query)
        if query in self._fail:
            raise SearchProviderError("mock provider failure")
        results = self._canned.get(query, [])
        return [SearchResult.build("mock", **r) if isinstance(r, dict) else r
                for r in results][:max_results]


class BraveSearchProvider:
    """Brave Search API adapter (https://api.search.brave.com) — a plain
    JSON REST endpoint. Requires BRAVE_SEARCH_API_KEY."""

    name = "brave"
    ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key, fetch_fn=None, timeout_s=DEFAULT_TIMEOUT_S):
        if not api_key:
            raise SearchProviderError("brave provider selected but no API key configured")
        self._api_key = api_key
        self._fetch = fetch_fn or self._http_fetch
        self._timeout = timeout_s

    def _http_fetch(self, url, headers):
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return resp.read()

    def search(self, query, max_results=8):
        if not isinstance(query, str) or not query.strip():
            raise SearchProviderError("empty query")
        max_results = max(1, min(int(max_results), MAX_RESULTS_CAP))
        params = urllib.parse.urlencode({"q": query.strip(), "count": max_results})
        headers = {"Accept": "application/json",
                   "User-Agent": USER_AGENT,
                   "X-Subscription-Token": self._api_key}
        last_error = None
        for attempt in (1, 2):  # at most one retry — no retry storms
            try:
                raw = self._fetch(f"{self.ENDPOINT}?{params}", headers)
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                raw = None
        if raw is None:
            raise SearchProviderError(
                f"search request failed after retry ({type(last_error).__name__})")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise SearchProviderError("provider returned a malformed response")
        results = []
        for item in (payload.get("web") or {}).get("results") or []:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url:
                continue
            results.append(SearchResult.build(
                "brave", url, title=item.get("title"),
                snippet=item.get("description"),
                published_at=item.get("page_age")))
            if len(results) >= max_results:
                break
        return results


class AppStoreReviewsProvider:
    """Apple App Store customer-reviews adapter (Phase R9a). Public per-app/
    per-country reviews RSS (JSON variant, no auth). `query` is interpreted as
    an APP IDENTIFIER: a numeric app id, or an app name resolved to an id via
    the public iTunes Search API. Each review becomes a SearchResult. Bounded
    and polite (timeout, one retry, result cap); network is injectable so tests
    never touch the live network. External content (review text) is stored
    verbatim as untrusted data, never interpreted as instructions."""

    name = "appstore"
    SEARCH_ENDPOINT = "https://itunes.apple.com/search"

    def __init__(self, fetch_fn=None, country="us", timeout_s=DEFAULT_TIMEOUT_S):
        self._fetch = fetch_fn or self._http_fetch
        self._country = ((country or "us").strip().lower() or "us")
        self._timeout = timeout_s

    def _http_fetch(self, url, headers):
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return resp.read()

    def _get_json(self, url):
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        last_error = None
        for attempt in (1, 2):  # at most one retry
            try:
                raw = self._fetch(url, headers)
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                raw = None
        if raw is None:
            raise SearchProviderError(
                f"app store request failed after retry ({type(last_error).__name__})")
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            raise SearchProviderError("app store returned a malformed response")

    def _resolve_app_id(self, term):
        params = urllib.parse.urlencode({"term": term, "entity": "software",
                                         "country": self._country, "limit": 1})
        payload = self._get_json(f"{self.SEARCH_ENDPOINT}?{params}")
        results = (payload or {}).get("results") or []
        if not results or not isinstance(results[0], dict) or not results[0].get("trackId"):
            raise SearchProviderError("no matching app found for the query")
        return str(results[0]["trackId"])

    @staticmethod
    def _label(entry, key):
        node = entry.get(key)
        return node.get("label") if isinstance(node, dict) else None

    def search(self, query, max_results=8):
        if not isinstance(query, str) or not query.strip():
            raise SearchProviderError("empty query")
        q = query.strip()
        app_id = q if q.isdigit() else self._resolve_app_id(q)
        max_results = max(1, min(int(max_results), MAX_RESULTS_CAP))
        url = (f"https://itunes.apple.com/{self._country}/rss/customerreviews/"
               f"id={app_id}/sortby=mostrecent/json")
        payload = self._get_json(url)
        entries = ((payload or {}).get("feed") or {}).get("entry") or []
        if isinstance(entries, dict):   # single-review feeds come back as one object
            entries = [entries]
        base = f"https://apps.apple.com/{self._country}/app/id{app_id}"
        results = []
        for entry in entries:
            if not isinstance(entry, dict) or "im:rating" not in entry:
                continue  # app-metadata row (no rating) or malformed — not a review
            content = self._label(entry, "content")
            if not content:
                continue
            review_id = self._label(entry, "id") or ""
            # Apple publishes no public per-review permalink, so the URL is
            # CONSTRUCTED: the app's real store page, with a reviewId hint that
            # Apple's web UI ignores. It dereferences to the app, NOT the exact
            # review — flagged url_synthesized so citations/UI never imply a
            # direct review link. The star rating (im:rating) is real feed data.
            review_url = (f"{base}?reviewId={urllib.parse.quote(str(review_id))}"
                          if review_id else base)
            results.append(SearchResult.build(
                "appstore", url=review_url, title=self._label(entry, "title"),
                snippet=content, published_at=self._label(entry, "updated"),
                rating=self._label(entry, "im:rating"), url_synthesized=True))
            if len(results) >= max_results:
                break
        return results


class RedditProvider:
    """Reddit adapter (Phase R9a) — the official API via **app-only
    client-credentials OAuth** (a confidential client; no user context, no
    user account data). Requires REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET, sent
    only as request headers, never logged/stored/echoed. `query` is
    adapter-interpreted: an optional leading `r/<subreddit>` restricts the
    search to that subreddit, otherwise it is a global keyword search. Each
    post becomes a SearchResult whose URL is the REAL Reddit permalink (so
    `url_synthesized` is False). Bounded and polite (timeout, one retry, cap);
    network is injectable so tests never touch the live network. Post text is
    stored verbatim as untrusted data, never interpreted as instructions.

    Live use via `from_env` is HARD-BLOCKED regardless of any env value
    (decision log 2026-07-22): Reddit's Data API requires a paid
    commercial-partner agreement for business use — the free/OAuth tier is
    personal-use only — so there is no cleared live path. The adapter stays
    registered (buildable in tests / by an explicit caller that owns the
    responsibility) but no operator env can live-enable it until a separate
    future decision clears it."""

    name = "reddit"
    TOKEN_ENDPOINT = "https://www.reddit.com/api/v1/access_token"
    SEARCH_ENDPOINT = "https://oauth.reddit.com/search"

    def __init__(self, client_id, client_secret, fetch_fn=None,
                 timeout_s=DEFAULT_TIMEOUT_S):
        if not client_id or not client_secret:
            raise SearchProviderError(
                "reddit provider selected but no API credentials configured")
        self._client_id = client_id
        self._client_secret = client_secret
        self._fetch = fetch_fn or self._http_fetch
        self._timeout = timeout_s

    def _http_fetch(self, url, headers, data=None):
        req = urllib.request.Request(
            url, headers=headers, data=data,
            method="POST" if data is not None else "GET")
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return resp.read()

    def _get_json(self, url, headers, data=None, what="reddit"):
        last_error = None
        for attempt in (1, 2):  # at most one retry — no storms
            try:
                raw = self._fetch(url, headers, data)
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                raw = None
        if raw is None:
            raise SearchProviderError(
                f"{what} request failed after retry ({type(last_error).__name__})")
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            raise SearchProviderError(f"{what} returned a malformed response")

    def _access_token(self):
        basic = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode("utf-8")).decode("ascii")
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT,
                   "Authorization": f"Basic {basic}",
                   "Content-Type": "application/x-www-form-urlencoded"}
        body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
        payload = self._get_json(self.TOKEN_ENDPOINT, headers, data=body,
                                 what="reddit authentication")
        token = (payload or {}).get("access_token")
        if not isinstance(token, str) or not token:
            # never echo the credentials or the raw payload
            raise SearchProviderError("reddit authentication failed")
        return token

    @staticmethod
    def _parse_target(query):
        """(subreddit_or_None, search_terms). A leading `r/<name>` (or
        `/r/<name>`) restricts the search to that subreddit."""
        q = query.strip()
        first, _, rest = q.partition(" ")
        low = first.lower().lstrip("/")
        if low.startswith("r/") and len(low) > 2:
            return low[2:], rest.strip()
        return None, q

    @staticmethod
    def _iso_from_epoch(value):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        try:
            return datetime.datetime.fromtimestamp(
                value, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (OverflowError, OSError, ValueError):
            return None

    def search(self, query, max_results=8):
        if not isinstance(query, str) or not query.strip():
            raise SearchProviderError("empty query")
        max_results = max(1, min(int(max_results), MAX_RESULTS_CAP))
        subreddit, terms = self._parse_target(query)
        if not terms:
            raise SearchProviderError("empty query")
        token = self._access_token()
        params = {"q": terms, "limit": max_results, "sort": "relevance",
                  "type": "link", "raw_json": 1}
        if subreddit:
            params["restrict_sr"] = "true"
            endpoint = f"https://oauth.reddit.com/r/{urllib.parse.quote(subreddit)}/search"
        else:
            endpoint = self.SEARCH_ENDPOINT
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT,
                   "Authorization": f"Bearer {token}"}
        payload = self._get_json(f"{endpoint}?{urllib.parse.urlencode(params)}", headers)
        children = (((payload or {}).get("data") or {}).get("children")) or []
        results = []
        for child in children:
            if not isinstance(child, dict):
                continue
            data = child.get("data")
            if not isinstance(data, dict):
                continue
            permalink = data.get("permalink")
            if not isinstance(permalink, str) or not permalink.startswith("/"):
                continue  # no canonical discussion URL — skip, never invent one
            url = f"https://www.reddit.com{permalink}"
            selftext = data.get("selftext")
            snippet = selftext if isinstance(selftext, str) and selftext.strip() \
                else data.get("title")
            results.append(SearchResult.build(
                "reddit", url=url, title=data.get("title"), snippet=snippet,
                published_at=self._iso_from_epoch(data.get("created_utc"))))
            if len(results) >= max_results:
                break
        return results


# --- provider registry (Phase R9a) --------------------------------------- #
# name -> builder(env, fetch_fn). Adding a source is a new entry here, not a
# new code path. Real-content social adapters are registered so build_provider
# / tests can construct them, but from_env() will NOT live-enable a GATED one
# unless the fail-closed privacy/security gate (below) is explicitly on.

# Per-adapter live-ingestion policy — the outcome of the R9a privacy/security
# review (decision log 2026-07-22), which replaced the earlier all-or-nothing
# RESEARCH_ALLOW_LIVE_SOCIAL switch (now RETIRED, no back-compat alias):
#
#   * Apple App Store reviews (`appstore`): CLEARED for live use (public,
#     unauthenticated, approved RSS feed, no commercial license). Still requires
#     an explicit fail-closed operator opt-in — RESEARCH_ALLOW_LIVE_APPSTORE=1
#     — as defensive hygiene, NOT a second privacy gate. Only the exact value
#     "1" enables (any typo / "true" / "yes" / empty stays off).
#   * Reddit (`reddit`): HARD-BLOCKED. Its Data API needs a paid
#     commercial-partner agreement for business use; not cleared. NO env value
#     enables it — turning it on later is a code change + a separate decision,
#     never an ops toggle.
APPSTORE_LIVE_ENV = "RESEARCH_ALLOW_LIVE_APPSTORE"


def _build_brave(env, fetch_fn):
    return BraveSearchProvider(env.get("BRAVE_SEARCH_API_KEY", ""), fetch_fn=fetch_fn)


def _build_appstore(env, fetch_fn):
    return AppStoreReviewsProvider(fetch_fn=fetch_fn,
                                   country=env.get("APPSTORE_COUNTRY", "us"))


def _build_reddit(env, fetch_fn):
    return RedditProvider(env.get("REDDIT_CLIENT_ID", ""),
                          env.get("REDDIT_CLIENT_SECRET", ""), fetch_fn=fetch_fn)


_PROVIDER_BUILDERS = {"brave": _build_brave, "appstore": _build_appstore,
                      "reddit": _build_reddit}
# adapters that ingest real external (potentially PII-bearing) content.
_GATED_PROVIDERS = {"appstore", "reddit"}
# cleared adapters -> the fail-closed opt-in env that live-enables them ("1" only)
_LIVE_OPT_IN_ENV = {"appstore": APPSTORE_LIVE_ENV}
# hard-blocked adapters -> the reason. NO env value enables these.
_HARD_BLOCKED = {
    "reddit": "Reddit's Data API requires a paid commercial-partner agreement "
              "for business use (the free/OAuth tier is personal-use only); not "
              "cleared by the R9a privacy/security review (decision log "
              "2026-07-22). It stays refused until a separate decision clears it.",
}


def live_enabled(name, env=None):
    """True only when adapter `name` is CLEARED and its fail-closed opt-in env
    is exactly "1". A HARD-BLOCKED adapter is never enabled, whatever the env
    says; an ungated adapter (e.g. brave) is trivially allowed."""
    e = env if env is not None else os.environ
    if name in _HARD_BLOCKED:
        return False
    envvar = _LIVE_OPT_IN_ENV.get(name)
    if envvar is None:
        return name not in _GATED_PROVIDERS
    return e.get(envvar, "0") == "1"


def build_provider(name, env=None, fetch_fn=None):
    """Construct a registered provider by name (injectable). Used by tests and,
    later, the runner. Does NOT consult the privacy gate — a caller that builds
    a gated adapter directly owns that responsibility; the ENV entry point
    (`from_env`) is the gated one. `mock` is never registered here."""
    e = env if env is not None else os.environ
    builder = _PROVIDER_BUILDERS.get((name or "").strip().lower())
    if builder is None:
        raise SearchProviderError(f"unknown search provider '{name}'")
    return builder(e, fetch_fn)


def from_env(env=None, fetch_fn=None):
    """The configured provider, or None when research is not configured.
    `mock` is intentionally not accepted here — synthetic results must never
    be produced by a deployment's environment configuration. Real-content
    social adapters follow the per-adapter R9a policy: a HARD-BLOCKED one
    (Reddit) is always refused; a CLEARED one (Apple) is refused unless its own
    fail-closed opt-in env is explicitly on (decision log 2026-07-22)."""
    e = env if env is not None else os.environ
    name = (e.get("RESEARCH_SEARCH_PROVIDER") or "").strip().lower()
    if not name:
        return None
    if name not in _PROVIDER_BUILDERS:
        raise SearchProviderError(f"unknown search provider '{name}'")
    if name in _HARD_BLOCKED:
        raise SearchProviderError(
            f"search provider '{name}' is not cleared for live ingestion: "
            f"{_HARD_BLOCKED[name]}")
    if name in _GATED_PROVIDERS and not live_enabled(name, e):
        raise SearchProviderError(
            f"search provider '{name}' ingests real external content "
            "(reviews, possibly personal data) and is disabled by default; "
            "its R9a privacy/security review has passed, so an operator must "
            f"opt in explicitly by setting {_LIVE_OPT_IN_ENV[name]}=1")
    return build_provider(name, e, fetch_fn)
