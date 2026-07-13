"""Merchant Voice & Validation — backend (Phase 1 + Phase 2).

PROTOTYPE-GRADE AUTHENTICATION. SYNTHETIC-DATA-ONLY. NOT FOR PRODUCTION USE
AND NOT APPROVED FOR REAL MERCHANT DATA.

A separate, human-reviewed research-to-evidence pipeline: research campaigns
and guides -> merchant participants and responses (manual + CSV + text
transcript ingestion, consent-gated, redacted) -> (Phase 3+) AI-assisted
extraction -> human review -> evidence candidates -> approved findings -> a
Part A evidence *proposal* (never an authoritative write). Nothing here
writes to Part A evidence, Part B scorecards/opportunities, the impact
engine, or monitoring history.

Phase 1 implements: shared provider wiring, configuration, auth, the
mv.db/identity.db schema foundation, campaigns, and research guides.

Phase 2 implements: pseudonymous participants (identity kept separately in
identity.db), consent/privacy gating (including the AI-processing gate
Phase 3 extraction will have to pass through — no provider is ever called
here), manual and CSV-bulk response ingestion, text-only transcript
ingestion, deterministic redaction, and withdrawal/retention/deletion
(including recoverable transcript deletion). Still not implemented: AI
extraction, observation review, evidence candidates, approved findings,
strength analysis, campaign aggregation, Part A proposals, and Copilot
Merchant Voice tools.
"""
