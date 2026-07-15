// Phase 4 — stale-evidence flags on chat citations. The flag is driven ONLY
// by deterministic backend metadata (citation metadata or the overview
// read-model) — never derived in the frontend.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { AppProvider, useApp } from "../store";
import type { AppState } from "../store";
import { overviewFixture } from "../test/fixtures";
import Citations from "./Citations";
import type { Citation } from "../types";

vi.mock("../lib/api", () => ({
  api: { overview: vi.fn(() => Promise.resolve(overviewFixture)) },
  isLive: () => true,
}));

let state: AppState;
function Harness({ citations }: { citations: Citation[] }) {
  const s = useApp();
  state = s;
  return <Citations citations={citations} />;
}

beforeEach(() => window.localStorage.clear());

async function mount(citations: Citation[]) {
  render(
    <AppProvider>
      <Harness citations={citations} />
    </AppProvider>,
  );
  await waitFor(() => expect(state.loading).toBe(false));
}

const target = (v: string) => ({ type: "internal_route", value: v });

describe("Citations stale-evidence flag (Phase 4)", () => {
  it("flags a citation whose backend metadata says stale, with the reason in the tooltip", async () => {
    await mount([{
      id: "EV-2026-W28-099", type: "evidence", title: "Old evidence", role: "primary",
      target: target("/evidence/EV-2026-W28-099"),
      metadata: { freshness_status: "stale", freshness_reason: "Last verified 214 days ago." },
    }]);
    expect(screen.getByTestId("citation-stale-flag")).toHaveTextContent("stale");
    expect(screen.getByRole("button", { name: /EV-2026-W28-099/ }))
      .toHaveAttribute("title", expect.stringContaining("Last verified 214 days ago."));
  });

  it("falls back to the overview read-model when the citation has no metadata", async () => {
    await mount([{
      id: "EV-2026-W28-002", type: "evidence", title: "Internal", role: "contextual",
      target: target("/evidence/EV-2026-W28-002"), metadata: null,
    }]);
    expect(screen.getByTestId("citation-stale-flag")).toBeInTheDocument();
  });

  it("shows no flag for fresh or unknown-freshness evidence", async () => {
    await mount([
      { id: "EV-2026-W28-001", type: "evidence", title: "Fresh", role: "primary",
        target: target("/evidence/EV-2026-W28-001"), metadata: null },
      { id: "EV-2026-W28-003", type: "evidence", title: "Unknown", role: "contextual",
        target: target("/evidence/EV-2026-W28-003"), metadata: null },
    ]);
    expect(screen.queryByTestId("citation-stale-flag")).not.toBeInTheDocument();
  });
});
