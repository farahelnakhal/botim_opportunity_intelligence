# conversation-api.schema — v1.0

**Producer:** `copilot-backend/` (stdlib Python HTTP JSON API) · **Consumer:** the executive UI (Farah) via normal `fetch()`. **Read-only backend:** it never modifies evidence, segments, scorecards, assumptions, impact state, monitoring history, or backlogs; chat-triggered generation (drafts, briefs) is ephemeral/in-memory only.

**Streaming: not supported in 1.0.** Responses are single JSON documents. (A future 1.1 may add SSE via `Accept: text/event-stream`; nothing in 1.0 depends on it.)

## Server & auth

- Default bind: `127.0.0.1:8010` (`COPILOT_HOST`/`COPILOT_PORT`). Never binds non-locally unless explicitly configured.
- CORS: only the configured UI origin (`COPILOT_CORS_ORIGIN`, default `http://localhost:8000`). Preflight `OPTIONS` supported.
- If `COPILOT_API_TOKEN` is set (required for any non-local bind), every request must send `Authorization: Bearer <token>`; otherwise 401 `unauthorized`.

## Endpoints

| Method & path | Purpose |
|---|---|
| `POST /api/chat` | send a message; creates a conversation when `conversation_id` is null |
| `GET /api/conversations/{conversation_id}` | conversation metadata |
| `GET /api/conversations/{conversation_id}/messages` | ordered messages |
| `DELETE /api/conversations/{conversation_id}` | permanently removes the conversation **and all its stored messages** from the local store (never touches knowledge-base records) |

## POST /api/chat — request

| Field | Req? | Nullable | Type | Notes |
|---|---|---|---|---|
| `conversation_id` | optional | yes | string | null/absent ⇒ new conversation |
| `message` | required | no | string | 1..`COPILOT_MAX_MESSAGE_CHARS` (default 4000) |
| `context` | optional | yes | object | optional hints: `opportunity_id`, `segment_id` (validated IDs only); Phase 6 additive: `user_opportunity` — a persisted user-opportunity draft (`shared/contracts/user-opportunities.schema.md`), sanitized/bounded server-side and grounded as clearly labelled USER-PROVIDED fields, never repository evidence, never written back |

```json
{ "conversation_id": null,
  "message": "Why is OPP-013 still unvalidated?",
  "context": { "opportunity_id": "OPP-013" } }
```

## POST /api/chat — response (200)

| Field | Req? | Nullable | Type / enum |
|---|---|---|---|
| `schema_version` | required | no | `"1.0"` |
| `conversation_id` | required | no | string (`conv_…`) |
| `message_id` | required | no | string (`msg_…`) |
| `answer_markdown` | required | no | string — natural-language answer ending with an **“Evidence used”** section |
| `answer_type` | required | no | enum: `analysis, brief, comparison, evidence, challenge, assumptions, research_recommendation, research_request_draft, change_summary, merchant_feedback, new_opportunity_analysis, clarification` (`merchant_feedback` added for Merchant Voice research questions; `new_opportunity_analysis` added in Integration Phase 2 for a genuinely new idea with no OPP record yet; `clarification` added in Phase 3 for a bare greeting/help message with no product-discovery content — all additive, backward compatible, `schema_version` unchanged) |
| `confidence` | required | no | `{level: "high"|"medium"|"low"|"mixed", basis: string}` — derived deterministically from records/engines, never model-invented |
| `citations` | required | no | array of citation objects (below); may be empty |
| `assumptions` | required | no | string[] — working assumptions relevant to the answer |
| `unknowns` | required | no | string[] — explicit gaps; never silently filled |
| `recommended_next_actions` | required | no | string[] |
| `warnings` | required | no | string[] (e.g. wording-guard notes, weak-evidence flags) |
| `safe_tool_trace` | required | no | string[] — **empty `[]` in normal production responses**; populated with short operational one-liners (e.g. `"loaded OPP-013"`) only when the server runs with `COPILOT_DEBUG_TRACE=1`. Never contains prompts, reasoning, provider payloads, file paths, secrets, or full tool results |
| `runtime_mode` | required (Phase 3) | no | enum: `deterministic_demo` \| `live_model` — `deterministic_demo` when the configured provider is `MockProvider` (echoes only the grounded facts block, never invents), `live_model` for any real model provider (currently Anthropic). Additive; absent is backward-compatible (older clients ignore it). Never reveals whether an API key is configured, the provider class, or any other configuration detail |
| `draft` | optional | yes | object — present only for draft answer types; ephemeral (never persisted server-side beyond conversation storage) |

Citation object:

