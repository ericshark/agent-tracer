import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { formatCost, formatTokens } from "../lib/format";
import type { StatsBucket } from "../lib/types";
import { useAuth } from "../state/auth";
import {
  ChevronDownIcon,
  ChevronsLeftIcon,
  CompareIcon,
  FolderIcon,
  GearIcon,
  GridIcon,
  LogoMark,
  LogoutIcon,
  MenuIcon,
  MoonIcon,
  MoreIcon,
  SearchIcon,
  SunIcon,
} from "./icons";
import { Menu, MenuItem } from "./ui";

function readPref(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode */
  }
}

function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState<string>(
    () => document.documentElement.dataset.theme ?? "dark",
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    writePref("at-theme", theme);
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
}

export function Layout({
  title,
  actions,
  children,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(() => readPref("at-sidebar") === "collapsed");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    writePref("at-sidebar", collapsed ? "collapsed" : "expanded");
  }, [collapsed]);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => setDrawerOpen(false), [location.pathname]);

  return (
    <div className="flex min-h-full">
      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 md:hidden"
          onClick={() => setDrawerOpen(false)}
          aria-hidden
        />
      )}
      <Sidebar
        collapsed={collapsed}
        drawerOpen={drawerOpen}
        onToggleCollapsed={() => setCollapsed((c) => !c)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar title={title} actions={actions} onOpenDrawer={() => setDrawerOpen(true)} />
        <main className="flex-1 px-4 py-5 md:px-6">{children}</main>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ top bar */

function TopBar({
  title,
  actions,
  onOpenDrawer,
}: {
  title: string;
  actions?: ReactNode;
  onOpenDrawer: () => void;
}) {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!projectId) return;
    const q = query.trim();
    navigate(q ? `/projects/${projectId}?q=${encodeURIComponent(q)}` : `/projects/${projectId}`);
  };

  return (
    <header className="sticky top-0 z-30 border-b border-hairline bg-page/85 backdrop-blur">
      <div className="flex h-14 items-center gap-3 px-4 md:px-6">
        <button
          type="button"
          onClick={onOpenDrawer}
          aria-label="Open navigation"
          className="-ml-1 rounded-md p-1.5 text-ink-secondary hover:bg-surface-2 md:hidden"
        >
          <MenuIcon size={18} />
        </button>
        <h1 className="title-bracket truncate text-[15px] text-ink">{title}</h1>

        <div className="ml-auto flex min-w-0 items-center gap-2">
          {actions}
          {projectId && (
            <form onSubmit={submit} className="hidden lg:block" role="search">
              <label className="flex w-56 items-center gap-2 rounded-lg border border-hairline bg-surface-1 px-2.5 py-1.5 text-ink-muted focus-within:border-accent/60">
                <SearchIcon size={14} className="shrink-0" />
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search traces…"
                  aria-label="Search traces"
                  className="w-full min-w-0 bg-transparent text-xs text-ink placeholder:text-ink-muted focus:outline-none"
                />
              </label>
            </form>
          )}
        </div>
      </div>
    </header>
  );
}

/* ------------------------------------------------------------------ sidebar */

