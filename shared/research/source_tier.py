"""Source-tier registry (Phase R9a) — the executable meaning of an
"authoritative / verified" source, shared across the research platform.

Every research source is tagged T1..T4 by its DOMAIN, from this HUMAN-CURATED
registry. The tier is a registry lookup ONLY — never inferred by a model,
never derived from page content (which is untrusted, data-not-instructions).
An unknown domain falls to T4; it is never silently treated as authoritative.

  T1  government / regulator / official statistics
  T2  industry / analyst research
  T3  reputable press
  T4  general web / forums / social   (the default)

Shared on purpose: R9a uses it for source quality on candidate evidence, and
Phase C2 (verified-source market sizing) reuses the SAME tiers for its
corroboration rule (e.g. ">=2 independent T1/T2 sources"). Extend the tables
below only by human commit — that IS the curation.
"""

from urllib.parse import urlsplit

TIERS = ("T1", "T2", "T3", "T4")
DEFAULT_TIER = "T4"

# Registrable domain -> tier. Matched against the hostname AND each parent
# domain, so `data.worldbank.org` resolves via `worldbank.org`. Curated seed;
# grow it by commit (never programmatically, never from fetched content).
_REGISTRY = {
    # ---- T1: government / regulator / official statistics ----
    "centralbank.ae": "T1", "sca.gov.ae": "T1", "u.ae": "T1", "fcsc.gov.ae": "T1",
    "mohre.gov.ae": "T1", "dubaided.gov.ae": "T1",
    "imf.org": "T1", "worldbank.org": "T1", "oecd.org": "T1", "bis.org": "T1",
    "un.org": "T1", "wto.org": "T1",
    # ---- T2: industry / analyst research ----
    "mckinsey.com": "T2", "gartner.com": "T2",
    "deloitte.com": "T2", "pwc.com": "T2", "kpmg.com": "T2", "ey.com": "T2",
    "spglobal.com": "T2", "bcg.com": "T2", "forrester.com": "T2", "idc.com": "T2",
    # ---- T3: reputable press ----
    # statista.com is T3 (not T2): it is an AGGREGATOR that re-publishes others'
    # figures, so it must not carry primary-analyst weight — this matters for
    # C2's corroboration rule (a primary source + Statista repeating it are NOT
    # two independent sources).
    "statista.com": "T3",
    "reuters.com": "T3", "bloomberg.com": "T3", "ft.com": "T3", "wsj.com": "T3",
    "economist.com": "T3", "thenationalnews.com": "T3", "arabianbusiness.com": "T3",
    "zawya.com": "T3", "gulfnews.com": "T3", "khaleejtimes.com": "T3",
    # ---- T4: explicitly listed general/forum/social (also the default) ----
    # the R9a adapters' sources live here; listed to document intent, though
    # they would fall to the default anyway.
    "reddit.com": "T4", "apps.apple.com": "T4", "itunes.apple.com": "T4",
    "play.google.com": "T4", "medium.com": "T4", "quora.com": "T4",
    "x.com": "T4", "twitter.com": "T4", "facebook.com": "T4", "trustpilot.com": "T4",
}

# Unambiguous government TLD suffixes -> T1 (conservative; exact endswith only).
_GOV_SUFFIXES = (".gov", ".gov.ae", ".gov.uk", ".gov.sa", ".gov.qa", ".gov.bh",
                 ".gov.kw", ".gov.om", ".govt.nz", ".gc.ca")


def _hostname(url_or_domain):
    """Lowercased hostname for a URL or a bare domain, `www.` stripped."""
    s = (url_or_domain or "").strip().lower()
    if not s:
        return ""
    host = urlsplit(s if "//" in s else "//" + s).hostname or ""
    host = host.strip(".")
    return host[4:] if host.startswith("www.") else host


def tier_for(url_or_domain):
    """The T1..T4 tier for a URL or bare domain. Registry lookup only; an
    unknown domain returns DEFAULT_TIER (T4). Deterministic, no network,
    no content inspection."""
    host = _hostname(url_or_domain)
    if not host:
        return DEFAULT_TIER
    labels = host.split(".")
    # exact host, then each parent domain (data.worldbank.org -> worldbank.org).
    # CAVEAT: parent-domain matching means ANY content hosted under a listed
    # org's main domain inherits that org's tier — fine for the current seed,
    # but revisit once PR9a-2+ adapters pull from large multi-content domains
    # (e.g. a T2/T3 org that also hosts user-generated content on the same host
    # would wrongly lend its tier to that content).
    for i in range(len(labels) - 1):
        candidate = ".".join(labels[i:])
        if candidate in _REGISTRY:
            return _REGISTRY[candidate]
    for suffix in _GOV_SUFFIXES:
        if host.endswith(suffix):
            return "T1"
    return DEFAULT_TIER
