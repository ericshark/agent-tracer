import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../lib/api";
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
    <div className="grid min-h-full place-items-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2 text-lg font-semibold">
          <span
            aria-hidden
            className="grid h-7 w-7 place-items-center rounded-md bg-accent text-sm font-bold text-white"
          >
            ⌁
          </span>
          Agent Tracer
        </div>
        <form onSubmit={submit} className="card flex flex-col gap-3 p-6">
          <h1 className="text-sm font-semibold">
            {mode === "login" ? "Sign in" : "Create your account"}
          </h1>
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
        <p className="mt-4 text-center text-xs text-ink-muted">
          Seeded demo: demo@agenttracer.dev / demo-password
        </p>
      </div>
    </div>
  );
}
