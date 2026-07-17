// Types mirror the read-only Python API (executive-ui/api/serialize.py).
// The UI never invents these values; it renders engine truth.

export interface Factor {
  key: string;
  score: number;
  assumption: boolean;
  basis: string;
  evidence_ids: string[];
}

// Deterministic freshness bands — computed ONLY by the backend
// (shared/freshness.py, single home for the thresholds); the UI displays
// the status, it never re-derives one.
export type FreshnessStatus = "fresh" | "aging" | "stale" | "unknown";

export interface EvidenceRef {
  ev_id: string;
  resolved: boolean;
  source_type: string;
  evidence_class: string;
  strength: number | string;
  confidence: string;
  status: string;
  segment: string;
  title: string;
  role: string;
  weak: boolean;
  // --- provenance (Phase 4; all optional so legacy payloads/seed still work,
  // null/undefined = not recorded, never invented) ---
  source_title?: string | null;
  source_url?: string | null; // backend emits http(s) only; UI re-validates before rendering
  publisher?: string | null;
  publication_date?: string | null;
  date_of_evidence?: string | null;
  retrieved_at?: string | null;
  created_at?: string | null;
  last_verified_at?: string | null;
  excerpt?: string | null;
  access_label?: string | null;
  contradictory_evidence?: string | null;
  freshness_status?: FreshnessStatus;
  freshness_reference_date?: string | null;
  freshness_age_days?: number | null;
  freshness_reason?: string;
  linked_opportunity_ids?: string[];
  linked_assumption_ids?: string[]; // "OPP-nnn::factor_key"
}

export interface Assumption {
  opportunity_id: string;
  factor_key: string;
  text: string;
  status: string;
  evidence_ids: string[];
  sensitivity: string;
  validation_method: string;
  owner: string;
  decision_importance: string;
  source: string;
}

export interface Opportunity {
  id: string;
  name: string;
  raw_score: number | null;
  raw_max: number;
  composite: number | null;
  classification: string;
  classification_label: string;
  confidence: string;
  assumption_count: number;
  factors: Factor[];
  critical_flags: string[];
  segment: string;
  jtbd: string;
  hypothesis: string;
  strongest_evidence: EvidenceRef[];
  contradictory_evidence: string;
  rejection_conditions: string;
  validation_plan: string;
  score_history: { date: string; subject: string }[];
  latest_change: string;
  latest_alert: string;
  next_action: string;
  profile_path: string;
  is_archived: boolean;
  impact_history: Record<string, unknown>[];
  brief_envelope: Record<string, any> | null;
  generated?: boolean; // true = an on-demand AI analysis, not a committed KB opportunity
  engine?: "claude" | "scaffold" | "copilot";
  // Phase 5/6 — explicit source type; never merged indistinguishably:
  // "user" = persisted user opportunity, "demo" = committed demo corpus,
  // "committed_reference" = committed reference record, absent = legacy.
  source?: "user" | "demo" | "committed_reference";
  // Phase 6 — true for a fresh analysis that has NOT been saved to the
  // backend yet (browser-local only until "Save opportunity").
  unsaved?: boolean;
}

// --- Phase 6: persisted user-created opportunity drafts -------------------- //
export type UserOpportunityStatus = "draft" | "saved" | "archived";

export interface UserOpportunity {
  id: string; // UOPP-…
  title: string;
  status: UserOpportunityStatus;
  product_definition: string | null;
  problem_statement: string | null;
  target_segment: string | null;
  customer_description: string | null;
  value_proposition: string | null;
  assumptions: string[];
  risks: string[];
  unknowns: string[];
  next_actions: string[];
  source_conversation_id: string | null;
  created_from_analysis: boolean;
  monitoring_enabled: boolean;
  version: number;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  source: "user";
}

// --- Phase 7: monitoring configuration for a user opportunity -------------- //
export type MonitoringConfigStatus =
  | "not_configured" | "active" | "paused" | "error" | "never_run";
