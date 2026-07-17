"""Research profiles — objective-based query generation (Phase R2).

A profile is a reusable, deterministic recipe: named objectives, each with
query templates that a small context dict fills in. No LLM is involved —
query generation is transparent, testable, and free. Profiles are labels on
runs (`research_runs.profile`), never hardcoded platform behavior: any
opportunity can use `generic`, and new profiles are added here as data.

The first validation profile is `sme-financial-product` (the "SME Credit
Cards" internship brief — see docs/product-context.md). Per the platform
rules it must serve that case well while the mechanism stays reusable; and
per the BOTIM constraint its objectives investigate viability and structure
(issuer/partner/program roles, non-card alternatives) rather than assuming
BOTIM issues cards or extends credit.

Context keys (all optional): `market` (e.g. "UAE", "GCC"), `segment` (e.g.
"SME"), `product` (e.g. "corporate card"), `extra_terms` (list of free
keywords appended as their own queries). Each profile declares its own
`defaults`; `generic` deliberately defaults to nothing (so an unparameterised
generic run stays genuinely generic, never the validation case), while
`sme-financial-product` defaults to its documented UAE/SME/corporate-card
focus. Empty fields collapse cleanly out of the generated query text.
"""

import re

PROFILE_MAX_QUERIES = 20

# A profile with no defaults of its own falls back to these — empty, i.e. no
# assumed market/segment/product. Never bake the validation case in here.
_NEUTRAL_CONTEXT = {"market": "", "segment": "", "product": ""}

PROFILES = {
    "generic": {
        "title": "Generic opportunity research",
        "defaults": {},  # genuinely generic: no assumed market/segment/product
        "objectives": [
            ("market size", ["{market} {segment} {product} market size",
                             "{market} {segment} {product} adoption statistics"]),
            ("competitors", ["{product} providers {market} {segment}",
                             "{market} {segment} {product} competitors comparison"]),
            ("customer need", ["{market} {segment} {product} pain points problems"]),
            ("pricing", ["{product} pricing fees {market}"]),
            ("regulation", ["{market} {product} regulation licensing requirements"]),
        ],
    },
    "sme-financial-product": {
        "title": "SME financial-product opportunity (first validation profile)",
        # This profile IS the UAE/GCC SME validation case, so it legitimately
        # defaults to that focus; any run may still override via context.
        "defaults": {"market": "UAE", "segment": "SME", "product": "corporate card"},
        "objectives": [
            ("market size and segmentation",
             ["{market} SME market size number of businesses statistics",
              "{market} SME definition segmentation criteria central bank"]),
            ("spending and cash-flow behavior",
             ["{market} SME spending behavior working capital needs study",
              "{market} SME cash flow challenges payment delays"]),
            ("card and non-card adoption",
             ["{market} SME {product} adoption usage statistics",
              "{market} SME payment methods corporate cards vs bank transfer"]),
            ("competitors international",
             ["SME corporate card spend management platforms comparison international",
              "business expense card startups Brex Ramp Pleo equivalents {market}"]),
            ("competitors regional",
             ["{market} GCC SME business card fintech providers",
              "{market} banks SME credit card business card offerings"]),
            ("product structure and partnerships",
             ["card issuing program manager BIN sponsor model {market}",
              "embedded finance partnerships SME cards {market} issuer program"]),
            ("pricing and revenue model",
             ["{market} corporate card interchange rates fees",
              "SME card revenue model interchange annual fees FX"]),
            ("underwriting and onboarding",
             ["SME credit underwriting approaches alternative data {market}",
              "{market} SME onboarding KYB KYC requirements business account"]),
            ("risk and controls",
             ["SME corporate card fraud misuse controls spending limits",
              "SME credit card collections default rates {market}"]),
            ("regulation and licensing",
             ["{market} central bank card issuing license requirements",
              "{market} lending license SME finance regulation fintech"]),
        ],
    },
}


def available_profiles():
    return sorted(PROFILES)


def generate_queries(profile_name, context=None, max_queries=PROFILE_MAX_QUERIES):
    """[(objective, query_text), …] — deterministic, bounded, no fabrication:
    unknown profile raises KeyError for the caller to handle honestly."""
    profile = PROFILES[profile_name]
    ctx = dict(_NEUTRAL_CONTEXT)
    ctx.update(profile.get("defaults") or {})
    for key in ("market", "segment", "product"):
        value = (context or {}).get(key)
        if isinstance(value, str) and value.strip():
            ctx[key] = value.strip()
    out = []
    for objective, templates in profile["objectives"]:
        for template in templates:
            out.append((objective, _collapse(template.format(**ctx))))
    for term in (context or {}).get("extra_terms") or []:
        if isinstance(term, str) and term.strip():
            out.append(("additional focus",
                        _collapse(f"{ctx['market']} {ctx['segment']} {term.strip()}")))
    return out[:max(1, min(int(max_queries), PROFILE_MAX_QUERIES))]


def _collapse(text):
    """Normalise whitespace so empty context fields don't leave gaps or
    stray leading/trailing spaces in a query (e.g. the generic profile with
    no market/segment/product supplied)."""
    return re.sub(r"\s+", " ", text).strip()
