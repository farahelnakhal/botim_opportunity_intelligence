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
  const { openDrawer, openDetail } = useApp();
  if (!citations.length) return null;

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
          return (
            <button key={c.id} type="button" className="citation-chip clickable"
              onClick={() => openDetail("evidence", c.id)} title={label}>
              <Icon name="file" size={12} /> {c.id} <span className="citation-role">{roleLabel}</span>
            </button>
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