export type MonitoringCadence = "manual" | "daily" | "weekly" | "monthly";

export interface UserMonitoringConfig {
  opportunity_id: string;
  status: MonitoringConfigStatus;
  enabled: boolean;
  id?: string;
  cadence?: MonitoringCadence;
  topics?: string[];
  keywords?: string[];
  entities?: string[];
  source_categories?: string[];
  preferred_domains?: string[];
  excluded_domains?: string[];
  geographic_scope?: string | null;
  language?: string | null;
  notes?: string | null;
  last_error?: string | null;
  consecutive_failure_count?: number;
  last_run_at?: string | null;
  next_run_at?: string | null;
  created_at?: string;
  updated_at?: string;
  suggested_topics?: string[]; // present only while not_configured
  opportunity_title?: string;  // present in the monitoring-overview list
}

// Phase R4a — a monitoring event: exactly "a new, non-duplicate source
// recorded by a manual monitoring run", grounded in an RSRC- research source.
export interface UserMonitoringEvent {
  id: string; // MEVT-<12 hex>
  opportunity_id: string;
  config_id: string;
  research_run_id: string;
  source_id: string;
  title: string | null;
  canonical_url: string;
  domain: string;
  published_at: string | null;
  detected_at: string;
}

export interface UserMonitoringRunResult {
  run_id: string;
  run_status: "complete" | "partial" | "failed";
  events_created: number;
  new_events: UserMonitoringEvent[];
  note: string;
  config?: UserMonitoringConfig;
}

// Phase 6 — web-report read model for a user opportunity (record_type
// distinguishes it from the committed BriefPayload; nothing is fabricated).
export interface UserBriefPayload {
  record_type: "user_opportunity";
  opportunity_id: string;
  title: string;
  generated_at: string;
  status: UserOpportunityStatus;
  is_archived: boolean;
  classification: "unscored";
  classification_label: string;
  product_definition: string | null;
  problem_statement: string | null;
  target_segment: string | null;
  customer_description: string | null;
  value_proposition: string | null;
  assumptions: string[];
  risks: string[];
  unknowns: string[];
  next_actions: string[];
  monitoring: UserMonitoringConfig;
  source_conversation_id: string | null;
  created_from_analysis: boolean;
  created_at: string;
  updated_at: string;
  version: number;
  decision_banner: string;
}

export interface FeedItem {
  id: string;
  kind: string;
  tier: string;
  title: string;
  detected_at: string;
  detail: string;
  before_after: { before: string; after: string } | null;
}

export interface Brief {
  opportunity_id: string;
  exists: boolean;
  path: string;
  body: string;
}

// Phase 5 — the backend is the source of truth for the application data mode
// (BOTIM_APP_MODE); the frontend only displays what it reports.
export type AppMode = "normal" | "demo" | "test";

export interface OverviewPayload {
  meta: {
    generated_note: string;
    decision_banner: string;
    impact_available: boolean;
    counts: Record<string, number>;
    app_mode?: AppMode; // absent on legacy payloads → treated as unknown
  };
  opportunities: Opportunity[];
  archived: Opportunity[];
  evidence: EvidenceRef[];
  assumptions: Assumption[];
  feed: FeedItem[];
  briefs: Brief[];
  impact_proposals: unknown[];
}

export interface CommercialCase {
  case: string;
  total_revenue: number;
  financing_revenue: number;
  payment_revenue: number;
  acquiring_revenue: number;
  total_cost: number;
  cost_of_capital: number;
  expected_credit_loss: number;
  contribution: number;
  contribution_pct: number;
  portfolio_contribution: number;
  breakeven_merchants: number | null;
  active_merchants: number;
  warnings: string[];
}

export interface CommercialModel {
  opportunity_id: string;
  name: string;
  currency: string;
  source: string;
  cases: Record<string, CommercialCase>;
  decision_banner: string;
  note: string;
}

