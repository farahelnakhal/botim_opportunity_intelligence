"""Research platform (Phase R1) — persistence for external-research runs.

See shared/contracts/research.schema.md for the contract and
docs/roadmap.md (Phases R1-R4) for where this layer is headed. R1 is
storage only: no live fetching, no query generation, no review UI.
"""

from .store import ResearchStore, ResearchStoreError  # noqa: F401
