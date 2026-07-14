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
| `context` | optional | yes | object | optional hints: `opportunity_id`, `segment_id` (validated IDs only) |

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
| `answer_type` | required | no | enum: `analysis, brief, comparison, evidence, challenge, assumptions, research_recommendation, research_request_draft, change_summary, merchant_feedback` (`merchant_feedback` added for Merchant Voice research questions — additive, backward compatible, `schema_version` unchanged) |
| `confidence` | required | no | `{level: "high"|"medium"|"low"|"mixed", basis: string}` — derived deterministically from records/engines, never model-invented |
| `citations` | required | no | array of citation objects (below); may be empty |
| `assumptions` | required | no | string[] — working assumptions relevant to the answer |
| `unknowns` | required | no | string[] — explicit gaps; never silently filled |
| `recommended_next_actions` | required | no | string[] |
| `warnings` | required | no | string[] (e.g. wording-guard notes, weak-evidence flags) |
| `safe_tool_trace` | required | no | string[] — **empty `[]` in normal production responses**; populated with short operational one-liners (e.g. `"loaded OPP-013"`) only when the server runs with `COPILOT_DEBUG_TRACE=1`. Never contains prompts, reasoning, provider payloads, file paths, secrets, or full tool results |
| `draft` | optional | yes | object — present only for draft answer types; ephemeral (never persisted server-side beyond conversation storage) |

Citation object:

```json
{ "id": "EV-2026-W28-014",
  "type": "evidence",             // enum: evidence | opportunity | segment | inflection | experiment | assumption | merchant_finding
  "title": "Card rails appear unsuitable for many core supplier-payment transactions…",
  "role": "primary",              // enum: primary | contextual | contradictory | weak_lead | excluded | concept_reaction
  "target": { "type": "internal_route", "value": "/evidence/EV-2026-W28-014" },
  "metadata": null }              // additive field; non-null only for merchant_finding citations — see below
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

`error.code` enum → HTTP status: `invalid_request` 400 · `unauthorized` 401 · `not_found` 404 · `message_too_long` 413 · `rate_limited` 429 (`retryable: true`) · `provider_error` 502 (`retryable: true`) · `provider_timeout` 504 (`retryable: true`) · `internal` 500. Error messages are safe (no stack traces, paths, or secrets).

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