export interface Experiment {
  id: string;
  title: string;
  hypothesis: string;
  success_threshold: string;
  kill_threshold: string;
  method: string;
  linked_opportunity: string;
  duration: string;
  decision_informed: string;
  status: string;
  result: Record<string, any> | null;
  spec_issues: string[];
  source: string;
}

export interface Prediction {
  id: string;
  statement: string;
  p: number;
  made: string;
  resolve_by: string;
  outcome: boolean | null;
  resolved_on: string | null;
  resolution_note: string;
  rationale: string;
  links: string[];
  brier: number | null;
  excluded_from_calibration: boolean;
}

export interface JournalPayload {
  predictions: Prediction[];
  calibration: {
    brier: number | null;
    n_resolved: number;
    n_open: number;
    n_overdue: number;
    buckets: { range: string; n: number; mean_p: number | null; observed: number | null }[];
  } | null;
  note?: string;
}

// Phase 4 — monitoring event shape (mirrors the monitoring engine's event
// schema; required fields per intelligence-monitoring events.py, optional
// fields preserved end-to-end instead of being dropped).
export interface MonitoringEvent {
  id: string;
  entity: string;
  detected_at: string;
  adapter: string; // "kb-watcher" = internal knowledge-base change
  signal_type: string;
  fingerprint?: string;
  title: string;
  scores: Record<string, number>;
  tier: string;
  status: string;
  facts?: Record<string, unknown> | unknown[];
  kb_links?: string[];
  thread_id?: string;
  dedup_of?: string;
  details?: Record<string, unknown>;
  score_note?: string;
  summary_ref?: string | null;
  [key: string]: unknown;
}

// Phase 4 — current-state monitoring summary. Computed by the backend from
// committed artefacts only; null = the backend cannot calculate it.
export interface MonitoringSummaryState {
  status: "active" | "no-recent-updates" | "no-events" | "never-run" | "unavailable";
  status_note: string;
  last_checked: string | null;
  latest_event_at: string | null;
  event_count: number | null;
  open_alert_count: number | null;
  unresolved_warning_count: number | null;
  monitored_entity_count: number | null;
  external_source_count: number | null;
  internal_only: boolean | null;
}

export interface MonitoringPayload {
  events: MonitoringEvent[];
  alerts: Record<string, any>[];
  summaries: { id: string; available: boolean; flags?: Record<string, unknown> | null }[];
  summary_state?: MonitoringSummaryState | null;
  // Phase 7 — user monitoring configurations (always present when the
  // backend has the user store; honest note that no runner exists yet)
  user_monitoring?: { configs: UserMonitoringConfig[]; note: string } | null;
}

// Phase 4 — GET /executive-api/brief/{opportunity_id} (web report read model)
export interface BriefPayload {
  record_type?: "committed_reference"; // absent on the wire; discriminates from UserBriefPayload
  opportunity_id: string;
  title: string;
  generated_at: string;
  classification: string;
  classification_label: string;
  is_archived: boolean;
  segment: string;
  jtbd: string;
  hypothesis: string;
  confidence: string;
  score_summary: {
    raw_score: number | null;
    raw_max: number;
    composite: number | null;
    assumption_count: number;
    critical_flags: string[];
  };
  brief_envelope: Record<string, any> | null;
  brief_markdown: string | null;
  evidence: EvidenceRef[];
  contradictory_evidence: string;
  assumptions: Assumption[];
  predictions: Prediction[];
  monitoring: { state: MonitoringSummaryState | null; events: MonitoringEvent[] };
  merchant_voice: { available: boolean; findings: Record<string, unknown>[]; note: string };
  risks: string[];
  unknowns: string[];
  recommended_next_actions: string[];
  sources: {
    source_title: string | null;
    publisher: string | null;
    source_url: string | null;
    retrieved_at: string | null;
    access_label: string | null;
    evidence_ids: string[];
  }[];
  decision_banner: string;
}

