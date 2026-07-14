// Real client-side actions for the UI's buttons — export, share, copy.
// Everything here works offline in the browser; nothing pretends to reach a
// service we don't have (no fake "email sent", no fake integrations).

import type { Opportunity } from "../types";
import { humanize } from "./labels";
import { tagLabel, humanFactorKey } from "./format";

export function downloadText(filename: string, content: string, mime = "text/markdown") {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Fallback for browsers/contexts without the async clipboard API.
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch {
      return false;
    }
  }
}

function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "opportunity";
}

// A readable Markdown summary of an opportunity — used by Export and Share.
export function opportunityMarkdown(opp: Opportunity): string {
  const lines: string[] = [];
  lines.push(`# ${opp.name}`);
  lines.push("");
  lines.push(`**Classification:** ${tagLabel(opp.classification)}  `);
  lines.push(`**Confidence:** ${opp.confidence}  `);
  if (opp.raw_score != null) lines.push(`**Score:** ${opp.raw_score}/${opp.raw_max} (composite ${opp.composite})  `);
  lines.push(`**Unresolved assumptions:** ${opp.assumption_count}  `);
  if (opp.segment && opp.segment !== "—") lines.push(`**Segment:** ${humanize(opp.segment)}  `);
  lines.push("");
  if (opp.generated) lines.push("> AI-generated, unvalidated hypothesis — not a committed opportunity.\n");
  if (opp.hypothesis && opp.hypothesis !== "—") {
    lines.push("## Summary");
    lines.push(humanize(opp.hypothesis));
    lines.push("");
  }
  if (opp.next_action && opp.next_action !== "—") {
    lines.push("## Recommended next action");
    lines.push(humanize(opp.next_action));
    lines.push("");
  }
  if (opp.factors.length) {
    lines.push("## Scorecard (17 dimensions)");
    lines.push("");
    lines.push("| Dimension | Score | Basis |");
    lines.push("|---|---|---|");
    for (const f of opp.factors) {
      const basis = (f.basis || "").replace(/\|/g, "\\|").slice(0, 120);
      lines.push(`| ${humanFactorKey(f.key)}${f.assumption ? " (assumption)" : ""} | ${f.score}/5 | ${basis} |`);
    }
    lines.push("");
  }
  lines.push("---");
  lines.push("_No product or build decision has been made._");
  return lines.join("\n");
}

export function opportunityFilename(opp: Opportunity): string {
  return `${slug(opp.name)}.md`;
}
