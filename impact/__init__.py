"""Human-governed evidence-impact workflow (shared: Workstream A + B).

New evidence -> impact proposal -> human approval -> transactional application
-> validation -> append-only score history -> executive email preview, with
rollback and automatic recovery of interrupted transactions.

Jointly owned by both workstreams (see root README). Reuses, and never
modifies, the Part B scoring engine and the Part A evidence parser.
"""
