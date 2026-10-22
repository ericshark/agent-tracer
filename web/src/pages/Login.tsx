import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../lib/api";
import { LogoMark } from "../components/icons";
import { PrimaryButton, TextInput } from "../components/ui";
import { useAuth } from "../state/auth";

export function LoginPage() {
  const { signIn, signUp } = useAuth();
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await signIn(email, password);
      else await signUp(email, name, password);
      navigate(location.state?.from ?? "/projects", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="dot-grid grid min-h-full place-items-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2.5 text-ink">
          <LogoMark size={26} className="text-accent" />
          <span className="mono text-lg font-medium tracking-tight">agent-tracer</span>
        </div>
        <form onSubmit={submit} className="card flex flex-col gap-3 p-6 shadow-2xl">
          <h1 className="title-bracket text-[15px] text-ink">
            {mode === "login" ? "Sign in" : "Create account"}
          </h1>
          <p className="-mt-1 mb-1 text-xs text-ink-muted">
            {mode === "login"
              ? "Inspect, replay, and compare your agent runs."
              : "Start tracing your agents in minutes."}
          </p>
          {mode === "register" && (
            <TextInput
              placeholder="Your name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoComplete="name"
            />
          )}
          <TextInput
            type="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
          <TextInput
            type="password"
            placeholder={mode === "register" ? "Password (min 8 characters)" : "Password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={mode === "register" ? 8 : undefined}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
          {error && <p className="text-xs text-critical">{error}</p>}
          <PrimaryButton type="submit" disabled={busy}>
            {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
          </PrimaryButton>
          <button
            type="button"
            className="text-xs text-ink-muted hover:text-ink-secondary"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError(null);
            }}
          >
            {mode === "login"
              ? "No account yet? Create one"
              : "Already have an account? Sign in"}
          </button>
        </form>
        <p className="mono mt-4 text-center text-[11px] text-ink-muted">
          Seeded demo: demo@agenttracer.dev / demo-password
        </p>
      </div>
    </div>
  );
}
