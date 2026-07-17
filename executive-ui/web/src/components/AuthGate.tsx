// Phase R8a — the sign-in gate. Renders its children untouched when the
// deployment runs with auth off (the default) or a session exists; shows
// the sign-in/register screen only when the backend says auth is required
// and no session is present. The frontend never decides the mode — it asks
// GET /auth/me (backend-authoritative, like BOTIM_APP_MODE).
import { createContext, useContext, useEffect, useState } from "react";
import { authApi, type AuthMe, type AuthUser } from "../lib/authApi";

interface AuthContextValue {
  user: AuthUser | null;
  authMode: "off" | "required";
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null, authMode: "off", signOut: async () => {},
});
export const useAuth = () => useContext(AuthContext);

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<AuthMe | null>(null);
  const [unreachable, setUnreachable] = useState<string | null>(null);
  const [mode, setMode] = useState<"signin" | "register">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    const res = await authApi.me();
    if (!res.ok) {
      setUnreachable(res.error);
      return;
    }
    setUnreachable(null);
    setMe(res.data);
  };
  useEffect(() => { load(); }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = mode === "signin"
      ? await authApi.login(email, password)
      : await authApi.register(email, password, displayName.trim() || undefined);
    setBusy(false);
    if (!res.ok) {
      setError(res.error);
      return;
    }
    setPassword("");
    await load();
  };

  const signOut = async () => {
    await authApi.logout();
    await load();
  };

  if (unreachable) {
    return (
      <div className="auth-screen" data-testid="auth-unreachable">
        <div className="auth-card">
          <h1>BOTIM Opportunity Intelligence</h1>
          <div className="error-banner">{unreachable}</div>
        </div>
      </div>
    );
  }
  if (!me) {
    return <div className="auth-screen"><div className="skeleton" style={{ height: 160, width: 320 }} /></div>;
  }

  if (me.auth_mode === "required" && !me.user) {
    return (
      <div className="auth-screen" data-testid="auth-gate">
        <div className="auth-card">
          <h1>BOTIM Opportunity Intelligence</h1>
          <p className="auth-sub">
            {mode === "signin" ? "Sign in to continue." : "Create an account to continue."}
          </p>
          {error && <div className="error-banner" data-testid="auth-error">{error}</div>}
          <form onSubmit={submit} className="auth-form">
            {mode === "register" && (
              <>
                <label htmlFor="auth-name">Name (optional)</label>
                <input id="auth-name" type="text" value={displayName} autoComplete="name"
                  onChange={(e) => setDisplayName(e.target.value)} />
              </>
            )}
            <label htmlFor="auth-email">Email</label>
            <input id="auth-email" type="email" required value={email} autoComplete="email"
              onChange={(e) => setEmail(e.target.value)} />
            <label htmlFor="auth-password">Password{mode === "register" ? " (10+ characters)" : ""}</label>
            <input id="auth-password" type="password" required value={password}
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
              minLength={mode === "register" ? 10 : undefined}
              onChange={(e) => setPassword(e.target.value)} />
            <button type="submit" className="btn btn-primary" disabled={busy} data-testid="auth-submit">
              {busy ? "Working…" : mode === "signin" ? "Sign in" : "Create account"}
            </button>
          </form>
          {me.registration_open ? (
            <button type="button" className="auth-switch" data-testid="auth-switch"
              onClick={() => { setMode(mode === "signin" ? "register" : "signin"); setError(null); }}>
              {mode === "signin" ? "New here? Create an account" : "Already registered? Sign in"}
            </button>
          ) : (
            <p className="auth-sub">Registration is closed on this deployment — ask your administrator for an account.</p>
          )}
          <p className="auth-note">
            Password reset is not available yet (it requires the email
            infrastructure planned for a later phase) — keep your password safe.
          </p>
        </div>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ user: me.user, authMode: me.auth_mode, signOut }}>
      {me.auth_mode === "required" && me.user && (
        <div className="auth-bar" data-testid="auth-bar">
          <span>{me.user.display_name || me.user.email}</span>
          <button type="button" className="auth-signout" onClick={signOut} data-testid="auth-signout">
            Sign out
          </button>
        </div>
      )}
      {children}
    </AuthContext.Provider>
  );
}
