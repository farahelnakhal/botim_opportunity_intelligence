"""Merchant Voice re-imports the shared redaction floor.

The single implementation now lives in `shared/redaction.py` (lifted there in
Phase H2 so the research platform's social-content ingestion and Merchant Voice
share ONE deterministic floor — no second copy to drift). Merchant Voice keeps
importing it as before (`from app import redaction`); every name and behavior is
identical, so MV's `test_redaction.py` passes against this shim unchanged.

This module deliberately references only `shared.redaction` — never the
provider layer — so the Phase-2 "consent gate never calls the provider" check
(tests/test_provider_integration.py) still holds.
"""

from shared.redaction import (  # noqa: F401  (re-export — keep names identical)
    ACCOUNT_RE, CATEGORY_ACCOUNT, CATEGORY_EMAIL, CATEGORY_ENTITY,
    CATEGORY_IBAN, CATEGORY_NAME, CATEGORY_PHONE, EMAIL_RE, IBAN_RE,
    MANUAL_REVIEW_FLAG, NAME_TRIGGER_RE, PHONE_RE, PLACEHOLDERS,
    RedactionResult, process_answer, process_text)

__all__ = [
    "CATEGORY_PHONE", "CATEGORY_EMAIL", "CATEGORY_IBAN", "CATEGORY_ACCOUNT",
    "CATEGORY_NAME", "CATEGORY_ENTITY", "MANUAL_REVIEW_FLAG", "PLACEHOLDERS",
    "EMAIL_RE", "IBAN_RE", "PHONE_RE", "ACCOUNT_RE", "NAME_TRIGGER_RE",
    "RedactionResult", "process_text", "process_answer",
]
