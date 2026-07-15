"""Research platform (Phases R1-R2) — persisted, bounded external research.

See shared/contracts/research.schema.md for the contract and
docs/roadmap.md for where this layer is headed. R1: storage/traceability.
R2: provider seam (providers.py), safe retrieval (retrieval.py),
deterministic profiles (profiles.py), and the run executor (runner.py).
Claim extraction and human review arrive in R3.
"""

from .store import ResearchStore, ResearchStoreError  # noqa: F401
from .providers import MockSearchProvider, SearchProviderError, from_env as provider_from_env  # noqa: F401
from .runner import execute_run  # noqa: F401
