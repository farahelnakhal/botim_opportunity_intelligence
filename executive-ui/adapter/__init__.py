"""Executive UI read-only adapter (feature/executive-ui).

Transforms committed repository outputs into UI-ready objects. It NEVER
writes to the knowledge base, NEVER recomputes scores in view code, and
NEVER reinterprets confidence — it reuses Workstream B's and C's existing
engines (scoring, backlog, evidence, journal, monitoring events/alerts/
summaries) as the single source of truth.

collect.build_model(root) -> dict is the one entry point the renderers use.
"""

__all__ = ["model", "collect"]