```json
{ "id": "EV-2026-W28-014",
  "type": "evidence",             // enum: evidence | opportunity | segment | inflection | experiment | assumption | merchant_finding | competitor
  "title": "Card rails appear unsuitable for many core supplier-payment transactions…",
  "role": "primary",              // enum: primary | contextual | contradictory | weak_lead | excluded | concept_reaction
  "target": { "type": "internal_route", "value": "/evidence/EV-2026-W28-014" },
  "metadata": null }              // additive field; non-null for merchant_finding citations and (Phase 4) evidence citations with provenance — see below
```

`target.value` is an internal UI route (`/evidence/{id}`, `/opportunity/{id}`, `/segment/{id}`, `/inflection/{id}`, `/experiment/{id}`, `/assumption/{id}`, `/merchant-findings/{id}`) — never a filesystem path.

**`merchant_finding` citations (additive — every other citation type keeps `metadata: null`).** A `merchant_finding` citation points at an approved, **published** Merchant Voice finding (`shared/contracts/merchant-voice-api.schema.md`) — a research signal, never authoritative Part A evidence, never assigned an EV ID. Its `role` is `concept_reaction` when the finding type is a concept reaction (never presented as proof of pain/frequency/willingness-to-pay), `contradictory` for a contradiction finding, `weak_lead` for `single_signal`/`insufficient` strength, otherwise `primary`. `metadata` carries fields that don't fit the generic citation shape:

```json
{ "id": "MEF-a644d766ab", "type": "merchant_finding", "role": "weak_lead",
  "title": "Suppliers cancel late payments.",
  "target": { "type": "internal_route", "value": "/merchant-findings/MEF-a644d766ab" },
  "metadata": { "campaign_id": "MVC-…", "method": "interview", "segment_id": null,
               "strength_band": "single_signal", "support_count": 1, "contradiction_count": 0,
               "denominator": 1, "denominator_definition": "included participants in campaign MVC-…" } }
```

`metadata` never contains identity fields, participant/response ids, transcript paths, or raw response text — those never leave Merchant Voice's own read-only query layer in the first place.

**`evidence` citations with provenance (additive — Integration Phase 4).** When the answer's tool run loaded the evidence record itself (`get_evidence_record`), the citation carries a bounded provenance `metadata` object so clients can show where the evidence came from and how current it is without a second lookup. Every field is optional/nullable — a client must treat an absent field or `metadata: null` exactly like before Phase 4 (backward compatible):

```json
{ "id": "EV-2026-W28-001", "type": "evidence", "role": "weak_lead",
  "title": "Telr: multi-month fund holds…",
  "target": { "type": "internal_route", "value": "/evidence/EV-2026-W28-001" },
  "metadata": { "source_title": "Trustpilot — Telr", "publisher": "Trustpilot",
               "source_url": "https://trustpilot.com/review/www.telr.com",
               "publication_date": null, "retrieved_at": "2026-07-10",
               "last_verified_at": "2026-07-10", "access_label": "search-snippet",
               "excerpt": "\"PAYMENTS ARE SENT TO ISSUER BANK VERIFICATION\" — …",
               "freshness_status": "fresh",
               "freshness_reason": "Last verified 5 days ago." } }
```

Rules:

- `source_url` is either an absolute **http(s)** URL or `null`. It is never a `javascript:`/`data:`/`file:` URL, never a filesystem path, and never fabricated — an internal record with no external source keeps `source_url: null` and the client says so honestly.
- `freshness_status` ∈ `fresh | aging | stale | unknown` is a **deterministic** calculation over stored dates only (`shared/freshness.py` — reference-date priority `last_verified_at > retrieved_at > publication_date > date_of_evidence > created_at`; bands ≤90 days fresh, ≤180 aging, >180 stale, no date → unknown). It is never an LLM judgment and never implies the source was re-fetched.
- When an answer relies on stale evidence, the response's top-level `warnings` array carries one deduplicated entry per stale record (e.g. `"EV-2026-W28-001 was last verified 214 days ago — stale evidence; …"`) — never one per mention.
- `metadata` never contains prompts, traces, filesystem paths, or private identity data.

## GET /api/conversations/{id} — 200

`{schema_version, conversation_id, created_at, updated_at, context: {opportunity_id|null, segment_id|null}, message_count}`

## GET /api/conversations/{id}/messages — 200

`{schema_version, conversation_id, messages: [{message_id, role: "user"|"assistant", content, created_at, cited_ids: []}]}`

## DELETE /api/conversations/{id} — 200

`{schema_version, deleted: true, conversation_id}` — conversation row and all message rows removed from the local SQLite store. Repeat delete ⇒ 404.

## Error response (any endpoint)

```json
{ "schema_version": "1.0",
  "error": { "code": "not_found", "message": "…", "retryable": false } }
```

