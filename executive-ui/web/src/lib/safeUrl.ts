// Frontend half of the source-URL policy (Phase 4) — defense in depth on
// top of shared/source_urls.py. Only absolute http(s) URLs are ever
// rendered as a clickable external link; javascript:, data:, file:,
// vbscript:, scheme-relative, local paths, and malformed values are
// rejected, and callers must fall back to honest "no external source" text.
export function safeExternalUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const candidate = value.trim();
  if (!candidate || /\s/.test(candidate) || candidate.includes("\\")) return null;
  let parsed: URL;
  try {
    parsed = new URL(candidate); // relative/scheme-less values throw → rejected
  } catch {
    return null;
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
  if (!parsed.hostname.includes(".")) return null; // no localhost / file-ish hosts
  return candidate;
}
