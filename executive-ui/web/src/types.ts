// Types mirror the read-only Python API (executive-ui/api/serialize.py).
// The UI never invents these values; it renders engine truth.

export interface Factor {
  key: string;
  score: number;
  assumption: boolean;
  basis: string;
  evidence_ids: string[];
}

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

export interface OverviewPayload {
  meta: {
    generated_note: string;
    decision_banner: string;
    impact_available: boolean;
    counts: Record<string, number>;
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

export interface MonitoringPayload {
  events: Record<string, any>[];
  alerts: Record<string, any>[];
  summaries: { id: string; text: string }[];
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
  | "monitoring_update" | "knowledge_source";

export type CitationRole = "primary" | "contextual" | "contradictory" | "weak_lead" | "excluded" | "concept_reaction";

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
