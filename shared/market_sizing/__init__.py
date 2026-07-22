"""Verified-source market sizing — candidate persistence (Phase C2).

A pure owner-scoped store (`store.py`, `MSZ-` namespace) for candidate TAM/SAM/SOM
sizings composed from corroborated, tier-ranked source figures. The composition
orchestration (figures + corroboration + the C1 calculator) lives in
`executive-ui/api/market_sizing_builder.py`; this package never computes,
corroborates, calls a model, or writes the knowledge base.
"""

from .store import MarketSizingStore, MarketSizingStoreError, MSZ_RE, STATUSES

__all__ = ["MarketSizingStore", "MarketSizingStoreError", "MSZ_RE", "STATUSES"]