// Chat routing
export type BlockType =
  | "opportunity"
  | "scorecard"
  | "executive_summary"
  | "brief_envelope"
  | "commercial_model"
  | "experiment"
  | "monitoring_alert"
  | "feed_item"
  | "decision_journal"
  | "calibration"
  | "evidence"
  | "research_plan"
  | "banner"
  | "empty";

export interface ChatBlock {
  type: BlockType;
  opportunity?: Opportunity;
  data?: any;
  text?: string;
}

export interface ChatResponse {
  intent: string;
  stages: string[];
  text: string;
  blocks: ChatBlock[];
  decision_banner: string;
  generated_opportunity?: Opportunity | null;
}

// --- copilot-backend conversation contract (shared/contracts/conversation-api.schema.md) ---
// Additive citation types beyond what copilot-backend emits today
// (monitoring_update, knowledge_source) are included so the frontend renders
// them safely as non-clickable references if a future backend change adds them,
// per Phase 2K ("unsupported citation types render safely, never crash").
export type CitationType =
  | "opportunity" | "evidence" | "segment" | "inflection" | "experiment"
  | "assumption" | "merchant_finding" | "competitor"
  | "monitoring_update" | "knowledge_source"
  | "research_candidate"; // Phase R3 — approved external web-research claim

export type CitationRole =
  | "primary" | "contextual" | "contradictory" | "weak_lead" | "excluded"
  | "concept_reaction"
  | "external_research"; // Phase R3

// --- research platform (shared/contracts/research.schema.md, Phases R1-R3) ---
export type ResearchRunStatus = "pending" | "running" | "partial" | "complete" | "failed";
export type ResearchCandidateStatus = "pending_review" | "approved" | "rejected";

export interface ResearchRunSummary {
  id: string;
  title: string;
  objective: string | null;
  objectives: string[];
  profile: string | null;
  opportunity_ref: string | null;
  status: ResearchRunStatus;
  error: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  counts?: { queries: number; sources: number; candidates: number };
}

export interface ResearchQuery {
  id: string;
  run_id: string;
  objective: string | null;
  query_text: string;
  provider: string | null;
  status: "pending" | "executed" | "failed";
  error: string | null;
  result_count: number | null;
  created_at: string;
  executed_at: string | null;
}

export interface ResearchSource {
  id: string;
  run_id: string;
  query_id: string | null;
  canonical_url: string;
  domain: string;
  title: string | null;
  publisher: string | null;
  author: string | null;
  published_at: string | null;
  retrieved_at: string | null;
  language: string | null;
  excerpt: string | null;
  content_hash: string | null;
  duplicate_of: string | null;
  quality_signals: Record<string, string | number | boolean>;
  created_at: string;
  // computed deterministically server-side from the stored publication date
  freshness_status?: "fresh" | "aging" | "stale" | "unknown";
  freshness_reference_date?: string | null;
  freshness_age_days?: number | null;
  freshness_reason?: string;
  // Phase R4b — latest re-check (append-only history; the source row itself
  // is never mutated); null/absent = never revalidated
  last_revalidation?: SourceRevalidation | null;
}

export interface SourceRevalidation {
  id: string; // RREV-<12 hex>
  source_id: string;
  outcome: "unchanged" | "changed" | "unreachable";
  http_status: number | null;
  new_content_hash: string | null;
  note: string | null;
  checked_at: string;
}

export interface ResearchCandidate {
  id: string;
  run_id: string;
  claim: string;
  source_ids: string[];
  status: ResearchCandidateStatus;
  review_note: string | null;
  contradicts: string | null;
  created_at: string;
  updated_at: string;
  // present on cross-run listings (review queue)
  run_title?: string;
  run_status?: ResearchRunStatus;
  opportunity_ref?: string | null;
  // Phase R4b — worst latest revalidation outcome among cited sources
  // ("ok" also covers never-revalidated); computed server-side on run detail
  source_health?: "ok" | "changed" | "unreachable";
}

