#!/usr/bin/env python3
"""Standalone SMTP smoke test for the Phase R6 email sender (shared/email).

CREDENTIAL-FREE: reads SMTP_* from the environment — it never contains and
never prints secrets (the password is never echoed). Use it to prove the REAL
smtplib STARTTLS + auth + send path works against a live relay, which the
offline unit tests (MockEmailSender) structurally cannot cover.

Run it in an environment that HAS SMTP egress (a local machine, or a shell on
the deploy host) — this repo's CI/dev sandbox blocks outbound SMTP (443 only),
so it cannot run there. See docs/decision-log.md (R6 email entry).

Usage (from the repo root):
    export SMTP_HOST=smtp-relay.example.com SMTP_PORT=587 SMTP_STARTTLS=true \
           SMTP_USERNAME=... SMTP_PASSWORD=... SMTP_FROM=you@example.com
    python3 scripts/smoke_smtp.py recipient@inbox.example

Interpreting results:
  - creds set correctly        -> "SEND OK" (check the inbox, and spam)
  - wrong SMTP_PASSWORD        -> "SEND FAILED (EmailError status=502)" (auth/TLS/delivery)
  - SMTP_HOST / SMTP_FROM unset -> "SEND FAILED (EmailError status=503)" (honest unconfigured)
The 502-vs-503 split is the same distinction the tick records as
email_send_failed vs email_unconfigured.
"""

import os
import sys
from pathlib import Path

# make `shared` importable regardless of the caller's working directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.email import EmailError, make_sender, resolve_email_env  # noqa: E402


def main():
    to = sys.argv[1] if len(sys.argv) > 1 else None
    if not to:
        print("usage: python3 scripts/smoke_smtp.py <recipient@example.com>")
        return 2
    cfg = resolve_email_env()
    # never prints the password — only whether auth is configured
    print(f"host={cfg.host!r} port={cfg.port} from={cfg.sender!r} "
          f"starttls={cfg.use_starttls} ssl={cfg.use_ssl} "
          f"configured={cfg.configured} auth={'yes' if cfg.username else 'no'}")
    sender = make_sender(cfg)
    print(f"sender: {type(sender).__name__}")
    try:
        result = sender.send(
            to, "BOTIM R6 SMTP smoke test",
            "Plain-text smoke test of the R6 SMTP sender. Receiving this confirms "
            "STARTTLS negotiation, auth, and send all work against this relay.")
        print(f"SEND OK: {result}")
        return 0
    except EmailError as exc:
        print(f"SEND FAILED (EmailError status={exc.status}): {exc}")
        # surface the raw server response for diagnosis (rejection reason, not
        # a secret — auth already succeeded before this point)
        if exc.smtp_code is not None:
            print(f"  SMTP response code: {exc.smtp_code}")
        if exc.smtp_detail:
            print(f"  SMTP server said : {exc.smtp_detail}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
