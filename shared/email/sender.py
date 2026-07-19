"""Outbound email seam (Phase R6) — pure stdlib, no SDK, no new dependency.

Design (see docs/decision-log.md, 2026-07-19 "R6 email"):

- Sending uses `smtplib` + `email.message.EmailMessage` against an
  operator-configured SMTP relay (SMTP_HOST / SMTP_PORT / SMTP_USERNAME /
  SMTP_PASSWORD / SMTP_FROM / SMTP_STARTTLS / SMTP_SSL). The backing provider
  (Amazon SES, Postmark, Resend, any SMTP server) is an OPERATOR choice — all
  expose SMTP, so this code is provider-neutral and adds no pip dependency.
- `MockEmailSender` records messages in memory and NEVER opens a socket; it is
  the explicit default in tests. This mirrors `MockProvider` in
  `shared/llm/provider.py`: the mock is selected explicitly, never as a silent
  production fallback.
- Unconfigured is an HONEST not-sent state: `make_sender()` returns an
  `UnconfiguredEmailSender` whose `send()` raises `EmailError(503)` — never a
  silent success. Secrets (the SMTP password) are never logged or echoed, and
  a delivery failure never leaks the SMTP dialog.

This module only SENDS a message it is handed. It does not decide who receives
it (that is the owner-scoped subscription in the workspace store) and it does
not compose monitoring bodies (that is the R6 digest renderer). Keeping send
separate from compose is the same discipline as `impact/email.py`, which
renders a digest and deliberately has no send capability.
"""

import os
import re
import smtplib
import ssl
from email.message import EmailMessage

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMAIL_MAX = 254
SUBJECT_MAX = 300
BODY_MAX = 200_000


class EmailError(Exception):
    """Safe, structured email error — `status` maps to the HTTP status; the
    message never contains the SMTP password or the raw server dialog."""

    def __init__(self, message, status=500):
        super().__init__(message)
        self.status = status


def _env_bool(env, name, default):
    value = env.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class EmailConfig:
    """Resolved SMTP settings. `configured` is the honest gate: without a host
    and a From address there is nothing to send through."""

    def __init__(self, host=None, port=587, username=None, password=None,
                 sender=None, use_starttls=True, use_ssl=False):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender
        self.use_starttls = use_starttls
        self.use_ssl = use_ssl

    @property
    def configured(self):
        return bool(self.host and self.sender)


def resolve_email_env(env=None):
    """Build an EmailConfig from the environment (SMTP_* variables). Absent or
    blank values stay None so `configured` reports the truth."""
    env = env if env is not None else os.environ

    def g(key):
        val = env.get(key)
        return val.strip() if isinstance(val, str) and val.strip() else None

    port_raw = env.get("SMTP_PORT")
    try:
        port = int(port_raw) if port_raw else 587
    except (ValueError, TypeError):
        port = 587
    return EmailConfig(
        host=g("SMTP_HOST"), port=port, username=g("SMTP_USERNAME"),
        password=(env.get("SMTP_PASSWORD") or None), sender=g("SMTP_FROM"),
        use_starttls=_env_bool(env, "SMTP_STARTTLS", True),
        use_ssl=_env_bool(env, "SMTP_SSL", False))


def _validate(to, subject, text_body):
    if not isinstance(to, str) or len(to) > EMAIL_MAX or not EMAIL_RE.match(to or ""):
        raise EmailError("a valid recipient email address is required", status=400)
    if not isinstance(subject, str) or not subject.strip():
        raise EmailError("an email subject is required", status=400)
    if len(subject) > SUBJECT_MAX:
        raise EmailError("the email subject is too long", status=400)
    if not isinstance(text_body, str) or not text_body.strip():
        raise EmailError("an email body is required", status=400)
    if len(text_body) > BODY_MAX:
        raise EmailError("the email body is too long", status=400)


def _build_message(sender, to, subject, text_body, html_body=None):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    # header-injection guard: a Subject can never span lines
    msg["Subject"] = subject.replace("\r", " ").replace("\n", " ").strip()
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    return msg


class MockEmailSender:
    """Records messages in memory; never touches the network. The explicit
    test default — assert against `.sent` instead of sending real mail."""

    def __init__(self, sender="monitoring@botim.test"):
        self.sender = sender
        self.sent = []

    def send(self, to, subject, text_body, html_body=None):
        _validate(to, subject, text_body)
        self.sent.append({"to": to, "subject": subject, "text_body": text_body,
                          "html_body": html_body, "from": self.sender})
        return {"sent": True, "transport": "mock", "to": to}


class UnconfiguredEmailSender:
    """Honest not-sent state when no SMTP relay is configured — the R6 caller
    records this as a failed notification, never as a delivered update."""

    sender = None

    def send(self, to, subject, text_body, html_body=None):
        raise EmailError("email not sent: no SMTP relay is configured "
                         "(set SMTP_HOST and SMTP_FROM)", status=503)


class SmtpEmailSender:
    """Sends one message through the operator's SMTP relay using stdlib only."""

    def __init__(self, config):
        self.config = config

    @property
    def sender(self):
        return self.config.sender

    def send(self, to, subject, text_body, html_body=None):
        cfg = self.config
        if not cfg.configured:
            raise EmailError("email not sent: SMTP relay is not configured", status=503)
        _validate(to, subject, text_body)
        msg = _build_message(cfg.sender, to, subject, text_body, html_body)
        try:
            if cfg.use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=15,
                                      context=context) as smtp:
                    self._auth_send(smtp, msg)
            else:
                with smtplib.SMTP(cfg.host, cfg.port, timeout=15) as smtp:
                    if cfg.use_starttls:
                        smtp.starttls(context=ssl.create_default_context())
                    self._auth_send(smtp, msg)
        except EmailError:
            raise
        except (smtplib.SMTPException, OSError) as exc:
            # never surface the password or the full SMTP dialog
            raise EmailError(f"email delivery failed: {type(exc).__name__}", status=502)
        return {"sent": True, "transport": "smtp", "to": to}

    def _auth_send(self, smtp, msg):
        cfg = self.config
        if cfg.username and cfg.password:
            smtp.login(cfg.username, cfg.password)
        smtp.send_message(msg)


def make_sender(config=None):
    """Return the active sender: a real SMTP sender when configured, otherwise
    an honest unconfigured sender (NOT the mock — the mock is test-only and is
    injected explicitly, never selected as a silent production fallback)."""
    cfg = config if config is not None else resolve_email_env()
    if cfg.configured:
        return SmtpEmailSender(cfg)
    return UnconfiguredEmailSender()
