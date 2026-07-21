"""Draft merchant research-question sets — shared runtime layer (Phase R10).

A pure owner-scoped store (`store.py`, `RQSET-` namespace) for
proposal-only question sets. Generation/taxonomy-validation orchestration lives
in `executive-ui/api/question_generator.py` (it composes the gap profile, the
LLM provider, and Merchant Voice's taxonomy validator); this package never
generates, validates a taxonomy, or writes the knowledge base.
"""

from .store import QuestionSetStore, QuestionStoreError, RQSET_RE, STATUSES

__all__ = ["QuestionSetStore", "QuestionStoreError", "RQSET_RE", "STATUSES"]
