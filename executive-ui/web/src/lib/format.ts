// Presentation helpers. No business logic, no score computation.

const CLASS_TO_TAG: Record<string, string> = {
  strong: "strong",
  promising: "promising",
  weak: "weak",
  reject: "reject",
  unscored: "neutral",
};

const CLASS_LABEL: Record<string, string> = {
  strong: "Strong opportunity",
  promising: "Promising",
  weak: "Needs validation",
  reject: "Archived / rejected",
  unscored: "Unscored",
};

export function tagClass(classification: string): string {
  return CLASS_TO_TAG[classification] ?? "neutral";
}

export function tagLabel(classification: string): string {
  return CLASS_LABEL[classification] ?? classification;
}

// Percentage for the score ring: raw / raw_max. We NEVER invent a 0–100 score;
// this is purely a visual proportion of the engine's own raw/max.
export function scorePct(raw: number | null, max: number): number {
  if (raw == null || !max) return 0;
  return Math.round((raw / max) * 100);
}

export function confidenceLabel(c: string): string {
  if (!c || c === "—") return "Unknown";
  return c.charAt(0).toUpperCase() + c.slice(1);
}

export function money(n: number, currency = "AED"): string {
  return `${currency} ${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export function statusFromClassification(c: string): "active" | "review" | "reject" {
  if (c === "strong" || c === "promising") return "active";
  if (c === "reject") return "reject";
  return "review";
}

// Ring geometry (r=27 in the 64×64 SVG from the mockup).
export const RING_CIRCUMFERENCE = 2 * Math.PI * 27;
export function ringOffset(pct: number): number {
  return RING_CIRCUMFERENCE - (RING_CIRCUMFERENCE * pct) / 100;
}

export function humanFactorKey(key: string): string {
  return key
    .replace(/_7wk$/, " (7wk)")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}
