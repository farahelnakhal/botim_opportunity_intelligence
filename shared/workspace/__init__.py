"""Versioned preliminary analysis workspace (Phase R5, PR4).

Each saved chat/opportunity gets an append-only series of workspace versions
(AWV-). A version is a SNAPSHOT of one full analysis chain run — KB context,
external research run, extracted candidate claims, and a preliminary score
computed by the REAL scoring engine — with per-version provenance. Normal
follow-up questions reuse the latest complete version; the chain re-runs only
on explicit triggers (first_analysis, manual_refresh, meaningful_change,
stale, monitoring). Everything machine-generated stays labelled preliminary
until a human reviews it; approvals live on the claims themselves (research
store), never on a version.
"""

from .store import (WorkspaceStore, WorkspaceStoreError, TRIGGERS,  # noqa: F401
                    compare_versions)
from .builder import build_workspace, build_queries  # noqa: F401
