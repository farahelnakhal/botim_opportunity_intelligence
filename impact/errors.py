"""Shared exception type for the impact workflow."""


class ImpactError(Exception):
    """Any handled workflow error (validation, staleness, integrity, gating)."""
