# scripts/

Operational dev tools. Standard-library only; credential-free (they read
secrets from the environment, never from committed files).

## `smoke_smtp.py` — live SMTP send check (Phase R6)

Proves the real `shared/email` SMTP sender (STARTTLS + auth + send) works
against a live relay — the one thing `MockEmailSender` and the offline unit
tests cannot verify. Use it after a key rotation, an SMTP-provider change, or a
first deploy.

Run from the repo root, in an environment with **SMTP egress** (a local machine
or a shell on the deploy host — the CI/dev sandbox blocks outbound SMTP):

```bash
export SMTP_HOST=smtp-relay.example.com SMTP_PORT=587 SMTP_STARTTLS=true \
       SMTP_USERNAME=... SMTP_PASSWORD=... SMTP_FROM=you@example.com
python3 scripts/smoke_smtp.py recipient@inbox.example
```

The `SMTP_*` vars are the same ones the app reads (declared in `render.yaml`,
documented in `docs/current-state.md`). Never put the real password in a
committed file — export it in the shell or a gitignored `.env`. Wrong password
→ `EmailError status=502`; vars unset → `status=503`.