export interface ResearchRun extends ResearchRunSummary {
  queries?: ResearchQuery[];
  sources?: ResearchSource[];
  candidate_evidence?: ResearchCandidate[];
  // present on the response of POST /research/runs/{id}/revalidate
  revalidation_summary?: { run_id: string; checked: number; skipped: number;
    unchanged: number; changed: number; unreachable: number };
}

export interface Citation {
  id: string;
  type: CitationType;
  title: string;
  role: CitationRole;
  target: { type: string; value: string };
  metadata: Record<string, unknown> | null;
}

export interface CopilotConfidence {
  level: "high" | "medium" | "low" | "mixed";
  basis: string;
}

// Normalized (camelCase) shape the frontend works with — see
// lib/copilotApi.ts for the adapter from the wire (snake_case) response.
export interface CopilotChatResult {
  conversationId: string;
  messageId: string | null;
  answerMarkdown: string;
  answerType: string;
  confidence: CopilotConfidence | null;
  citations: Citation[];
  assumptions: string[];
  unknowns: string[];
  recommendedNextActions: string[];
  warnings: string[];
  // true when copilot-backend could not be reached / errored. Never silently
  // replaced by generate.py or seed data — the frontend must render an honest
  // unavailable state instead (Phase 2L/2J).
  unavailable: boolean;
  unavailableReason?: string;
  // Phase 3 — true when this result came from the one-shot stale-conversation
  // retry (the original conversation_id no longer existed; copilotApi already
  // retried once as a fresh conversation). Tells the caller to overwrite its
  // stored conversation id for this chat even though one was already on file.
  staleConversationRecovered?: boolean;
  // Phase 3 — "deterministic_demo" (MockProvider) | "live_model" (Anthropic).
  // Absent is safe/backward-compatible (treated as unknown, no badge shown).
  runtimeMode?: "deterministic_demo" | "live_model";
}

/* ---------------- Analysis workspace (Phase R5, PR4-UI) ---------------- */
// shared/contracts/workspace.schema.md — everything a workspace contains is
// machine-generated PRELIMINARY analysis; the UI must always badge it as
// such and show gaps honestly.

export type WorkspaceTrigger =
  | "first_analysis" | "manual_refresh" | "meaningful_change" | "stale" | "monitoring";

export interface WorkspaceKbEvidence {
  id: string;
  title: string;
  segment: string | null;
  status: string | null;
  evidence_confidence: string | null;
  match: number;
}

export interface WorkspacePreliminaryScore {
  preliminary: boolean;
  engine: string;
  composite: number;
  assumption_count: number;
  assumption_capped: boolean;
  max_classification: string;
  classification: string;
  confidence: string;
  basis_note?: string;
  inputs_found?: { kb_evidence_records: number; accepted_candidate_claims: number };
}

export interface WorkspaceClaim {
  id: string;
  claim: string;
  status: ResearchCandidateStatus;
  origin: "human" | "extracted" | null;
  source_ids: string[];
}

export interface WorkspaceVersionSummary {
  id: string;
  opportunity_id: string;
  version: number;
  status: "running" | "complete" | "failed";
  trigger: WorkspaceTrigger;
  question: string | null;
  error: string | null;
  research_run_id: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface WorkspaceDocumentEvidence {
  document_id: string;
  filename: string;
  chunk_seq: number;
  match: number;
  excerpt: string;
}

export interface WorkspaceVersion extends WorkspaceVersionSummary {
  kb_evidence: WorkspaceKbEvidence[];
  document_evidence?: WorkspaceDocumentEvidence[];
  claim_ids: string[];
  preliminary_score: WorkspacePreliminaryScore | null;
  gaps: string[];
  provenance: Record<string, unknown> | null;
  // enrichment from the GET/refresh view
  is_stale?: boolean;
  claims?: WorkspaceClaim[];
}

export interface WorkspaceDiff {
  older_id: string;
  newer_id: string;
  composite_before: number | null;
  composite_after: number | null;
  composite_delta: number | null;
  new_claim_ids: string[];
  removed_claim_ids: string[];
  new_gaps: string[];
  resolved_gaps: string[];
}
