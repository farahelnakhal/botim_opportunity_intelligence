# Merchant research-question sets (Phase R10, PR10b–c) — schema v2

Contract for **draft, proposal-only** merchant research-question sets generated
from an opportunity's evidence-gap profile. Implementation: the pure store
`shared/questions/store.py` (`QUESTION_SETS_DB_PATH`, default
`runtime/question-sets.db`, gitignored) + the generation orchestration
`executive-ui/api/question_generator.py` (composes `impact.gap_profile`,
`shared.llm.provider`, and Merchant Voice's own taxonomy validator). Changes are
**additive only**.

A question set is a **proposal**: `status` is born `draft` and a **human**
reviews it (PR10c) before any question is attached to a Merchant Voice guide.
Nothing here writes `knowledge-base/`, writes Merchant Voice storage, mutates a
score, or sends anything to a merchant. Questions are drafted by the LLM but
**every one is deterministically validated** against Merchant Voice's taxonomy
and against the profile before it is persisted — the model drafts text and picks
a taxonomy purpose/type; it never assigns severity (that is the deterministic
gap profile, PR10a) and never approves.

## ID namespace

| Prefix | Object | Shape |
|---|---|---|
| `RQSET-` | a draft question set | `RQSET-<12 hex>` |
| (question) | a question within a set | `<RQSET-id>-Q<n>` |

Cannot collide with any other namespace (`OPP-`, `UOPP-`, `RRUN-`, `RSRC-`,
`RCAND-`, `AWV-`, `WSUB-`, `MCFG-`, `MEVT-`, `DOC-`, `USER-`, `CALC-`, and
Merchant Voice's `MVC-`/`MVG-`/`MEF-`).

## Generation (model proposes, deterministic validation disposes)

From the gap profile's top-K weak links (bounded), one bounded model call
proposes questions; each is **rejected** (never softened) unless:
- it targets an `assumption_id` that is a real weak link **in this profile**
  (an invented/unmatched id is dropped — the model cannot fabricate a link);
- it conforms to Merchant Voice's taxonomy — validated by MV's own
  `validate_question_input` (`purpose ∈ QUESTION_PURPOSES`,
  `question_type ∈ QUESTION_TYPES`, non-empty text, `linked_assumption` matching
  `ASM-OPP-nnn-<factor>`);
- it is within the per-weak-link and per-set caps.

Survivors carry `linked_assumption` (the motivating gap) so review and any later
Merchant Voice guide can trace each question to the evidence gap it tests. A
missing/unconfigured model or a malformed response yields an **honest empty
draft with a note** — never a fabricated question.

## Question-set object

| Field | Type | Notes |
|---|---|---|
| `id` | `RQSET-…` | |
| `opportunity_id` | `OPP-nnn` | R10 targets committed opportunities (where gap profiles exist) |
| `status` | `draft\|approved\|rejected` | born `draft`; a human review transitions it **exactly once** (PR10c) |
| `questions` | question[] | validated survivors (below) |
| `provenance` | object \| null | `{generator, model, generated_at, gap_profile_weak_links:[{assumption_id, priority_rank, signals}]}` |
| `rejected_count` | int | proposed-but-rejected count (honest; shown) |
| `note` | string \| null | honest gap note (no model / no gaps / none passed validation) |
| `owner_user_id` | `USER-…` \| null | owner-scoped; legacy NULL shared; foreign → indistinguishable 404 |
| `created_at` | UTC ISO-8601 | |
| `reviewed_at` | UTC ISO-8601 \| null | set on review (**PR10c**, schema v2) |
| `reviewer` | `USER-…` \| null | the reviewing user (null when auth is off) |
| `review_note` | string \| null | optional reviewer note |

### Question object (Merchant Voice taxonomy shape)

`question_id` (`<RQSET-id>-Q<n>`), `text`, `purpose` (MV `QUESTION_PURPOSES`),
`question_type` (MV `QUESTION_TYPES`), `follow_up_prompts` (string[]),
`linked_assumption` (`ASM-OPP-nnn-<factor>`), `linked_hypothesis` (null in R10),
`signals` (the gap signals that motivated it), `source_weak_link_rank` (int).

## HTTP (executive API; `/api/` and `/executive-api/` aliases)

| Route | Behavior |
|---|---|
| `POST /opportunities/{OPP-nnn}/question-sets` | generate a draft set from the gap profile → 201 `{question_set}`. Owner-scoped; `question_generate` quota; mode-gated like the opportunity detail route |
| `GET /question-sets[?opportunity_id=]` | list draft sets (owner-scoped) |
| `GET /question-sets/{RQSET-id}` | one set (owner-scoped; foreign → 404) |
| `POST /question-sets/{RQSET-id}/review` (**PR10c**) | `{action: "approve"\|"reject", questions?, note?}` — draft → approved\|rejected, **exactly once** (409 if already reviewed). On approve, optional reviewer-edited `questions` REPLACE the set and are **re-validated against Merchant Voice's taxonomy** first (a bad edit → 400, the set stays a draft). Owner-scoped |
| `GET /question-sets/{RQSET-id}/handoff` (**PR10c**) | for an **approved** set only (else 409): `{handoff: {markdown, mv_guide_payload}}` — a copy-paste hand-off + a Merchant-Voice-guide-shaped payload. **Read-only; R10 never calls Merchant Voice** |
| `DELETE /question-sets/{RQSET-id}` (**PR10c**) | owner-scoped hard delete of a proposal (foreign/absent → 404) |

Review/hand-off **never** write the knowledge base or Merchant Voice, mint an EV
id, change a score, or contact a merchant — approval only unlocks the manual
hand-off (D3). Taxonomy re-validation of reviewer edits happens in the route
layer (executive-ui/api), never in the pure store (D1). Errors are structured
`{error: message}` with no SQL/paths/model output.

## Boundary (unchanged R10 invariants)

Proposals only. Nothing here writes `knowledge-base/` or Merchant Voice, mints an
EV id, changes a score, or contacts a merchant — a human creates the Merchant
Voice guide from a reviewed set through MV's own review/approval flow (D3).
