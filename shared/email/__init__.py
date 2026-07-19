"""Outbound email seam (Phase R6) — pure stdlib, provider-neutral SMTP.

See `sender.py` and docs/decision-log.md (2026-07-19 "R6 email"). The mock
sender is the explicit test default; unconfigured deployments get an honest
not-sent error, never a silent success.
"""

from .sender import (  # noqa: F401
    EmailError, EmailConfig, resolve_email_env, make_sender,
    SmtpEmailSender, MockEmailSender, UnconfiguredEmailSender)
