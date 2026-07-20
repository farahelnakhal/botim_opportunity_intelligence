"""Research profiles — objective-based query generation (Phase R2; multi-language
querying added in R9a/PR9a-4).

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
keywords appended as their own queries), `languages` (list of language codes
to issue queries in — see below). Each profile declares its own `defaults`;
`generic` deliberately defaults to nothing (so an unparameterised generic run
stays genuinely generic, never the validation case), while
`sme-financial-product` defaults to its documented UAE/SME/corporate-card
focus. Empty fields collapse cleanly out of the generated query text.

**Multi-language querying (R9a, querying only — NOT content translation, which
is R9c):** an objective's templates are keyed by language code. Query terms
per language are **human-curated** (like every other profile datum) — never
machine-translated, so generation stays deterministic and fabrication-free.
English (`en`) is always available and on by default; other languages are
opt-in per run via `context["languages"]`. Ships with `en` + `ar` curated on
`sme-financial-product`; `hi`/`ur` (roadmap "second") and `ml`/`tl`
("deferred") are recognized codes but **not yet curated** — requesting one
raises an honest error rather than emitting empty or guessed queries. Context
values (`{market}` etc.) are localized per language via `_CONTEXT_L10N`, with
an English fall-back for any value not in the glossary (never a guess).
"""

import re

PROFILE_MAX_QUERIES = 20

# Recognized query languages. `tier` documents delivery status (not behavior);
# a language is only usable for a given profile if that profile curates
# templates in it — otherwise generate_queries raises honestly.
LANGUAGES = {
    "en": {"name": "English", "tier": "first-class"},
    "ar": {"name": "Arabic", "tier": "first-class"},
    "hi": {"name": "Hindi", "tier": "second"},
    "ur": {"name": "Urdu", "tier": "second"},
    "ml": {"name": "Malayalam", "tier": "deferred"},
    "tl": {"name": "Tagalog", "tier": "deferred"},
}
DEFAULT_LANGUAGES = ("en",)  # non-English querying is opt-in per run

# Curated localization of context VALUES per language (market/segment/product).
# Registry lookup only; an unlisted value falls back to the English text — we
# never guess a translation. Grow by human commit, like the templates.
_CONTEXT_L10N = {
    "ar": {
        "UAE": "الإمارات", "GCC": "دول الخليج", "Saudi Arabia": "السعودية",
        "Egypt": "مصر", "Qatar": "قطر", "Bahrain": "البحرين", "Oman": "عُمان",
        "Kuwait": "الكويت",
        "SME": "الشركات الصغيرة والمتوسطة",
        "corporate card": "بطاقة الشركات",
    },
}

# A profile with no defaults of its own falls back to these — empty, i.e. no
# assumed market/segment/product. Never bake the validation case in here.
_NEUTRAL_CONTEXT = {"market": "", "segment": "", "product": ""}

PROFILES = {
    "generic": {
        "title": "Generic opportunity research",
        "defaults": {},  # genuinely generic: no assumed market/segment/product
        # English-only for now (list form == {"en": [...]}); localize by commit.
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
        # Curated in English AND Arabic (both first-class). Arabic query terms
        # are human-authored MSA — never machine-translated.
        "objectives": [
            ("market size and segmentation", {
                "en": ["{market} SME market size number of businesses statistics",
                       "{market} SME definition segmentation criteria central bank"],
                "ar": ["حجم سوق {segment} في {market} عدد المنشآت إحصاءات",
                       "تعريف {segment} في {market} معايير التصنيف حسب البنك المركزي"]}),
            ("spending and cash-flow behavior", {
                "en": ["{market} SME spending behavior working capital needs study",
                       "{market} SME cash flow challenges payment delays"],
                "ar": ["سلوك إنفاق {segment} في {market} احتياجات رأس المال العامل دراسة",
                       "تحديات التدفق النقدي لدى {segment} في {market} تأخر المدفوعات"]}),
            ("card and non-card adoption", {
                "en": ["{market} SME {product} adoption usage statistics",
                       "{market} SME payment methods corporate cards vs bank transfer"],
                "ar": ["معدل استخدام {product} لدى {segment} في {market} إحصاءات",
                       "طرق الدفع لدى {segment} في {market} البطاقات مقابل التحويلات البنكية"]}),
            ("competitors international", {
                "en": ["SME corporate card spend management platforms comparison international",
                       "business expense card startups Brex Ramp Pleo equivalents {market}"],
                "ar": ["منصات إدارة مصاريف الشركات وبطاقات الشركات مقارنة عالمية",
                       "شركات ناشئة لبطاقات مصاريف الأعمال Brex Ramp Pleo بدائل في {market}"]}),
            ("competitors regional", {
                "en": ["{market} GCC SME business card fintech providers",
                       "{market} banks SME credit card business card offerings"],
                "ar": ["مزودو بطاقات الأعمال لـ {segment} في {market} والخليج فنتك",
                       "عروض البنوك لبطاقات الائتمان وبطاقات الأعمال لـ {segment} في {market}"]}),
            ("product structure and partnerships", {
                "en": ["card issuing program manager BIN sponsor model {market}",
                       "embedded finance partnerships SME cards {market} issuer program"],
                "ar": ["نموذج إصدار البطاقات ومدير البرنامج وراعي BIN في {market}",
                       "شراكات التمويل المضمّن لبطاقات {segment} في {market} برنامج المُصدِر"]}),
            ("pricing and revenue model", {
                "en": ["{market} corporate card interchange rates fees",
                       "SME card revenue model interchange annual fees FX"],
                "ar": ["رسوم ومعدلات التبادل لبطاقات الشركات في {market}",
                       "نموذج إيرادات بطاقات {segment} رسوم التبادل والرسوم السنوية وصرف العملات"]}),
            ("underwriting and onboarding", {
                "en": ["SME credit underwriting approaches alternative data {market}",
                       "{market} SME onboarding KYB KYC requirements business account"],
                "ar": ["أساليب تقييم الجدارة الائتمانية لـ {segment} البيانات البديلة في {market}",
                       "متطلبات فتح حساب ومعرفة العميل للأعمال KYB KYC في {market}"]}),
            ("risk and controls", {
                "en": ["SME corporate card fraud misuse controls spending limits",
                       "SME credit card collections default rates {market}"],
                "ar": ["ضوابط الاحتيال وسوء الاستخدام لبطاقات الشركات حدود الإنفاق",
                       "معدلات التعثر والتحصيل لبطاقات ائتمان {segment} في {market}"]}),
            ("regulation and licensing", {
                "en": ["{market} central bank card issuing license requirements",
                       "{market} lending license SME finance regulation fintech"],
                "ar": ["متطلبات ترخيص إصدار البطاقات من البنك المركزي في {market}",
                       "تنظيم تمويل {segment} وترخيص الإقراض والفنتك في {market}"]}),
        ],
    },
}


