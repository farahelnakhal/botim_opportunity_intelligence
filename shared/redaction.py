"""Deterministic, regex-based PII redaction — the shared "floor, not ceiling"
for any text that will reach an AI/provider call or be persisted from an
external source.

Lifted into `shared/` in Phase H2 so the research platform's social-content
ingestion (Apple/Reddit reviews/posts) and Merchant Voice share ONE
implementation — no second copy to drift (Merchant Voice re-imports this via a
thin `merchant-voice/app/redaction.py` shim; its `test_redaction.py` passes
against this relocated module unchanged).

This module does **not** claim perfect PII detection. It is a conservative,
explainable, offline text transform: phone numbers, email addresses,
IBAN-like values, generic long account-number digit runs, a small set of
name-introduction patterns, and explicitly-supplied "known entity" strings
(e.g. a company name a researcher flags as sensitive) are replaced with
fixed placeholders. Anything not matched by these patterns is NOT
guaranteed to be redacted — this is a floor, not a ceiling.

`process_text()` never raises for a well-formed string; malformed input
(non-str, or containing NUL/control bytes suggesting non-text content) is
treated as a redaction *failure* so the caller can block the record from
future AI eligibility rather than silently pass unredacted content through.
"""

import re

CATEGORY_PHONE = "phone"
CATEGORY_EMAIL = "email"
CATEGORY_IBAN = "iban"
CATEGORY_ACCOUNT = "account"
CATEGORY_NAME = "name"
CATEGORY_ENTITY = "entity"
MANUAL_REVIEW_FLAG = "manual_review_required"

PLACEHOLDERS = {
    CATEGORY_PHONE: "[REDACTED-PHONE]",
    CATEGORY_EMAIL: "[REDACTED-EMAIL]",
    CATEGORY_IBAN: "[REDACTED-IBAN]",
    CATEGORY_ACCOUNT: "[REDACTED-ACCOUNT]",
    CATEGORY_NAME: "[REDACTED-NAME]",
    CATEGORY_ENTITY: "[REDACTED-ENTITY]",
}

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
PHONE_RE = re.compile(r"(?<!\w)\+?\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]\d{2,4}[\s-]\d{2,4}(?:[\s-]\d{2,4})?(?!\w)")
ACCOUNT_RE = re.compile(r"(?<!\w)\d{9,18}(?!\w)")
NAME_TRIGGER_RE = re.compile(
    r"\b(?:(?i:my name is|this is|i am|i'm|name:))\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})")

__all__ = [
    "CATEGORY_PHONE", "CATEGORY_EMAIL", "CATEGORY_IBAN", "CATEGORY_ACCOUNT",
    "CATEGORY_NAME", "CATEGORY_ENTITY", "MANUAL_REVIEW_FLAG", "PLACEHOLDERS",
    "EMAIL_RE", "IBAN_RE", "PHONE_RE", "ACCOUNT_RE", "NAME_TRIGGER_RE",
    "RedactionResult", "process_text", "process_answer",
]


class RedactionResult:
    def __init__(self, redacted_text, categories, manual_review_required):
        self.redacted_text = redacted_text
        self.categories = categories
        self.manual_review_required = manual_review_required


def _redact_names(text):
    found = []

    def _sub(match):
        found.append(match.group(1))
        return match.group(0)[: match.start(1) - match.start(0)] + PLACEHOLDERS[CATEGORY_NAME]

    new_text = NAME_TRIGGER_RE.sub(_sub, text)
    return new_text, bool(found)


def process_text(text, known_entities=None):
    """Returns a RedactionResult, or raises ValueError for input that cannot
    be safely processed as text (caller must treat this as a redaction
    failure, never as unredacted content)."""
    if not isinstance(text, str):
        raise ValueError("redaction input must be a string")
    if any(ord(ch) < 32 and ch not in ("\n", "\r", "\t") for ch in text):
        raise ValueError("redaction input contains non-text control bytes")

    categories = []
    result = text

    result, n = EMAIL_RE.subn(PLACEHOLDERS[CATEGORY_EMAIL], result)
    if n:
        categories.append(CATEGORY_EMAIL)

    result, n = IBAN_RE.subn(PLACEHOLDERS[CATEGORY_IBAN], result)
    if n:
        categories.append(CATEGORY_IBAN)

    result, n = PHONE_RE.subn(PLACEHOLDERS[CATEGORY_PHONE], result)
    if n:
        categories.append(CATEGORY_PHONE)

    result, n = ACCOUNT_RE.subn(PLACEHOLDERS[CATEGORY_ACCOUNT], result)
    if n:
        categories.append(CATEGORY_ACCOUNT)

    result, name_found = _redact_names(result)
    manual_review_required = False
    if name_found:
        categories.append(CATEGORY_NAME)
        manual_review_required = True

    for entity in (known_entities or []):
        if not entity:
            continue
        pattern = re.compile(re.escape(entity), re.IGNORECASE)
        result, n = pattern.subn(PLACEHOLDERS[CATEGORY_ENTITY], result)
        if n:
            if CATEGORY_ENTITY not in categories:
                categories.append(CATEGORY_ENTITY)

    return RedactionResult(result, categories, manual_review_required)


def process_answer(original_answer, known_entities=None):
    """Runs redaction for a raw answer at ingestion time. Returns
    (redaction_status, sensitive_data_flags) — never raises; a processing
    failure is captured as redaction_status="failed" with no flags, so the
    caller can block the record from AI eligibility without exposing the
    original sensitive text anywhere (not even in an error message)."""
    try:
        result = process_text(original_answer, known_entities=known_entities)
    except (ValueError, TypeError):
        return "failed", []
    flags = list(result.categories)
    if result.manual_review_required:
        flags.append(MANUAL_REVIEW_FLAG)
    return "complete", flags