function Sidebar({
  collapsed,
  drawerOpen,
  onToggleCollapsed,
}: {
  collapsed: boolean;
  drawerOpen: boolean;
  onToggleCollapsed: () => void;
}) {
  const { projectId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.listProjects });

  const path = location.pathname;
  const onSettings = path.endsWith("/settings");
  const onCompare = path.endsWith("/compare");

  // The mobile drawer always shows the full sidebar.
  const narrow = collapsed && !drawerOpen;

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-50 flex w-60 shrink-0 flex-col border-r border-hairline bg-page transition-[transform,width] duration-200 md:sticky md:top-0 md:h-screen md:translate-x-0 ${
        drawerOpen ? "translate-x-0" : "-translate-x-full"
      } ${collapsed ? "md:w-[68px]" : "md:w-60"}`}
      aria-label="Primary"
    >
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-hairline px-4">
        <Link
          to="/projects"
          className="flex items-center gap-2.5 text-ink"
          aria-label="Agent Tracer home"
        >
          <LogoMark size={22} className="text-ink-secondary" />
          <span className={`mono text-sm font-medium tracking-tight ${narrow ? "md:hidden" : ""}`}>
            agent-tracer
          </span>
        </Link>
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={`hidden rounded-md p-1 text-ink-muted hover:bg-surface-2 hover:text-ink md:block ${
            narrow
              ? "md:absolute md:-right-3 md:top-4 md:border md:border-hairline md:bg-surface-1"
              : ""
          }`}
        >
          <ChevronsLeftIcon size={14} className={collapsed ? "rotate-180" : ""} />
        </button>
      </div>

      <nav className="panel-scroll flex-1 overflow-y-auto px-2 py-3">
        <NavItem
          to="/projects"
          icon={<FolderIcon />}
          label="Projects"
          active={path === "/projects"}
          narrow={narrow}
        />

        {projectId && (
          <>
            <div className="my-3 border-t border-hairline" />
            <SectionLabel narrow={narrow}>Project</SectionLabel>
            {!narrow && projects.data && (
              <div className="relative mb-2 px-1">
                <select
                  aria-label="Switch project"
                  className="mono w-full appearance-none truncate rounded-lg border border-hairline bg-surface-1 py-1.5 pr-7 pl-2.5 text-xs text-ink focus:border-accent/60 focus:outline-none"
                  value={projectId}
                  onChange={(event) => navigate(`/projects/${event.target.value}`)}
                >
                  {projects.data.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <ChevronDownIcon
                  size={13}
                  className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-ink-muted"
                />
              </div>
            )}
            <NavItem
              to={`/projects/${projectId}`}
              icon={<GridIcon />}
              label="Overview"
              active={!onSettings && !onCompare}
              narrow={narrow}
            />
            {onCompare && (
              <NavItem
                to={`${path}${location.search}`}
                icon={<CompareIcon />}
                label="Compare"
                active
                narrow={narrow}
              />
            )}
            <NavItem
              to={`/projects/${projectId}/settings`}
              icon={<GearIcon />}
              label="Settings"
              active={onSettings}
              narrow={narrow}
            />
          </>
        )}
      </nav>

      <div className="flex shrink-0 flex-col gap-2 p-2">
        {projectId && !narrow && <SpendCard projectId={projectId} />}
        <UserCard narrow={narrow} />
      </div>
    </aside>
  );
}

function SectionLabel({ children, narrow }: { children: ReactNode; narrow: boolean }) {
  if (narrow) return null;
  return (
    <p className="mb-1.5 px-2.5 text-[10px] font-medium tracking-[0.08em] text-ink-muted uppercase">
      {children}
    </p>
  );
}

function NavItem({
  to,
  icon,
  label,
  active,
  narrow,
}: {
  to: string;
  icon: ReactNode;
  label: string;
  active: boolean;
  narrow: boolean;
}) {
  return (
    <Link
      to={to}
      title={narrow ? label : undefined}
      aria-current={active ? "page" : undefined}
      className={`mb-0.5 flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors ${
        active ? "nav-active text-ink" : "text-ink-secondary hover:bg-surface-1 hover:text-ink"
      } ${narrow ? "md:justify-center md:px-0" : ""}`}
    >
      <span className={`shrink-0 ${active ? "text-ink" : "text-ink-muted"}`}>{icon}</span>
      <span className={narrow ? "md:hidden" : ""}>{label}</span>
    </Link>
  );
}

/* --------------------------------------------------------------- spend card
   24h spend with a dot-matrix sparkline of cost per bucket. Shares the cache
   entry with the overview page's 24h stats query. */

function SpendCard({ projectId }: { projectId: string }) {
  const stats = useQuery({
    queryKey: ["stats", projectId, 24],
    queryFn: () => api.projectStats(projectId, 24),
    refetchInterval: 60_000,
  });
  if (!stats.data) return null;
  const tokens = stats.data.total_input_tokens + stats.data.total_output_tokens;

  return (
    <div className="card hatch overflow-hidden px-3 py-2.5">
      <p className="text-[10px] font-medium tracking-[0.08em] text-ink-secondary uppercase">
        Spend · 24h
      </p>
      <p className="mono mt-1 text-base text-ink">{formatCost(stats.data.total_cost_usd)}</p>
      <CostSparkline buckets={stats.data.buckets} />
      <div className="mono mt-1.5 flex justify-between text-[10px] text-ink-muted">
        <span>{formatTokens(tokens)} tokens</span>
        <span>{stats.data.trace_count} traces</span>
      </div>
    </div>
  );
}

function CostSparkline({ buckets }: { buckets: StatsBucket[] }) {
  const rows = 4;
  const pitch = 4;
  const max = Math.max(0, ...buckets.map((b) => b.cost_usd));
  return (
    <svg
      viewBox={`0 0 ${buckets.length * pitch} ${rows * pitch}`}
      className="mt-2 h-4 w-full"
      preserveAspectRatio="none"
      role="img"
      aria-label="Spend per hour over the last 24 hours"
    >
      {buckets.map((b, c) => {
        const level = max > 0 ? Math.ceil((b.cost_usd / max) * rows) : 0;
        return Array.from({ length: rows }, (_, r) => (
          <rect
            key={`${c}-${r}`}
            x={c * pitch}
            y={(rows - 1 - r) * pitch}
            width={pitch - 1}
            height={pitch - 1}
            rx={0.5}
            fill={r < level ? "var(--accent)" : "var(--dot-dim)"}
          />
        ));
      })}
    </svg>
  );
}

/* ---------------------------------------------------------------- user card */

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts[1]?.[0] ?? parts[0][1] ?? "")).toUpperCase();
}

function UserCard({ narrow }: { narrow: boolean }) {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [theme, toggleTheme] = useTheme();
  if (!user) return null;

  const avatar = (
    <span className="mono grid h-8 w-8 shrink-0 place-items-center rounded-md border border-hairline bg-surface-2 text-xs font-medium text-ink">
      {initials(user.name)}
    </span>
  );

  return (
    <div className={`card flex items-center gap-2.5 ${narrow ? "justify-center p-1.5" : "p-2"}`}>
      {!narrow && (
        <>
          {avatar}
          <span className="min-w-0 flex-1">
            <span className="block truncate text-xs font-medium text-ink">{user.name}</span>
            <span className="block truncate text-[10px] text-ink-muted">{user.email}</span>
          </span>
        </>
      )}
      <Menu
        label="Account menu"
        align={narrow ? "left" : "right"}
        placement="top"
        triggerClassName="grid place-items-center rounded-md p-1 text-ink-muted hover:bg-surface-2 hover:text-ink"
        trigger={narrow ? avatar : <MoreIcon size={16} />}
      >
        {(close) => (
          <>
            <MenuItem
              onSelect={() => {
                toggleTheme();
                close();
              }}
            >
              {theme === "dark" ? <SunIcon size={14} /> : <MoonIcon size={14} />}
              {theme === "dark" ? "Light theme" : "Dark theme"}
            </MenuItem>
            <MenuItem
              onSelect={() => {
                close();
                signOut();
                navigate("/login");
              }}
            >
              <LogoutIcon size={14} />
              Sign out
            </MenuItem>
          </>
        )}
      </Menu>
    </div>
  );
}
