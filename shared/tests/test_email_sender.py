"""Phase R6 (PR6a) — the outbound email seam. Pure stdlib, offline.

Verifies the honesty contract: the mock records instead of sending; an
unconfigured deployment fails loudly (never a silent success); env resolution
reports the truth; and the message builder guards against header injection."""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.email import (  # noqa: E402
    EmailError, MockEmailSender, UnconfiguredEmailSender, SmtpEmailSender,
    make_sender, resolve_email_env)


class EmailSeam(unittest.TestCase):
    def test_mock_records_and_never_sends(self):
        sender = MockEmailSender()
        out = sender.send("dest@example.com", "Subject", "Body text")
        self.assertEqual(out["transport"], "mock")
        self.assertEqual(len(sender.sent), 1)
        self.assertEqual(sender.sent[0]["to"], "dest@example.com")

    def test_unconfigured_is_an_honest_error_not_a_silent_success(self):
        sender = UnconfiguredEmailSender()
        with self.assertRaises(EmailError) as cm:
            sender.send("dest@example.com", "Subject", "Body")
        self.assertEqual(cm.exception.status, 503)
        self.assertIn("no SMTP relay is configured", str(cm.exception))

    def test_make_sender_picks_smtp_only_when_configured(self):
        # nothing configured -> honest unconfigured sender (NOT the mock)
        self.assertIsInstance(make_sender(resolve_email_env({})), UnconfiguredEmailSender)
        cfg = resolve_email_env({"SMTP_HOST": "smtp.example.com",
                                 "SMTP_FROM": "monitoring@example.com"})
        self.assertTrue(cfg.configured)
        self.assertIsInstance(make_sender(cfg), SmtpEmailSender)

    def test_resolve_env_reports_the_truth(self):
        blank = resolve_email_env({})
        self.assertFalse(blank.configured)
        self.assertIsNone(blank.host)
        full = resolve_email_env({"SMTP_HOST": "h", "SMTP_FROM": "f@x.io",
                                  "SMTP_PORT": "2525", "SMTP_STARTTLS": "0",
                                  "SMTP_SSL": "1", "SMTP_USERNAME": "u",
                                  "SMTP_PASSWORD": "secret"})
        self.assertEqual((full.host, full.sender, full.port), ("h", "f@x.io", 2525))
        self.assertFalse(full.use_starttls)
        self.assertTrue(full.use_ssl)

    def test_recipient_and_body_are_validated(self):
        sender = MockEmailSender()
        for bad_to in ("not-an-email", "", None):
            with self.assertRaises(EmailError):
                sender.send(bad_to, "Subject", "Body")
        with self.assertRaises(EmailError):
            sender.send("dest@example.com", "", "Body")       # empty subject
        with self.assertRaises(EmailError):
            sender.send("dest@example.com", "Subject", "")    # empty body

    def test_subject_header_injection_is_neutralized(self):
        from shared.email.sender import _build_message
        msg = _build_message("from@x.io", "to@x.io",
                             "Update\r\nBcc: victim@x.io", "body")
        # the newline-bearing header can never become a second header
        self.assertNotIn("\n", msg["Subject"])
        self.assertNotIn("\r", msg["Subject"])
        self.assertIsNone(msg["Bcc"])

    def test_smtp_response_error_surfaces_code_and_server_text(self):
        # a DATA-phase rejection (like Brevo's) must surface the server's own
        # code + message text for diagnosis — not just the exception class name
        import smtplib
        from shared.email import sender as sndr

        class FakeSMTP:
            def __init__(self, host, port, timeout=None): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def starttls(self, context=None): pass
            def login(self, u, p): pass
            def send_message(self, msg):
                raise smtplib.SMTPDataError(554, b"5.7.1 Message rejected as spam")

        cfg = sndr.resolve_email_env({"SMTP_HOST": "h", "SMTP_FROM": "f@x.io",
                                      "SMTP_STARTTLS": "1"})
        orig = smtplib.SMTP
        smtplib.SMTP = FakeSMTP
        try:
            with self.assertRaises(EmailError) as cm:
                sndr.SmtpEmailSender(cfg).send("d@example.com", "Subj", "Body")
        finally:
            smtplib.SMTP = orig
        exc = cm.exception
        self.assertEqual(exc.status, 502)
        self.assertEqual(exc.smtp_code, 554)
        self.assertIn("Message rejected as spam", exc.smtp_detail)
        # the human-readable message carries the code + text too
        self.assertIn("554", str(exc))
        self.assertIn("Message rejected as spam", str(exc))

    def test_recipients_refused_surfaces_each_address_reason(self):
        import smtplib
        from shared.email import sender as sndr

        class FakeSMTP:
            def __init__(self, host, port, timeout=None): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def starttls(self, context=None): pass
            def send_message(self, msg):
                raise smtplib.SMTPRecipientsRefused(
                    {"d@example.com": (550, b"5.1.1 unknown recipient")})

        cfg = sndr.resolve_email_env({"SMTP_HOST": "h", "SMTP_FROM": "f@x.io",
                                      "SMTP_STARTTLS": "1"})
        orig = smtplib.SMTP
        smtplib.SMTP = FakeSMTP
        try:
            with self.assertRaises(EmailError) as cm:
                sndr.SmtpEmailSender(cfg).send("d@example.com", "Subj", "Body")
        finally:
            smtplib.SMTP = orig
        self.assertEqual(cm.exception.status, 502)
        self.assertIn("unknown recipient", cm.exception.smtp_detail)
        self.assertIn("550", str(cm.exception))

    def test_smtp_send_failures_do_not_leak_the_dialog(self):
        # a real SMTP send to an unreachable host fails as a safe EmailError
        cfg = resolve_email_env({"SMTP_HOST": "127.0.0.1", "SMTP_PORT": "1",
                                 "SMTP_FROM": "f@x.io", "SMTP_STARTTLS": "0"})
        with self.assertRaises(EmailError) as cm:
            SmtpEmailSender(cfg).send("dest@example.com", "Subj", "Body")
        self.assertIn(cm.exception.status, (502,))
        self.assertIn("email delivery failed", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
