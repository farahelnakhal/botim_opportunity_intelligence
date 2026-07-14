// @vitest-environment node
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

// Phase 1H — the audit did not reproduce a general dark-mode contrast bug.
// This is a focused, token-level regression guard (not a full visual/screenshot
// QA pass — see Phase 1H notes in the completion report) so a future edit to
// index.css can't silently break dark-theme text contrast.

const CSS_PATH = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "index.css");

function relLuminance(hex: string): number {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const [rl, gl, bl] = [r, g, b].map(lin);
  return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl;
}

function contrast(a: string, b: string): number {
  const la = relLuminance(a);
  const lb = relLuminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

function extractBlock(css: string, selector: string): Record<string, string> {
  const idx = css.indexOf(selector);
  if (idx === -1) throw new Error(`selector not found: ${selector}`);
  const start = css.indexOf("{", idx);
  const end = css.indexOf("}", start);
  const body = css.slice(start + 1, end);
  const vars: Record<string, string> = {};
  for (const m of body.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)) vars[m[1]] = m[2];
  return vars;
}

describe("dark-theme token contrast (Phase 1H — focused, not exhaustive)", () => {
  const css = readFileSync(CSS_PATH, "utf-8");
  const dark = extractBlock(css, '[data-theme="dark"]');

  it("body text on the app background meets WCAG AA (4.5:1) for normal text", () => {
    expect(contrast(dark["text"], dark["bg"])).toBeGreaterThanOrEqual(4.5);
  });

  it("body text on a raised surface meets WCAG AA (4.5:1) for normal text", () => {
    expect(contrast(dark["text"], dark["surface"])).toBeGreaterThanOrEqual(4.5);
  });

  it("secondary text on the app background meets WCAG AA (4.5:1) for normal text", () => {
    expect(contrast(dark["text-secondary"], dark["bg"])).toBeGreaterThanOrEqual(4.5);
  });

  it("the accent color on a surface is readable (>=3:1, used for links/buttons)", () => {
    expect(contrast(dark["accent"], dark["surface"])).toBeGreaterThanOrEqual(3);
  });

  it("warning and critical text remain distinguishable from the background (>=3:1)", () => {
    expect(contrast(dark["warning"], dark["bg"])).toBeGreaterThanOrEqual(3);
    expect(contrast(dark["critical"], dark["bg"])).toBeGreaterThanOrEqual(3);
  });
});
