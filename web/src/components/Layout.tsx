import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { useAuth } from "../state/auth";

function ThemeToggle() {
  const [theme, setTheme] = useState<string>(
    () => document.documentElement.dataset.theme ?? "dark",
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("at-theme", theme);
    } catch {
      /* private mode */
    }
  }, [theme]);
  return (
    <button
      type="button"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      aria-label="Toggle color theme"
      className="rounded-md border border-hairline px-2 py-1 text-xs text-ink-secondary hover:bg-surface-2"
    >
      {theme === "dark" ? "☾ Dark" : "☀ Light"}
    </button>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const { projectId } = useParams();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.listProjects });

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-40 border-b border-hairline bg-page/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4">
          <Link to="/projects" className="flex items-center gap-2 font-semibold tracking-tight">
            <span
              aria-hidden
              className="grid h-6 w-6 place-items-center rounded-md bg-accent text-[13px] font-bold text-white"
            >
              ⌁
            </span>
            Agent Tracer
          </Link>

          {projectId && projects.data && (
            <>
              <span className="text-ink-muted">/</span>
              <select
                aria-label="Switch project"
                className="max-w-56 rounded-md border border-hairline bg-surface-1 px-2 py-1 text-sm"
                value={projectId}
                onChange={(event) => navigate(`/projects/${event.target.value}`)}
              >
                {projects.data.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <nav className="hidden items-center gap-1 text-sm sm:flex">
                <Link
                  to={`/projects/${projectId}`}
                  className="rounded-md px-2 py-1 text-ink-secondary hover:bg-surface-2 hover:text-ink"
                >
                  Traces
                </Link>
                <Link
                  to={`/projects/${projectId}/settings`}
                  className="rounded-md px-2 py-1 text-ink-secondary hover:bg-surface-2 hover:text-ink"
                >
                  Settings
                </Link>
              </nav>
            </>
          )}

          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            {user && (
              <div className="flex items-center gap-2 text-sm text-ink-secondary">
                <span className="hidden sm:inline">{user.name}</span>
                <button
                  type="button"
                  onClick={() => {
                    signOut();
                    navigate("/login");
                  }}
                  className="rounded-md border border-hairline px-2 py-1 text-xs hover:bg-surface-2"
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">{children}</main>
    </div>
  );
}