def available_profiles():
    return sorted(PROFILES)


def _templates_by_lang(value):
    """Normalize an objective's templates to a {lang: [templates]} dict. A bare
    list is treated as English-only (backward compatible)."""
    return {"en": value} if isinstance(value, list) else dict(value)


def _profile_languages(profile):
    """The set of languages this profile actually curates templates in."""
    langs = set()
    for _objective, templates in profile["objectives"]:
        langs.update(_templates_by_lang(templates))
    return langs


def _resolve_languages(context):
    """The requested language codes, validated. Defaults to English. Every code
    must be a recognized LANGUAGES key (else ValueError) — dedup, order
    preserved."""
    requested = (context or {}).get("languages")
    if not requested:
        return list(DEFAULT_LANGUAGES)
    if isinstance(requested, str):
        requested = [requested]
    if not isinstance(requested, (list, tuple)):
        raise ValueError("'languages' must be a list of language codes")
    out = []
    for code in requested:
        code = (code or "").strip().lower() if isinstance(code, str) else ""
        if code not in LANGUAGES:
            raise ValueError(
                f"unknown query language '{code}' "
                f"(recognized: {', '.join(sorted(LANGUAGES))})")
        if code not in out:
            out.append(code)
    return out or list(DEFAULT_LANGUAGES)


def _localize_context(ctx, lang):
    """Context values rendered for `lang`: English is identity; other languages
    use the curated glossary, falling back to the English value for anything
    uncurated (never a guessed translation)."""
    if lang == "en":
        return ctx
    glossary = _CONTEXT_L10N.get(lang, {})
    return {key: (glossary.get(value, value) if value else value)
            for key, value in ctx.items()}


def generate_queries(profile_name, context=None, max_queries=PROFILE_MAX_QUERIES):
    """[(objective, query_text, language), …] — deterministic, bounded, no
    fabrication. Unknown profile raises KeyError; an unknown or uncurated
    requested language raises ValueError — both for the caller to handle
    honestly. Multiple languages share the query budget breadth-first (every
    objective/language gets its first query before any gets a second), so a
    truncated multi-language run still covers all objectives in each language.
    """
    profile = PROFILES[profile_name]
    languages = _resolve_languages(context)
    curated = _profile_languages(profile)
    missing = [c for c in languages if c not in curated]
    if missing:
        raise ValueError(
            f"profile '{profile_name}' has no curated query templates for "
            f"language(s) {', '.join(missing)} (curated: {', '.join(sorted(curated))})")

    ctx = dict(_NEUTRAL_CONTEXT)
    ctx.update(profile.get("defaults") or {})
    for key in ("market", "segment", "product"):
        value = (context or {}).get(key)
        if isinstance(value, str) and value.strip():
            ctx[key] = value.strip()
    ctx_by_lang = {lang: _localize_context(ctx, lang) for lang in languages}

    # Build (objective, [per-language template lists]) then emit breadth-first
    # by template index so every objective×language gets a first query before
    # any gets a second — fair coverage under the shared cap.
    plans = []  # [(objective, {lang: [templates]})]
    max_depth = 0
    for objective, raw_templates in profile["objectives"]:
        by_lang = _templates_by_lang(raw_templates)
        plans.append((objective, by_lang))
        for lang in languages:
            max_depth = max(max_depth, len(by_lang.get(lang, [])))

    out = []
    for depth in range(max_depth):
        for objective, by_lang in plans:
            for lang in languages:
                templates = by_lang.get(lang, [])
                if depth < len(templates):
                    rendered = _collapse(templates[depth].format(**ctx_by_lang[lang]))
                    if rendered:
                        out.append((objective, rendered, lang))

    for term in (context or {}).get("extra_terms") or []:
        if isinstance(term, str) and term.strip():
            # free keywords are English; tagged en
            out.append(("additional focus",
                        _collapse(f"{ctx['market']} {ctx['segment']} {term.strip()}"),
                        "en"))
    return out[:max(1, min(int(max_queries), PROFILE_MAX_QUERIES))]


def _collapse(text):
    """Normalise whitespace so empty context fields don't leave gaps or
    stray leading/trailing spaces in a query (e.g. the generic profile with
    no market/segment/product supplied)."""
    return re.sub(r"\s+", " ", text).strip()
