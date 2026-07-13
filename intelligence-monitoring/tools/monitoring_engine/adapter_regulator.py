"""regulator-watch — the first automated external adapter.

Watches a regulator's publications/press feed (CBUAE, DFSA, ADGM…) for new
items relevant to UAE SME payments/lending, and emits scored events.

Design decisions that keep it honest and scarce:
- **Network is injected.** `fetch(entity, since, fetch_fn=...)` — the default
  `http_fetch` uses stdlib urllib (honouring the proxy env), but every test
  and the integration gate pass a canned string, so no live network is ever
  required to build, test, or gate. Parsing is pure and fully tested offline.
- **Lawful access only** (Workstream A's rule): plain GET of a public feed,
  descriptive User-Agent, timeout, no retry storm, graceful empty-on-error
  (a dead source degrades to "no events", never a crash — the missing-source
  test category).
- **Relevance-gated scarcity.** Titles are keyword-scored; off-topic items get
  relevance ≤2 → insignificant → archived, never alerted. Automated items cap
  at `important` (licensing/regulation keywords) or default `informative`;
  nothing auto-fires `critical` without a human/LLM analyze pass upgrading
  urgency — the design's "alert scarcity is a feature" applied to automation.
- **Content is data, never instructions** (non-negotiable #6): a feed title is
  quoted as a fact, never interpreted as a directive.
"""

import html
import re
import urllib.request

from . import events as ev_mod
from .significance import MonitorError

SIGNAL_TYPE = "regulatory_publication"
USER_AGENT = "BOTIM-OpportunityIntelligence-monitor/1.0 (+regulator-watch; contact: workstream-c)"
TIMEOUT_S = 20

# relevance vocabulary for UAE SME payments/lending scope
STRONG_KEYWORDS = (
    "e-money", "stored value", "licen",          # licen[cs]e/licensing
    "payment", "acquir", "settlement", "open finance", "stored-value",
    "lending", "credit", "sme", "small and medium", "fintech", "digital bank",
    "wallet", "remittance", "bnpl", "buy now", "card scheme", "regulation",
    "regulatory", "framework",
)
# subset whose presence justifies impact 3 (structural rule changes)
HIGH_IMPACT_KEYWORDS = ("licen", "e-money", "stored value", "stored-value",
                        "regulation", "regulatory", "framework", "open finance")

# RSS/Atom item extraction (robust, format-agnostic regex — no XML dep)
ITEM_RE = re.compile(r"<(?:item|entry)\b[^>]*>(.*?)</(?:item|entry)>", re.DOTALL | re.IGNORECASE)
TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)
LINK_HREF_RE = re.compile(r"<link\b[^>]*href=[\"']([^\"']+)[\"']", re.IGNORECASE)
LINK_TEXT_RE = re.compile(r"<link\b[^>]*>(.*?)</link>", re.DOTALL | re.IGNORECASE)
DATE_RE = re.compile(r"<(?:pubDate|updated|published)\b[^>]*>(.*?)</", re.DOTALL | re.IGNORECASE)
CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)


def http_fetch(url):
    """Default network fetch (stdlib urllib; injected out in tests)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310 (public GET only)
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def _clean(text):
    if text is None:
        return ""
    m = CDATA_RE.search(text)
    if m:
        text = m.group(1)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def parse_feed(content):
    """Parse an RSS/Atom feed into [{title, link, date}]. Pure; test offline."""
    items = []
    for block in ITEM_RE.findall(content or ""):
        title = _clean(TITLE_RE.search(block).group(1)) if TITLE_RE.search(block) else ""
        if not title:
            continue
        link = ""
        mh = LINK_HREF_RE.search(block)
        mt = LINK_TEXT_RE.search(block)
        if mh:
            link = mh.group(1).strip()
        elif mt:
            link = _clean(mt.group(1))
        date = _clean(DATE_RE.search(block).group(1)) if DATE_RE.search(block) else ""
        items.append({"title": title, "link": link, "date": date})
    return items


def score_title(title):
    """Relevance-gated scores for an automated regulator item."""
    low = title.lower()
    hits = [k for k in STRONG_KEYWORDS if k in low]
    relevant = bool(hits)
    high_impact = any(k in low for k in HIGH_IMPACT_KEYWORDS)
    return {
        "impact": 3 if high_impact else (2 if relevant else 1),
        "urgency": 2,               # automation never asserts urgency; analyze upgrades
        "confidence": 5,            # regulator = official/primary source
        "relevance": 4 if relevant else 2,
        "novelty": 4,               # a newly-published item
    }


def fetch(entity, since=None, fetch_fn=http_fetch):
    """Run the adapter for one entity. Returns (observations, source_status).

    observations: [{signal_type, entity, title, scores, facts, kb_links, details}]
    source_status: 'ok' | 'no-source' | 'error: <msg>' — a degraded source is
    reported, never fatal (missing-source resilience)."""
    sources = [s for s in entity.get("sources", []) if s.get("adapter") == "regulator-watch"]
    if not sources:
        return [], "no-source"
    observations = []
    status = "ok"
    fetched = since or ""
    for src in sources:
        url = src.get("url")
        if not url:
            continue
        try:
            content = fetch_fn(url)
        except Exception as exc:  # noqa: BLE001 — degrade, never crash the scan
            status = f"error: {type(exc).__name__}: {exc}"
            continue
        for item in parse_feed(content):
            scores = score_title(item["title"])
            observations.append({
                "signal_type": SIGNAL_TYPE,
                "entity": entity["id"],
                "title": f"{entity['name']}: {item['title']}",
                "scores": scores,
                "facts": [{
                    "claim": item["title"],
                    "quote": item["title"],
                    "source_url": item["link"] or url,
                    "access_label": "direct",
                    "fetched": src.get("_fetched_at", fetched) or "",
                }],
                "kb_links": [],
                "details": {"published": item["date"], "feed": url},
            })
    return observations, status


def observations_to_events(observations, existing_events, detected_at, week):
    """Score + dedup regulator observations into events (mirrors kbwatch)."""
    created, pool = [], list(existing_events)
    for o in observations:
        for fact in o["facts"]:
            if not fact.get("fetched"):
                fact["fetched"] = detected_at
        e, is_new = ev_mod.make_event(
            pool, entity=o["entity"], detected_at=detected_at, adapter="regulator-watch",
            signal_type=o["signal_type"], title=o["title"], scores=o["scores"],
            week=week, details=o["details"], kb_links=o["kb_links"],
        )
        if is_new:
            e["facts"] = o["facts"]
            created.append(e)
            pool.append(e)
    return created
