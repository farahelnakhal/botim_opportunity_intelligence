"""Merchant Voice & Validation — backend (Phase 1 + 2 + 3 + 4 + 5).

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
Part A/B/impact/assumption state.

Phase 4 implements: the human review workflow for those observations
(queue, edit with safeguard re-validation, approve/reject/merge — source
fields immutable, approved/rejected observations never silently edited,
separation-of-duties self-approval guard), evidence candidates (scoped to
one campaign, counts always computed from linked observations, known-
contradiction discovery), deterministic strength bands (the model never
assigns these), immutable approved Merchant Voice findings created only by
approving a candidate (still NOT authoritative Part A evidence), an
explicit publish/suppress action, campaign-level analysis (numerator/
denominator/segment-grouped, never a bare percentage), and full
withdrawal/revalidation integration with the Phase 2 suppression cascade.

Phase 5 implements: a human-reviewed Part A evidence proposal workflow
(app/part_a_proposal.py — generate only from an approved+published finding,
draft/edit/submit/approve/reject, a separate export-approval step, and
withdrawal-driven invalidation mirroring the Phase 4 finding cascade) whose
suggested_strength is always explicitly non-authoritative and whose
authoritative_ev_id is always null; a synthetic-only export action that
writes a server-named, banner-marked demo file to
knowledge-base/customer-evidence/merchant-voice-candidates/ (never
.../records/, never real merchant data); and a read-only,
Copilot-facing query layer (app/published_query.py — never opens
identity.db) exposing only approved, published, non-superseded content.
Nothing in Phase 5 mints an EV ID, writes authoritative Part A evidence,
promotes anything into Part A, or changes a score/assumption/impact/
monitoring record. Still not implemented (Phase 6+): authoritative EV
creation, Part A promotion, and any frontend.
"""
