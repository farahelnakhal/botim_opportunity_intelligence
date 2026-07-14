import { describe, it, expect } from "vitest";
import seed from "../seed.json";

// Phase 1G — the bundled offline-seed snapshot is real user-visible content
// (the app renders it directly whenever the live API is unreachable), so it
// must never carry internal QA/developer-only language. Mirrors the Python
// guard in executive-ui/api/tests/test_no_internal_wording.py.
const BANNED_PHRASES = ["as pre-committed in the test case", "test case", "fixme", "debug only"];

function walk(obj: unknown, hits: string[]) {
  if (typeof obj === "string") {
    const low = obj.toLowerCase();
    for (const phrase of BANNED_PHRASES) {
      if (low.includes(phrase)) hits.push(`"${phrase}" in: ${obj.slice(0, 160)}`);
    }
  } else if (Array.isArray(obj)) {
    obj.forEach((v) => walk(v, hits));
  } else if (obj && typeof obj === "object") {
    Object.values(obj as Record<string, unknown>).forEach((v) => walk(v, hits));
  }
}

describe("no internal QA wording in the bundled seed (Phase 1G)", () => {
  it("seed.json contains no internal test-case/debug language", () => {
    const hits: string[] = [];
    walk(seed, hits);
    expect(hits).toEqual([]);
  });
});
