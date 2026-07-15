"""Safe, bounded page retrieval and text extraction (Phase R2).

Lawful-access posture (same rules as the monitoring regulator adapter):
plain GET of public pages, descriptive User-Agent, hard timeout, at most one
retry, graceful failure (a dead page degrades to a recorded error, never a
crash). Additional safety here:

- URLs must pass shared.source_urls.safe_url (absolute http(s) only).
- Response size is capped (MAX_BYTES) — the read stops at the cap.
- Only text-ish content types are parsed; anything else is recorded as
  "unsupported content type", not downloaded further.
- Extraction strips scripts/styles/tags; the result is plain text stored as
  DATA. Nothing downstream ever interprets fetched text as instructions.
- No cookies, no auth, no POST, no redirects beyond urllib's default cap.
"""

import hashlib
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    from shared.source_urls import safe_url
except ImportError:
    from ..source_urls import safe_url

from .providers import USER_AGENT

MAX_BYTES = 500_000
DEFAULT_TIMEOUT_S = 10
EXCERPT_MAX = 2000
ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")

# tracking params stripped during URL normalization (dedup only — the stored
# canonical_url keeps what the source actually was, minus pure tracking noise)
_TRACKING_PARAMS = re.compile(r"^(utm_\w+|gclid|fbclid|mc_cid|mc_eid|ref)$", re.IGNORECASE)


class FetchResult(dict):
    """ok, url, status?, content_type?, title?, text?, content_hash?, error?
    — absent fields stay None; nothing is invented."""


def normalize_url(url):
    """Canonical form for duplicate detection: lowercase scheme/host, no
    fragment, no tracking params, no trailing slash on a bare path. Returns
    None for unsafe/malformed URLs."""
    checked = safe_url(url)
    if checked is None:
        return None
    parts = urlsplit(checked)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                       if not _TRACKING_PARAMS.match(k)])
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), (parts.hostname or "").lower()
                       + (f":{parts.port}" if parts.port else ""), path, query, ""))


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "noscript", "template", "svg", "head"}
    _BLOCK = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
              "section", "article", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self.title_parts = []
        self.text_parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self._BLOCK:
            self.text_parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)
        elif not self._skip_depth:
            self.text_parts.append(data)


def extract_text(html):
    """(title, text) as plain strings; scripts/styles removed; whitespace
    collapsed. Malformed HTML never raises."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass  # keep whatever was extracted before the parse error
    title = re.sub(r"\s+", " ", "".join(parser.title_parts)).strip() or None
    text = re.sub(r"[ \t]+", " ", "".join(parser.text_parts))
    text = re.sub(r"\s*\n\s*", "\n", text).strip()
    return title, text


def make_excerpt(text, limit=EXCERPT_MAX):
    if not text:
        return None
    excerpt = text[:limit].strip()
    return excerpt or None


def content_hash(text):
    if not text:
        return None
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _http_fetch(url, timeout_s):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "text/html,text/plain"},
                                 method="GET")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        body = resp.read(MAX_BYTES + 1)
        return resp.status, ctype, body


def fetch_page(url, fetch_fn=None, timeout_s=DEFAULT_TIMEOUT_S):
    """Fetch one public page safely. Always returns a FetchResult — network
    problems become {ok: False, error: …}, never an exception. `fetch_fn`
    (url, timeout_s) -> (status, content_type, body_bytes) is injectable so
    tests stay offline."""
    checked = safe_url(url)
    if checked is None:
        return FetchResult(ok=False, url=url, error="unsafe or non-http(s) URL")
    fetch = fetch_fn or _http_fetch
    last_error = None
    for attempt in (1, 2):  # at most one retry
        try:
            status, ctype, body = fetch(checked, timeout_s)
            break
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            last_error = exc
            status = None
    if status is None:
        return FetchResult(ok=False, url=checked,
                           error=f"fetch failed after retry ({type(last_error).__name__})")
    if status != 200:
        return FetchResult(ok=False, url=checked, status=status,
                           error=f"HTTP {status}")
    if ctype and ctype not in ALLOWED_CONTENT_TYPES:
        return FetchResult(ok=False, url=checked, status=status, content_type=ctype,
                           error=f"unsupported content type '{ctype}'")
    truncated = len(body) > MAX_BYTES
    body = body[:MAX_BYTES]
    try:
        html = body.decode("utf-8", errors="replace")
    except Exception:
        return FetchResult(ok=False, url=checked, status=status,
                           error="undecodable response body")
    if ctype == "text/plain":
        title, text = None, html
        text = re.sub(r"[ \t]+", " ", text).strip()
    else:
        title, text = extract_text(html)
    return FetchResult(ok=True, url=checked, status=status, content_type=ctype or None,
                       title=title, text=text, truncated=truncated,
                       content_hash=content_hash(text))
