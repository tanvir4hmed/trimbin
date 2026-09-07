"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import UploadTray from "@/components/UploadTray";
import { api } from "@/lib/api";
import { currentIdentity, signOut, type Identity } from "@/lib/auth";
import { paths } from "@/lib/slug";

const WORKSPACE = [
  ["/home", "⌂", "Home"],
  ["/projects", "□", "Projects"],
  ["/review", "▷", "Review queue"],
  ["/search", "⌕", "Search"],
] as const;
const SUPPORT = [
  ["/activity", "⌁", "Activity"],
  ["/accuracy", "◴", "Accuracy & review"],
  ["/guide", "?", "Guide"],
] as const;

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="waiting">Opening workspace…</div>}>
      <WorkspaceShell>{children}</WorkspaceShell>
    </Suspense>
  );
}

function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const params = useSearchParams();
  const router = useRouter();
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [projectQuery, setProjectQuery] = useState("");
  const [search, setSearch] = useState("");
  const currentId = Number(
    pathname.match(/\/projects\/(?:[^/]*?-)?(\d+)(?:$|\/)/)?.[1] ||
      params.get("project") ||
      0,
  );
  const projectQueryResult = useQuery({
    queryKey: ["projects", false, identity?.email ?? "anonymous"],
    queryFn: () => api.projects(),
    enabled: pathname !== "/",
    staleTime: 30_000,
  });
  const projects = projectQueryResult.data?.projects ?? [];
  const current = projects.find((p) => p.project_id === currentId);
  const filtered = useMemo(
    () =>
      projects.filter((p) =>
        p.name.toLowerCase().includes(projectQuery.trim().toLowerCase()),
      ),
    [projects, projectQuery],
  );
  const context = currentId ? `?project=${currentId}` : "";
  const scopeHref = (href: string) =>
    ["/search", "/review", "/accuracy"].includes(href) ? href + context : href;
  const switchDestination = (id: number, name: string) => {
    if (["/search", "/review", "/accuracy"].includes(pathname)) {
      const next = new URLSearchParams(params.toString());
      next.set("project", String(id));
      return `${pathname}?${next.toString()}`;
    }
    if (pathname.endsWith("/film")) return paths.film(id, name);
    if (pathname.endsWith("/ingest")) return paths.ingest(id, name);
    return paths.project(id, name);
  };

  useEffect(() => {
    const refresh = () => setIdentity(currentIdentity());
    refresh();
    try {
      setCollapsed(localStorage.getItem("trimbin.sidebar.collapsed") === "1");
    } catch {}
    addEventListener("trimbin:auth", refresh);
    addEventListener("storage", refresh);
    return () => {
      removeEventListener("trimbin:auth", refresh);
      removeEventListener("storage", refresh);
    };
  }, []);
  useEffect(() => {
    setSwitching(false);
  }, [pathname, currentId]);
  useEffect(() => {
    if (!switching) return;
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSwitching(false);
    };
    const outside = (e: MouseEvent) => {
      if (!(e.target as HTMLElement)?.closest(".switch-wrap"))
        setSwitching(false);
    };
    window.addEventListener("keydown", key);
    window.addEventListener("mousedown", outside);
    return () => {
      window.removeEventListener("keydown", key);
      window.removeEventListener("mousedown", outside);
    };
  }, [switching]);
  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem("trimbin.sidebar.collapsed", next ? "1" : "0");
    } catch {}
  };
  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    if (search.trim())
      router.push(
        `/search?q=${encodeURIComponent(search.trim())}${currentId ? `&project=${currentId}` : ""}`,
      );
  };
  const active = (href: string) => pathname === href;
  const projectNav = currentId
    ? ([
        [
          paths.project(currentId),
          "▤",
          "Scenes & shots",
          pathname.startsWith("/projects/") &&
            !pathname.endsWith("/ingest") &&
            !pathname.endsWith("/film"),
        ],
        [paths.ingest(currentId), "↑", "Footage", pathname.endsWith("/ingest")],
        [
          paths.film(currentId),
          "▶",
          "Film Preview",
          pathname.endsWith("/film"),
        ],
      ] as const)
    : [];
  if (pathname === "/") return <>{children}</>;
  return (
    <div className={collapsed ? "app-frame sidebar-collapsed" : "app-frame"}>
      <aside className="app-sidebar">
        <header>
          <Link
            href={identity ? "/home" : "/projects"}
            className="app-wordmark"
            aria-label="Trimbin workspace"
          >
            <span>◩</span>
            <b>TRIMBIN</b>
          </Link>
          <button
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
            onClick={toggle}
          >
            {collapsed ? "»" : "«"}
          </button>
        </header>
        <div className="sidebar-navigation">
          <nav aria-label="Workspace">
            <p className="nav-section-label">WORKSPACE</p>
            {WORKSPACE.map(([href, icon, label]) => (
              <Link
                key={href}
                href={scopeHref(href)}
                aria-current={active(href) ? "page" : undefined}
                title={label}
              >
                <i aria-hidden>{icon}</i>
                <span>{label}</span>
              </Link>
            ))}
          </nav>
          {currentId > 0 && (
            <nav aria-label="Current project" className="project-navigation">
              <p className="nav-section-label" title={current?.name}>
                CURRENT PROJECT
              </p>
              {projectNav.map(([href, icon, label, selected]) => (
                <Link
                  key={href}
                  href={href}
                  aria-current={selected ? "page" : undefined}
                  title={label}
                >
                  <i aria-hidden>{icon}</i>
                  <span>{label}</span>
                </Link>
              ))}
            </nav>
          )}
        </div>
        <footer>
          <nav
            className="support-navigation"
            aria-label="Workspace information"
          >
            {SUPPORT.map(([href, icon, label]) => (
              <Link
                key={href}
                href={scopeHref(href)}
                aria-current={active(href) ? "page" : undefined}
                title={label}
              >
                <i aria-hidden>{icon}</i>
                <span>{label}</span>
              </Link>
            ))}
          </nav>
          {identity ? (
            <>
              <div className="app-user" title={identity.name}>
                <i aria-hidden>{identity.name.slice(0, 1).toUpperCase()}</i>
                <span>
                  <b>{identity.name}</b>
                  <small>Team workspace</small>
                </span>
              </div>
              <button
                className="app-signout"
                title="Sign out"
                onClick={() => {
                  signOut();
                  setIdentity(null);
                  router.push("/");
                }}
              >
                Sign out
              </button>
            </>
          ) : (
            <Link className="ghost small" href="/">
              Sign in
            </Link>
          )}
        </footer>
      </aside>
      <div className="app-stage">
        <header className="app-topbar">
          <div className="switch-wrap">
            <button
              className="switch-button"
              aria-expanded={switching}
              aria-controls="project-switcher"
              onClick={() => {
                setSwitching(!switching);
                setProjectQuery("");
              }}
            >
              <small>Project</small>
              <b>
                {current?.name ||
                  (currentId ? `Project ${currentId}` : "All projects")}
              </b>
              <span>⌄</span>
            </button>
            {switching && (
              <div id="project-switcher" className="switch-menu">
                <input
                  autoFocus
                  aria-label="Search projects"
                  placeholder="Find a project…"
                  value={projectQuery}
                  onChange={(e) => setProjectQuery(e.target.value)}
                />
                <Link href="/projects" onClick={() => setSwitching(false)}>
                  All projects
                </Link>
                <div className="switch-results">
                  {filtered.map((p) => (
                    <Link
                      key={p.project_id}
                      href={switchDestination(p.project_id, p.name)}
                      onClick={() => setSwitching(false)}
                      aria-current={
                        p.project_id === currentId ? "true" : undefined
                      }
                    >
                      {p.name}
                      <small>
                        {p.you_are_owner
                          ? "Owner"
                          : p.you_can_upload
                            ? "Editor"
                            : "View"}
                      </small>
                    </Link>
                  ))}
                </div>
                {!filtered.length && (
                  <p className="hint">
                    {projectQueryResult.isError
                      ? "Projects unavailable."
                      : projectQueryResult.isPending
                        ? "Loading projects…"
                        : "No matching projects."}
                  </p>
                )}
                {projectQueryResult.isError && (
                  <button
                    className="ghost small"
                    onClick={() => void projectQueryResult.refetch()}
                  >
                    Retry
                  </button>
                )}
              </div>
            )}
          </div>
          <form className="app-global-search" onSubmit={submitSearch}>
            <span aria-hidden>⌕</span>
            <input
              aria-label={currentId ? "Search this project" : "Search footage"}
              placeholder={
                currentId
                  ? "Search this project: action, dialogue, issue…"
                  : "Find footage, dialogue or an issue…"
              }
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </form>
          {currentId > 0 && (
            <div className="app-top-actions">
              <span>{identity ? "Team workspace" : "Read-only preview"}</span>
            </div>
          )}
        </header>
        <div className="app-scroll">{children}</div>
        <UploadTray />
      </div>
    </div>
  );
}
