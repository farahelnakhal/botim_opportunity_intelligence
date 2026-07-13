// Read-only API client for the BOTIM Opportunity Intelligence engines.
//
// Talks to the Python JSON API (executive-ui/api/server.py). When the API is
// unreachable — e.g. a static build with no server running — it falls back to a
// bundled snapshot of REAL engine output (seed.json), so the UI always renders
// truthful data and never fabricates. It performs no writes.

import seed from "../seed.json";
import type {
  ChatResponse,
  CommercialModel,
  Experiment,
  JournalPayload,
  MonitoringPayload,
  Opportunity,
  OverviewPayload,
} from "../types";

const S = seed as any;

let liveOk: boolean | null = null;

async function get<T>(path: string, fallback: () => T): Promise<T> {
  try {
    const res = await fetch(`/api${path}`, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    liveOk = true;
    return (await res.json()) as T;
  } catch {
    liveOk = false;
    return fallback();
  }
}

export function isLive(): boolean | null {
  return liveOk;
}

export const api = {
  overview: () => get<OverviewPayload>("/overview", () => S.overview),

  opportunity: async (id: string): Promise<Opportunity | undefined> => {
    const ov = await api.overview();
    return [...ov.opportunities, ...ov.archived].find((o) => o.id === id);
  },

  commercial: (id: string) =>
    get<CommercialModel | null>(`/commercial/${id}`, () => S.commercial[id] ?? null),

  experiments: () => get<Experiment[]>("/experiments", () => S.experiments),

  journal: () => get<JournalPayload>("/journal", () => S.journal),

  monitoring: () => get<MonitoringPayload>("/monitoring", () => S.monitoring),

  // Chat routing. The live server runs the deterministic router; offline we run
  // the same routing shape client-side against the seed so the demo still works.
  chat: (message: string) =>
    get<ChatResponse>(
      `/chat?q=${encodeURIComponent(message)}`,
      () => routeOffline(message),
    ),
};

// --- offline routing fallback (mirrors api/router.py at a high level) -------
function routeOffline(message: string): ChatResponse {
  const ov: OverviewPayload = S.overview;
  const low = message.toLowerCase();
  const banner = ov.meta.decision_banner;
  const oppMatch = message.match(/OPP-?(\d{1,3})/i);
  const oid = oppMatch ? `OPP-${String(parseInt(oppMatch[1], 10)).padStart(3, "0")}` : null;
  const find = (id: string) =>
    [...ov.opportunities, ...ov.archived].find((o) => o.id === id);

  const wrap = (intent: string, stages: string[], text: string, blocks: any[]): ChatResponse => ({
    intent,
    stages,
    text,
    blocks,
    decision_banner: banner,
  });

  if (/(brief|recommend|executive summary|should we build|decision)/.test(low)) {
    const t = (oid && find(oid)) || ov.opportunities[0];
    const blocks: any[] = [];
    if (t) {
      blocks.push({ type: "executive_summary", opportunity: t });
      if (t.brief_envelope) blocks.push({ type: "brief_envelope", data: t.brief_envelope });
      if (S.commercial[t.id]) blocks.push({ type: "commercial_model", data: S.commercial[t.id] });
    }
    blocks.push({ type: "banner", text: banner });
    return wrap("brief", ["Gathering evidence", "Scoring opportunity", "Running assumptions check", "Generating commercial model", "Preparing executive summary", "Finished"],
      "Here is the current executive read. It states a decision requested, not a decision made — no product has been validated or selected.", blocks);
  }
  if (/(commercial|revenue|cost|break-?even|roi|unit economics|margin|contribution)/.test(low)) {
    const id = oid || ov.opportunities[0]?.id;
    const comm = id ? S.commercial[id] : null;
    return wrap("commercial", ["Loading model inputs", "Running scenarios", "Computing break-even", "Preparing commercial model", "Finished"],
      comm ? `Illustrative unit economics for ${comm.name} across downside / base / upside. Planning scenarios, not a forecast.` : "No committed commercial model for that opportunity yet.",
      comm ? [{ type: "commercial_model", data: comm }] : [{ type: "empty", text: "No commercial model inputs committed." }]);
  }
  if (/(experiment|validation|hypothesis|\bve-)/.test(low)) {
    let exps: Experiment[] = S.experiments;
    if (oid) exps = exps.filter((e) => (e.linked_opportunity || "").toLowerCase().includes(oid.toLowerCase())) || exps;
    return wrap("experiments", ["Loading experiment specs", "Checking pre-committed thresholds", "Reading results", "Finished"],
      `${exps.length} validation experiment(s). Each has a pre-committed success and kill threshold.`,
      exps.map((e) => ({ type: "experiment", data: e })));
  }
  if (/(monitor|alert|signal|news|competitor|watch|what changed|what's new|whats new)/.test(low)) {
    const mon: MonitoringPayload = S.monitoring;
    const blocks = mon.alerts.length
      ? mon.alerts.slice(0, 12).map((a) => ({ type: "monitoring_alert", data: a }))
      : ov.feed.slice(0, 12).map((f) => ({ type: "feed_item", data: f }));
    return wrap("monitoring", ["Scanning signals", "Ranking by tier", "Preparing alerts", "Finished"],
      `${mon.events.length} signals this period, ${mon.alerts.length} raised as alerts.`, blocks);
  }
  if (/(journal|calibration|brier|prediction)/.test(low)) {
    const j: JournalPayload = S.journal;
    const blocks: any[] = [{ type: "calibration", data: j.calibration }];
    j.predictions.forEach((p) => blocks.push({ type: "decision_journal", data: p }));
    return wrap("journal", ["Loading predictions", "Computing calibration", "Scoring Brier", "Finished"],
      "Decision journal with calibration. Brier is over resolved, non-excluded predictions only.", blocks);
  }
  if (oid) {
    const t = find(oid);
    if (t) {
      const evIds = new Set(t.strongest_evidence.map((r) => r.ev_id));
      const ev = ov.evidence.filter((e) => evIds.has(e.ev_id)).slice(0, 4);
      return wrap("opportunity", ["Finding evidence", "Scoring opportunity", "Assembling scorecard", "Preparing summary", "Finished"],
        `${t.id} — ${t.name}. All 17 scoring dimensions are shown; the composite is reference only.`,
        [{ type: "opportunity", opportunity: t }, { type: "scorecard", opportunity: t }, ...ev.map((e) => ({ type: "evidence", data: e }))]);
    }
  }
  const blocks = ov.opportunities.map((o) => ({ type: "opportunity", opportunity: o }));
  blocks.push({ type: "banner", text: banner } as any);
  return wrap("portfolio", ["Loading portfolio", "Ranking opportunities", "Checking evidence strength", "Preparing summary", "Finished"],
    `${ov.opportunities.length} live opportunities ranked by raw score, plus ${ov.archived.length} archived. None has been selected for build.`, blocks);
}
