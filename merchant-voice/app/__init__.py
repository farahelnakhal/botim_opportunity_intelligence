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
Phase 3 extraction has to pass through), manual and CSV-bulk response
ingestion, text-only transcript ingestion, deterministic redaction, and
withdrawal/retention/deletion (including recoverable transcript deletion).

Phase 3 implements: the canonical extraction eligibility gate (no
provider call may happen without it passing), provider-backed structured
extraction using the shared shared.llm.provider abstraction, deterministic
validation of everything the model proposes (source-excerpt verification,
quote/paraphrase enforcement, willingness-to-pay/frequency/severity
safeguards, single-response aggregate-claim rejection), and persistence of
every proposed observation as pending_review — the model may never approve
its own output, assign final evidence strength, create a finding, or touch
Part A/B/impact/assumption state. Still not implemented: reviewer
approval/rejection, duplicate observation merge, evidence candidates,
approved findings, strength bands, campaign aggregation, Part A proposals,
synthetic export, and Copilot Merchant Voice tools.
"""
