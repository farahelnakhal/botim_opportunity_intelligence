// Phase R8a — auth client. The session travels as an HttpOnly cookie set by
// the backend (same-origin fetch sends it automatically); this module never
// sees or stores a token. Honest failure shape like the other clients.

export interface AuthUser {
  id: string;
  email: string;
  display_name: string | null;
  created_at: string;
}

export interface AuthMe {
  auth_mode: "off" | "required";
  registration_open: boolean;
  user: AuthUser | null;
}

const BASE = import.meta.env.VITE_EXECUTIVE_API_BASE_URL || "/executive-api";

export type AuthResult<T> = { ok: true; data: T } | { ok: false; error: string };

async function request<T>(path: string, init?: RequestInit): Promise<AuthResult<T>> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      ...init,
    });
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      return { ok: false, error: "malformed response from the server" };
    }
    if (!res.ok) {
      const msg = (body as { error?: string })?.error || `HTTP ${res.status}`;
      return { ok: false, error: msg };
    }
    return { ok: true, data: body as T };
  } catch {
    return { ok: false, error: "the server is unreachable" };
  }
}

export const authApi = {
  me() {
    return request<AuthMe>("/auth/me");
  },
  login(email: string, password: string) {
    return request<{ user: AuthUser }>("/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }),
    });
  },
  register(email: string, password: string, displayName?: string) {
    return request<{ user: AuthUser }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, display_name: displayName || undefined }),
    });
  },
  logout() {
    return request<{ signed_out: boolean }>("/auth/logout", { method: "POST", body: "{}" });
  },
};
