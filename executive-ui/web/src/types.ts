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
}
