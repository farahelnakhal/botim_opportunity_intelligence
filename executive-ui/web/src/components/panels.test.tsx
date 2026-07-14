import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider, useApp } from "../store";
import type { AppState } from "../store";
import { overviewFixture } from "../test/fixtures";
import { KnowledgePanel, SourcesPanel } from "./panels";

vi.mock("../lib/api", () => ({
  api: { overview: vi.fn(() => Promise.resolve(overviewFixture)) },
  isLive: () => true,
}));

let state: AppState;
function Harness({ children }: { children: React.ReactNode }) {
  const s = useApp();
  state = s;
  return <>{children}</>;
}

async function mountWith(children: React.ReactNode) {
  render(
    <AppProvider>
      <Harness>{children}</Harness>
    </AppProvider>,
  );
  await waitFor(() => expect(state.loading).toBe(false));
}

beforeEach(() => window.localStorage.clear());

describe("Knowledge Base evidence clickability (Phase 1C/1D)", () => {
  it("clicking an evidence row opens its detail", async () => {
    await mountWith(<KnowledgePanel />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Merchants report slow settlement/ }));
    expect(state.detailTarget).toEqual({ type: "evidence", id: "EV-2026-W28-001" });
  });

  it("evidence rows are keyboard-activatable (Enter)", async () => {
    await mountWith(<KnowledgePanel />);
    const row = screen.getByRole("button", { name: /Merchants report slow settlement/ });
    row.focus();
    const user = userEvent.setup();
    await user.keyboard("{Enter}");
    expect(state.detailTarget).toEqual({ type: "evidence", id: "EV-2026-W28-001" });
  });
});

describe("Sources clickability (Phase 1C)", () => {
  it("clicking a source row opens its evidence detail", async () => {
    const opp = overviewFixture.opportunities[0];
    const oppWithFactor = {
      ...opp,
      factors: [{ key: "willingness_to_pay", score: 3, assumption: true, basis: "—", evidence_ids: ["EV-2026-W28-001"] }],
    };
    await mountWith(<SourcesPanel opp={oppWithFactor} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Merchants report slow settlement/ }));
    expect(state.detailTarget).toEqual({ type: "evidence", id: "EV-2026-W28-001" });
  });
});
