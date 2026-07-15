"""Application data modes (Phase 5) — normal | demo | test.

ONE backend configuration field is the source of truth:

    BOTIM_APP_MODE=normal|demo|test      (default: normal)

The effective mode is exposed to the frontend in the overview read model
(`meta.app_mode`), so the UI never has to guess from a second, independently
configured value. `VITE_APP_MODE` exists only as a build-time hint for the
one case where the backend cannot answer at all (deciding whether the
bundled demo seed may be used as an offline fallback) — it never overrides
the backend's mode.

Modes:

- **normal** (default; the production-oriented mode): the read model returns
  no synthetic demo opportunities, briefs, predictions, or monitoring feed
  items as if they were the user's. Persisted user opportunities and the
  reference knowledge layer (evidence corpus used by the grounded Copilot)
  remain available. The UI shows a clean empty state.
- **demo**: the committed synthetic corpus is served and clearly labelled as
  demo data; demo records stay read-only (the user-opportunity API only ever
  operates on UOPP- ids, never committed OPP- ids).
- **test**: behaves like demo for read-model content but exists so automated
  tests can pin a deterministic mode explicitly; it never loads production
  user data when a test store path is used (USER_OPPORTUNITIES_DB_PATH).

No mode ever falls back silently to another: an invalid BOTIM_APP_MODE value
resolves to "normal" (the safe default) — never to demo data.

Deployment notes: the bundled demo deployments (Render / Hugging Face Space)
set BOTIM_APP_MODE=demo explicitly in executive-ui/deploy/Dockerfile; local
development of the showcase uses BOTIM_APP_MODE=demo too. Anything left
unset is normal.
"""

import os

MODES = ("normal", "demo", "test")
DEFAULT_MODE = "normal"


def get_mode(env=None):
    """The effective application mode. Invalid values resolve to the safe
    default (normal) — never silently to demo."""
    env = os.environ if env is None else env
    value = env.get("BOTIM_APP_MODE", DEFAULT_MODE)
    value = str(value).strip().lower()
    return value if value in MODES else DEFAULT_MODE


def demo_corpus_visible(mode):
    """Whether the committed synthetic corpus may be presented as portfolio
    content (opportunities/briefs/predictions/monitoring feed)."""
    return mode in ("demo", "test")