`error.code` enum → HTTP status: `invalid_request` 400 · `unauthorized` 401 · `not_found` 404 · `conversation_not_found` 404 (Phase 3 — `POST /api/chat` with a `conversation_id` that no longer exists, e.g. after a store reset; distinct from generic `not_found` so a client can safely drop the stale id and retry once as a fresh conversation) · `message_too_long` 413 · `rate_limited` 429 (`retryable: true`) · `provider_error` 502 (`retryable: true`) · `provider_timeout` 504 (`retryable: true`) · `internal` 500. Error messages are safe (no stack traces, paths, or secrets).

## Conversation lifecycle

1. `POST /api/chat` with `conversation_id: null` → server creates `conv_…`, stores the user + assistant messages, returns them with the answer.
2. Follow-ups reuse `conversation_id`; pronouns/references resolve from stored context (**explicit IDs in the newest message always win** over remembered context).
3. History is convenience context only — it is never treated as evidence and never written to the knowledge base.
4. `DELETE` ends the lifecycle; storage is a local gitignored SQLite file.

## Grounding & wording guarantees (what the UI can rely on)

- Scores, classifications, confidence values, assumption counts, evidence roles and citations are computed **deterministically from the existing engines/records** — the model writes prose only and cannot override those fields.
- Weak/lead evidence is labelled `weak_lead` and never presented as primary support; contradictory evidence is labelled and never dropped.
- The answer never claims a product was validated/selected or a build approved; promising-but-unvalidated answers include: *“No product or build decision has been made.”*
- Repository/code/implementation questions get a polite product-discovery redirect; state-changing requests (apply/approve/rollback/email/shell/file access) are refused — the backend has no such tools.
- Merchant Voice research questions are grounded only in **approved, published** findings (`merchant_finding` citations) — never unreviewed/rejected/suppressed/`needs_revalidation` content, never identity fields, never raw transcript text. A finding's `suggested_strength` is a Merchant Voice research signal, never authoritative Part A evidence, and is never blended into the response's own `confidence` field. A `concept_reaction` finding is never presented as proof that pain, frequency, or willingness to pay have been established.
- **`new_opportunity_analysis` (Integration Phase 2).** A genuinely new product/opportunity with no `OPP-` record. Selected deterministically when: the conversation is new (`conversation_id` was null), no explicit `OPP-/EV-/SEG-/ASM-/MVC-` id is present in the message, and no `opportunity_id`/`segment_id` is already selected via `context` or prior conversation state — any of those instead route to the existing deterministic intents unchanged. Retrieval reuses `search_product_knowledge` (now also covering competitor profiles and inflection points), `get_evidence_gaps`, `get_recent_changes`, and `get_approved_merchant_findings` — the same read-only tools used elsewhere, never a new write path. No numeric score, composite, or classification is ever computed or stated for a new idea (the scoring engine requires a real, committed scorecard, which a brand-new idea never has); if nothing relevant is found, `unknowns` says so explicitly rather than the model inventing supporting signal. `citations` are only ever built from what the tools actually returned — the model cannot add a citation for an id it merely mentions in prose.

## Example — normal fetch() from the UI

```js
const r = await fetch("http://127.0.0.1:8010/api/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ conversation_id: null, message: "Explain OPP-013 in simple terms." }),
});
const data = await r.json();   // shape above
```

## Example response (abridged, real values)

```json
{ "schema_version": "1.0",
  "conversation_id": "conv_a1b2c3", "message_id": "msg_d4e5f6",
  "answer_markdown": "OPP-013 (import payment + working-capital account) scores 55/85 … \n\n## Evidence used\n- EV-2026-W28-014 — Card rails… (primary)\n- VE-004 — importer validation experiment",
  "answer_type": "analysis",
  "confidence": { "level": "medium", "basis": "scorecard evidence_confidence=medium; cited evidence 3×Medium, 1×Low (lead)" },
  "citations": [ { "id": "OPP-013", "type": "opportunity", "title": "Import payment + working-capital account", "role": "primary", "target": {"type": "internal_route", "value": "/opportunity/OPP-013"} } ],
  "assumptions": ["8 of 17 scorecard factors remain assumption-based"],
  "unknowns": ["UAE-importer willingness to pay is unverified (EV-2026-W28-015)"],
  "recommended_next_actions": ["Run VE-004 before any product build decision."],
  "warnings": [],
  "safe_tool_trace": [] }
```

## Per-user conversation ownership (Phase R8b) — additive

`conversations.owner_user_id` (nullable, idempotent in-place migration).
The executive proxy validates the session cookie and forwards the identity
as an `X-Botim-User` header (client-supplied copies are never forwarded);
copilot-backend honors it ONLY when `COPILOT_TRUST_PROXY_USER=1` (the
single-container deploy, where the backend binds 127.0.0.1 and is reachable
only through the proxy). A conversation created with an identity belongs to
that user; another user's access — chat continuation, reads, delete — gets
the existing `conversation_not_found` / `not_found` shape (indistinguishable
from nonexistent). Legacy NULL-owner conversations stay accessible.
