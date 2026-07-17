import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UserDocumentsPanel from "./UserDocumentsPanel";
import type { UserDocument } from "../lib/documentsApi";

const OPP = "UOPP-aaaaaaaaaaa1";

const DOC: UserDocument = {
  id: "DOC-aaaaaaaaaaa1", opportunity_id: OPP, owner_user_id: null,
  filename: "internal-study.txt", extension: ".txt", size_bytes: 2048,
  text_chars: 1800, truncated: false, chunk_count: 2, status: "extracted",
  error: null, created_at: "2026-07-17T10:00:00Z",
};

describe("UserDocumentsPanel (Phase R7)", () => {
  const realFetch = global.fetch;
  afterEach(() => { global.fetch = realFetch; });

  it("renders an honest empty state and the supported-types note", async () => {
    global.fetch = vi.fn(async () =>
      ({ ok: true, status: 200, json: async () => ({ documents: [] }) } as Response),
    ) as unknown as typeof fetch;
    render(<UserDocumentsPanel oppId={OPP} />);
    await waitFor(() => expect(screen.getByTestId("documents-empty")).toBeInTheDocument());
    expect(screen.getByText(/PDF is not supported yet/)).toBeInTheDocument();
  });

  it("lists documents with size and chunk metadata", async () => {
    global.fetch = vi.fn(async () =>
      ({ ok: true, status: 200, json: async () => ({ documents: [DOC] }) } as Response),
    ) as unknown as typeof fetch;
    render(<UserDocumentsPanel oppId={OPP} />);
    await waitFor(() => expect(screen.getByTestId("document-row")).toBeInTheDocument());
    expect(screen.getByTestId("document-row")).toHaveTextContent("internal-study.txt");
    expect(screen.getByTestId("document-row")).toHaveTextContent("2 KB");
    expect(screen.getByTestId("document-row")).toHaveTextContent("2 chunks");
  });

  it("uploads a file as base64 and reloads the list", async () => {
    let uploaded: { filename?: string; content_base64?: string } = {};
    let hasDoc = false;
    global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/documents") && init?.method === "POST") {
        uploaded = JSON.parse(String(init.body));
        hasDoc = true;
        return { ok: true, status: 201, json: async () => DOC } as Response;
      }
      return { ok: true, status: 200,
               json: async () => ({ documents: hasDoc ? [DOC] : [] }) } as Response;
    }) as unknown as typeof fetch;
    render(<UserDocumentsPanel oppId={OPP} />);
    await waitFor(() => expect(screen.getByTestId("documents-empty")).toBeInTheDocument());
    const file = new File(["Settlement takes 4 days."], "study.txt", { type: "text/plain" });
    await userEvent.upload(screen.getByTestId("upload-input"), file);
    await waitFor(() => expect(screen.getByTestId("document-row")).toBeInTheDocument());
    expect(uploaded.filename).toBe("study.txt");
    expect(atob(uploaded.content_base64!)).toContain("Settlement takes 4 days.");
  });

  it("surfaces the backend's honest error for unsupported files", async () => {
    global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).includes("/documents") && init?.method === "POST") {
        return { ok: false, status: 415, json: async () =>
          ({ error: "PDF extraction is not supported yet" }) } as Response;
      }
      return { ok: true, status: 200, json: async () => ({ documents: [] }) } as Response;
    }) as unknown as typeof fetch;
    render(<UserDocumentsPanel oppId={OPP} />);
    await waitFor(() => expect(screen.getByTestId("documents-empty")).toBeInTheDocument());
    const file = new File(["%PDF-1.4"], "deck.pdf", { type: "application/pdf" });
    // applyAccept off: users can bypass the accept filter via drag-drop or
    // "All files" — the backend's honest error must surface either way
    await userEvent.upload(screen.getByTestId("upload-input"), file, { applyAccept: false });
    await waitFor(() => expect(screen.getByTestId("documents-error"))
      .toHaveTextContent("PDF extraction is not supported yet"));
  });

  it("deletes after confirmation", async () => {
    let deleted = false;
    vi.spyOn(window, "confirm").mockReturnValue(true);
    global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/documents/DOC-") && init?.method === "DELETE") {
        deleted = true;
        return { ok: true, status: 200,
                 json: async () => ({ deleted: true, id: DOC.id }) } as Response;
      }
      return { ok: true, status: 200,
               json: async () => ({ documents: deleted ? [] : [DOC] }) } as Response;
    }) as unknown as typeof fetch;
    render(<UserDocumentsPanel oppId={OPP} />);
    await waitFor(() => expect(screen.getByTestId("document-row")).toBeInTheDocument());
    await userEvent.click(screen.getByTestId("delete-document"));
    await waitFor(() => expect(screen.getByTestId("documents-empty")).toBeInTheDocument());
    expect(deleted).toBe(true);
  });
});
