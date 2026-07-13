"""Merchant Voice & Validation — backend (Phase 1: foundation only).

PROTOTYPE-GRADE AUTHENTICATION. SYNTHETIC-DATA-ONLY. NOT FOR PRODUCTION USE
AND NOT APPROVED FOR REAL MERCHANT DATA.

A separate, human-reviewed research-to-evidence pipeline: research campaigns
and guides -> (Phase 2+) merchant responses -> AI-assisted extraction ->
human review -> evidence candidates -> approved findings -> a Part A evidence
*proposal* (never an authoritative write). Nothing here writes to Part A
evidence, Part B scorecards/opportunities, the impact engine, or monitoring
history.

Phase 1 implements only: shared provider wiring, configuration, auth, the
mv.db/identity.db schema foundation, campaigns, and research guides.
"""
