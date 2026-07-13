"""Deterministic redaction tests: category detection, placeholders,
failure gate (never claims perfect PII detection — see module docstring)."""

import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND.parent))

from app import redaction  # noqa: E402


class RedactionCategoryTests(unittest.TestCase):
    def test_redacts_phone(self):
        r = redaction.process_text("Call me at +971-50-123-4567 please.")
        self.assertIn("[REDACTED-PHONE]", r.redacted_text)
        self.assertIn("phone", r.categories)
        self.assertNotIn("971-50-123-4567", r.redacted_text)

    def test_redacts_email(self):
        r = redaction.process_text("Reach me at merchant@example.com.")
        self.assertIn("[REDACTED-EMAIL]", r.redacted_text)
        self.assertIn("email", r.categories)

    def test_redacts_iban(self):
        r = redaction.process_text("IBAN: AE070331234567890123456")
        self.assertIn("[REDACTED-IBAN]", r.redacted_text)
        self.assertIn("iban", r.categories)

    def test_redacts_account_number(self):
        r = redaction.process_text("Account 123456789012 needs a refund.")
        self.assertIn("[REDACTED-ACCOUNT]", r.redacted_text)
        self.assertIn("account", r.categories)

    def test_redacts_name_with_manual_review_flag(self):
        r = redaction.process_text("My name is Fatima Noor and I run the shop.")
        self.assertIn("[REDACTED-NAME]", r.redacted_text)
        self.assertIn("name", r.categories)
        self.assertTrue(r.manual_review_required)
        self.assertIn("and I run the shop", r.redacted_text)

    def test_redacts_known_entity(self):
        r = redaction.process_text("We buy from Al Faris Trading every month.",
                                   known_entities=["Al Faris Trading"])
        self.assertIn("[REDACTED-ENTITY]", r.redacted_text)
        self.assertIn("entity", r.categories)

    def test_clean_text_untouched(self):
        text = "Our biggest problem is late supplier payments."
        r = redaction.process_text(text)
        self.assertEqual(r.redacted_text, text)
        self.assertEqual(r.categories, [])
        self.assertFalse(r.manual_review_required)

    def test_does_not_claim_perfect_detection(self):
        # a name with no trigger phrase is NOT expected to be caught —
        # this is the documented floor, not a ceiling.
        r = redaction.process_text("Ahmed said the pricing was unfair.")
        self.assertNotIn("[REDACTED-NAME]", r.redacted_text)


class RedactionGateTests(unittest.TestCase):
    def test_process_answer_complete_for_clean_text(self):
        status, flags = redaction.process_answer("no PII here at all")
        self.assertEqual(status, "complete")
        self.assertEqual(flags, [])

    def test_process_answer_complete_with_categories(self):
        status, flags = redaction.process_answer("call me at merchant@example.com")
        self.assertEqual(status, "complete")
        self.assertIn("email", flags)

    def test_process_answer_failed_for_non_string_input(self):
        status, flags = redaction.process_answer(None)
        self.assertEqual(status, "failed")
        self.assertEqual(flags, [])

    def test_process_answer_failed_for_control_bytes(self):
        status, flags = redaction.process_answer("hello\x00world")
        self.assertEqual(status, "failed")
        self.assertEqual(flags, [])

    def test_process_text_raises_for_malformed_input_never_silently_passes_through(self):
        with self.assertRaises(ValueError):
            redaction.process_text(12345)


if __name__ == "__main__":
    unittest.main(verbosity=2)
