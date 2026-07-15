"""Source-URL safety and normalization (Integration Phase 4).

THE single home for the URL policy applied to evidence/monitoring source
links before they are ever placed in an API payload:

- Only absolute http:// and https:// URLs are ever emitted as `source_url`.
- javascript:, data:, file:, vbscript:, scheme-relative (//host), local
  filesystem paths, and anything malformed are rejected (None) — the UI
  then shows honest "no external source" text instead of a clickable link.
- Repository source references are often written scheme-less
  ("trustpilot.com/review/www.telr.com"); `normalize()` upgrades ONLY a
  string that strictly looks like a public domain path to https://, and
  refuses everything else. It never fabricates a URL that is not already
  written in the record.

The frontend applies the same accept-list again (defense in depth) before
rendering an anchor — see executive-ui/web/src/lib/safeUrl.ts.
"""

import re
from urllib.parse import urlsplit

# something.tld[/path][?query] — no scheme, no spaces, no @, no backslashes.
_DOMAIN_PATH_RE = re.compile(
    r"^[a-z0-9][a-z0-9-]{0,62}(\.[a-z0-9][a-z0-9-]{0,62})+"   # dotted host
    r"(:\d{2,5})?"                                             # optional port
    r"(/[^\s\\@]*)?$",                                         # optional path
    re.IGNORECASE,
)


def safe_url(value):
    """`value` if it is a well-formed absolute http(s) URL, else None."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or any(c.isspace() for c in candidate) or "\\" in candidate:
        return None
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https"):
        return None
    host = parts.hostname or ""
    # require a dotted public-looking host — rejects file-ish/localhost-ish
    # values and stops a local path from masquerading as an external source
    if "." not in host:
        return None
    return candidate


def normalize(value):
    """A safe absolute http(s) URL for a stored source reference, else None.

    Accepts an already-absolute http(s) URL, or a bare domain path exactly
    as written in the record ("news.ycombinator.com/item?id=47615145"),
    which gets https:// prepended. Anything else — other schemes, local
    paths, prose — returns None. Missing provenance stays missing.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip().rstrip(".,;")
    if not candidate:
        return None
    if "://" in candidate or candidate.startswith("//"):
        return safe_url(candidate)
    if candidate.startswith(("/", ".", "~")):
        return None  # local filesystem path — never an external source
    # split a trailing ?query off before matching, then re-attach
    path_part, sep, query = candidate.partition("?")
    if not _DOMAIN_PATH_RE.match(path_part):
        return None
    return safe_url("https://" + path_part + sep + query)


def first_candidate(text):
    """The first token of a stored source cell that normalizes to a safe
    absolute http(s) URL, else None. Used for evidence "Source" cells like
    "trustpilot.com/review/www.telr.com (SRC-001)". Never fabricates: a cell
    with no URL-shaped token yields None."""
    if not isinstance(text, str):
        return None
    for token in re.split(r"[\s()\[\];,]+", text):
        url = normalize(token)
        if url:
            return url
    return None
