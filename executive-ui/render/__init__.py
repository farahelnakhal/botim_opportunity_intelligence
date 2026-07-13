"""Server-side HTML renderers (stdlib only). Pure functions: UIModel -> HTML
strings. No scoring, no data mutation. Every renderer escapes external text."""

__all__ = ["layout", "overview", "opportunity", "evidence", "assumptions",
           "feed", "proposal", "brief"]
