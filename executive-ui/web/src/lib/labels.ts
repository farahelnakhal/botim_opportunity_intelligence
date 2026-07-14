// Turn internal machine codes into plain language for a non-technical audience.
// The UI should read like a product, not a database: no OPP-010, EV-…, VE-…,
// SEG-…, IP-…, PRED-… on screen. Names replace codes; where a code has no
// human name we describe what it is ("evidence", "an experiment").

import type { Opportunity } from "../types";

export function nameMap(opps: Opportunity[]): Record<string, string> {
  const m: Record<string, string> = {};
  for (const o of opps) m[o.id] = o.name;
  return m;
}

function titleCase(s: string): string {
  return s.replace(/[-_]/g, " ").replace(/\s+/g, " ").trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// Replace embedded codes inside a free-text string with friendly language.
export function humanize(text: string | undefined | null, names: Record<string, string> = {}): string {
  if (!text) return text ?? "";
  return text
    .replace(/\bOPP-\d{3}\b/g, (m) => names[m] || "this opportunity")
    .replace(/\bSEG-[a-z0-9-]+/gi, (m) => titleCase(m.replace(/^SEG-/i, "")))
    .replace(/\bIP-\d{4}-\d{3}\b/g, "market inflection point")
    .replace(/\bVE-\d{3}\b/g, "a validation experiment")
    .replace(/\bEV-\d{4}-W\d{2}-\d{3}\b/g, "a customer-evidence record")
    .replace(/\bPRED-\d{3}\b/g, "a prediction")
    .replace(/\s{2,}/g, " ")
    .trim();
}

// A short, human label for a single reference token (used in "Affected" lists).
export function humanizeRef(ref: string, names: Record<string, string> = {}): string {
  if (/^OPP-\d{3}$/.test(ref)) return names[ref] || "an opportunity";
  if (/^SEG-/i.test(ref)) return titleCase(ref.replace(/^SEG-/i, "")) + " segment";
  if (/^IP-/.test(ref)) return "market inflection point";
  if (/^VE-/.test(ref)) return "validation experiment";
  if (/^EV-/.test(ref)) return "evidence record";
  if (/^PRED-/.test(ref)) return "prediction";
  return ref;
}

export function humanizeRefs(refs: string[] | undefined, names: Record<string, string> = {}): string {
  if (!refs || !refs.length) return "—";
  return refs.map((r) => humanizeRef(r, names)).join(", ");
}
