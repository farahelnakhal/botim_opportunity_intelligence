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
    provider. Only `url` is guaranteed."""

    @classmethod
    def build(cls, provider, url, title=None, snippet=None, published_at=None):
        return cls(provider=provider, url=url, title=_clean_str(title),
                   snippet=_clean_str(snippet, 1000),
                   published_at=_clean_str(published_at, 120))


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


def from_env(env=None, fetch_fn=None):
    """The configured provider, or None when research is not configured.
    `mock` is intentionally not accepted here — synthetic results must never
    be produced by a deployment's environment configuration."""
    e = env if env is not None else os.environ
    name = (e.get("RESEARCH_SEARCH_PROVIDER") or "").strip().lower()
    if not name:
        return None
    if name == "brave":
        return BraveSearchProvider(e.get("BRAVE_SEARCH_API_KEY", ""), fetch_fn=fetch_fn)
    raise SearchProviderError(f"unknown search provider '{name}'")
