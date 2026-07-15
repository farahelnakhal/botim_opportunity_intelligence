// Renders copilot-backend citations as clickable chips using the existing
// Phase 1 detail-drawer model (Drawer for opportunities, DetailDrawer for
// everything else already supported). A citation type with no supported
// detail view renders as a safe, non-clickable reference chip rather than
// crashing or guessing a navigation target (Phase 2K).
import { useApp } from "../store";
import type { Citation } from "../types";
import Icon from "./Icon";

const ASSUMPTION_ID = /^ASM-(OPP-\d{3})-(.+)$/;

const ROLE_LABEL: Record<string, string> = {
  primary: "primary", contextual: "context", contradictory: "contradicts",
  weak_lead: "weak lead", excluded: "excluded", concept_reaction: "concept reaction",
};

export default function Citations({ citations }: { citations: Citation[] }) {
  const { openDrawer, openDetail, overview } = useApp();
  if (!citations.length) return null;

  // Phase 4 — deterministic freshness for an evidence citation: prefer the
  // citation's own backend-computed metadata, fall back to the overview
  // read-model. Displayed only; never derived in the frontend.
  const evidenceFreshness = (c: Citation): { status?: string; reason?: string } => {
    const meta = (c.metadata ?? {}) as Record<string, unknown>;
    if (typeof meta.freshness_status === "string") {
      return { status: meta.freshness_status, reason: meta.freshness_reason as string | undefined };
    }
    const e = overview?.evidence.find((x) => x.ev_id === c.id);
    return { status: e?.freshness_status, reason: e?.freshness_reason };
  };

  return (
    <div className="citation-list">
      {citations.map((c) => {
        const roleLabel = ROLE_LABEL[c.role] || c.role;
        const label = `${c.id}${c.title ? ` — ${c.title}` : ""}`;

        if (c.type === "opportunity") {
          return (
            <button key={c.id} type="button" className="citation-chip clickable"
              onClick={() => openDrawer(c.id)} title={label}>
              <Icon name="folder" size={12} /> {c.id} <span className="citation-role">{roleLabel}</span>
            </button>
          );
        }
        if (c.type === "evidence") {
          const fresh = evidenceFreshness(c);
          const isStale = fresh.status === "stale";
          const staleTitle = isStale && fresh.reason ? ` — STALE: ${fresh.reason}` : "";
          return (
            <button key={c.id} type="button" className="citation-chip clickable"
              onClick={() => openDetail("evidence", c.id)} title={`${label}${staleTitle}`}>
              <Icon name="file" size={12} /> {c.id} <span className="citation-role">{roleLabel}</span>
              {isStale && <span className="citation-stale-flag" data-testid="citation-stale-flag">stale</span>}
            </button>
          );
        }
        if (c.type === "research_candidate") {
          // Phase R3 — an approved EXTERNAL web-research claim. Visually
          // distinct from repository evidence; the tooltip carries the claim
          // and its recorded sources. Traceability detail (claim → sources →
          // run) lives in the Research view.
          const meta = (c.metadata ?? {}) as {
            sources?: { url?: string; title?: string; freshness_status?: string }[];
          };
          const srcBits = (meta.sources ?? [])
            .map((s) => `${s.title || s.url || "source"}${s.freshness_status === "stale" ? " [stale]" : ""}`)
            .join("; ");
          const hasStale = (meta.sources ?? []).some((s) => s.freshness_status === "stale");
          return (
            <span key={c.id} className="citation-chip citation-external"
              title={`External research (candidate): ${c.title}${srcBits ? ` — sources: ${srcBits}` : ""}`}
              data-testid="citation-research-candidate">
              <Icon name="search" size={12} /> {c.id}
              <span className="citation-role">external research</span>
              {hasStale && <span className="citation-stale-flag" data-testid="citation-stale-flag">stale</span>}
            </span>
          );
        }
        if (c.type === "merchant_finding") {
          return (
            <button key={c.id} type="button" className="citation-chip clickable"
              onClick={() => openDetail("merchant_finding", c.id, c)} title={label}>
              <Icon name="users" size={12} /> {c.id} <span className="citation-role">{roleLabel}</span>
            </button>
          );
        }
        if (c.type === "assumption") {
          const m = ASSUMPTION_ID.exec(c.id);
          if (m) {
            return (
              <button key={c.id} type="button" className="citation-chip clickable"
                onClick={() => openDetail("assumption", `${m[1]}::${m[2]}`)} title={label}>
                <Icon name="alert" size={12} /> {c.id} <span className="citation-role">{roleLabel}</span>
              </button>
            );
          }
        }
        // segment, competitor, inflection, experiment, and any future/unknown
        // type: a safe, informative, non-clickable reference (Phase 2K).
        return (
          <span key={c.id} className="citation-chip" title={label}>
            {c.id} <span className="citation-role">{roleLabel}</span>
          </span>
        );
      })}
    </div>
  );
}
