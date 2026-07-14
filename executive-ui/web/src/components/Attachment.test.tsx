import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider, useApp } from "../store";
import type { AppState } from "../store";
import { overviewFixture } from "../test/fixtures";
import Home from "./Home";
import Chat from "./Chat";

vi.mock("../lib/api", () => ({
  api: {
    overview: vi.fn(() => Promise.resolve(overviewFixture)),
    analyze: vi.fn(),
    chat: vi.fn(),
  },
  isLive: () => true,
}));

let state: AppState;
function Harness({ children }: { children: React.ReactNode }) {
  const s = useApp();
  state = s;
  return <>{children}</>;
}

beforeEach(() => window.localStorage.clear());

async function mount(children: React.ReactNode) {
  render(
    <AppProvider>
      <Harness>{children}</Harness>
    </AppProvider>,
  );
  await waitFor(() => expect(state.loading).toBe(false));
}

// Phase 1I — the attachment control must never imply the engine reads file
// contents: it only ever notes file *names*, and must say so up front.
describe("File attachment honesty (Phase 1I)", () => {
  it("Home's attach control discloses local-only, not-yet-analyzed behavior", async () => {
    await mount(<Home />);
    const btn = screen.getByTitle(/not uploaded to or read by the analysis engine/i);
    expect(btn).toBeInTheDocument();
  });

  it("Chat's attach control discloses local-only, not-yet-analyzed behavior", async () => {
    await mount(<Chat projectId="OPP-001" />);
    const btn = screen.getByTitle(/not uploaded to or read by the analysis engine/i);
    expect(btn).toBeInTheDocument();
  });

  it("attaching a file in Home inserts an honest note, not a claim of analysis", async () => {
    await mount(<Home />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["hello"], "notes.pdf", { type: "application/pdf" });
    const user = userEvent.setup();
    await user.upload(input, file);
    const textarea = screen.getByPlaceholderText(/Invoice financing for UAE logistics SMEs/i) as HTMLTextAreaElement;
    expect(textarea.value).toMatch(/file names noted, not uploaded or analyzed/);
    expect(textarea.value).not.toMatch(/^\[attached:/);
  });
});
