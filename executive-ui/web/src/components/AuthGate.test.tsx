import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AuthGate from "./AuthGate";

function fetchSequence(handler: (url: string, init?: RequestInit) => unknown) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const body = handler(String(input), init);
    if (body instanceof Error) throw body;
    const { status = 200, json } = body as { status?: number; json: unknown };
    return { ok: status < 400, status, json: async () => json } as Response;
  });
}

describe("AuthGate (Phase R8a)", () => {
  const realFetch = global.fetch;
  afterEach(() => { global.fetch = realFetch; });

  it("renders children untouched when auth is off (the default deployment)", async () => {
    global.fetch = fetchSequence((url) => {
      if (url.includes("/auth/me")) {
        return { json: { auth_mode: "off", registration_open: true, user: null } };
      }
      return { status: 404, json: { error: "not found" } };
    }) as unknown as typeof fetch;
    render(<AuthGate><div data-testid="the-app">app</div></AuthGate>);
    await waitFor(() => expect(screen.getByTestId("the-app")).toBeInTheDocument());
    expect(screen.queryByTestId("auth-gate")).toBeNull();
    expect(screen.queryByTestId("auth-bar")).toBeNull();  // no bar when auth is off
  });

  it("shows the sign-in screen when auth is required and no session exists", async () => {
    global.fetch = fetchSequence((url) => {
      if (url.includes("/auth/me")) {
        return { json: { auth_mode: "required", registration_open: true, user: null } };
      }
      return { status: 404, json: { error: "not found" } };
    }) as unknown as typeof fetch;
    render(<AuthGate><div data-testid="the-app">app</div></AuthGate>);
    await waitFor(() => expect(screen.getByTestId("auth-gate")).toBeInTheDocument());
    expect(screen.queryByTestId("the-app")).toBeNull();   // the app never leaks through
    expect(screen.getByText(/Password reset is not available yet/)).toBeInTheDocument();
  });

  it("signs in and then renders the app with the session bar", async () => {
    let signedIn = false;
    global.fetch = fetchSequence((url, init) => {
      if (url.includes("/auth/login") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual(
          { email: "a@example.com", password: "long-enough-pass" });
        signedIn = true;
        return { json: { user: { id: "USER-1", email: "a@example.com" } } };
      }
      if (url.includes("/auth/me")) {
        return { json: { auth_mode: "required", registration_open: true,
                         user: signedIn ? { id: "USER-1", email: "a@example.com",
                                            display_name: null, created_at: "" } : null } };
      }
      return { status: 404, json: { error: "not found" } };
    }) as unknown as typeof fetch;
    render(<AuthGate><div data-testid="the-app">app</div></AuthGate>);
    await waitFor(() => expect(screen.getByTestId("auth-gate")).toBeInTheDocument());
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "long-enough-pass");
    await userEvent.click(screen.getByTestId("auth-submit"));
    await waitFor(() => expect(screen.getByTestId("the-app")).toBeInTheDocument());
    expect(screen.getByTestId("auth-bar")).toHaveTextContent("a@example.com");
  });

  it("shows the backend's honest error on a failed sign-in", async () => {
    global.fetch = fetchSequence((url, init) => {
      if (url.includes("/auth/login") && init?.method === "POST") {
        return { status: 401, json: { error: "invalid email or password" } };
      }
      if (url.includes("/auth/me")) {
        return { json: { auth_mode: "required", registration_open: true, user: null } };
      }
      return { status: 404, json: { error: "not found" } };
    }) as unknown as typeof fetch;
    render(<AuthGate><div>app</div></AuthGate>);
    await waitFor(() => expect(screen.getByTestId("auth-gate")).toBeInTheDocument());
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password-1");
    await userEvent.click(screen.getByTestId("auth-submit"));
    await waitFor(() =>
      expect(screen.getByTestId("auth-error")).toHaveTextContent("invalid email or password"));
  });

  it("offers registration only while it is open", async () => {
    global.fetch = fetchSequence((url) => {
      if (url.includes("/auth/me")) {
        return { json: { auth_mode: "required", registration_open: false, user: null } };
      }
      return { status: 404, json: { error: "not found" } };
    }) as unknown as typeof fetch;
    render(<AuthGate><div>app</div></AuthGate>);
    await waitFor(() => expect(screen.getByTestId("auth-gate")).toBeInTheDocument());
    expect(screen.queryByTestId("auth-switch")).toBeNull();
    expect(screen.getByText(/Registration is closed/)).toBeInTheDocument();
  });

  it("renders an honest unreachable state when the API is down", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("down")) as unknown as typeof fetch;
    render(<AuthGate><div data-testid="the-app">app</div></AuthGate>);
    await waitFor(() =>
      expect(screen.getByTestId("auth-unreachable")).toBeInTheDocument());
    expect(screen.queryByTestId("the-app")).toBeNull();
  });
});
