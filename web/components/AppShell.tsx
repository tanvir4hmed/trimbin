"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import PublicShell from "@/components/PublicShell";
import UploadTray from "@/components/UploadTray";
import type { Project } from "@/lib/api";
import { api } from "@/lib/api";
import { currentIdentity, signOut, type Identity } from "@/lib/auth";

const APP_PREFIXES = ["/dashboard", "/projects", "/review", "/archive", "/activity", "/project/"];
const NAV = [
  ["/dashboard", "⌂", "Home"], ["/projects", "□", "Projects"],
  ["/review", "▷", "Review"], ["/archive", "⌕", "Search"], ["/activity", "⌁", "Activity"],
] as const;

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isApp = APP_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(prefix));
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [collapsed, setCollapsed] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [projectQuery, setProjectQuery] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    setIdentity(currentIdentity());
    setCollapsed(localStorage.getItem("trimbin.sidebar.collapsed") === "1");
    const refresh = () => setIdentity(currentIdentity());
    addEventListener("trimbin:auth", refresh); addEventListener("storage", refresh);
    return () => { removeEventListener("trimbin:auth", refresh); removeEventListener("storage", refresh); };
  }, []);
  useEffect(() => {
    if (!isApp) return;
    void api.projects().then((result) => setProjects(result.projects)).catch(() => setProjects([]));
  }, [identity, isApp]);
  useEffect(() => setSwitching(false), [pathname]);

  const currentId = Number(pathname.match(/\/project\/(\d+)/)?.[1] || 0);
  const current = projects.find((project) => project.project_id === currentId);
  const filtered = useMemo(() => projects.filter((project) => project.name.toLowerCase().includes(projectQuery.toLowerCase())), [projects, projectQuery]);
  const active = (href: string) => pathname === href || pathname.startsWith(`${href}/`) || (href === "/projects" && pathname.startsWith("/project/"));
  const submitSearch = (event: FormEvent) => { event.preventDefault(); if (search.trim()) router.push(`/archive?q=${encodeURIComponent(search.trim())}`); };

  // The entry page is its own thing — one screen, two buttons, no chrome. The
  // evidence pages get the public bar; before this they got nothing at all,
  // which left /accuracy with no way back to the product it measures.
  if (pathname === "/") return <>{children}</>;
  if (!isApp) return <PublicShell>{children}</PublicShell>;
  return <div className={collapsed ? "app-frame sidebar-collapsed" : "app-frame"}>
    <aside className="app-sidebar">
      <header><Link href="/dashboard" className="app-wordmark"><span>◩</span><b>TRIMBIN</b></Link><button aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} onClick={() => { const next = !collapsed; setCollapsed(next); localStorage.setItem("trimbin.sidebar.collapsed", next ? "1" : "0"); }}>{collapsed ? "»" : "«"}</button></header>
      <nav>{NAV.map(([href, icon, label]) => <Link key={href} href={href} aria-current={active(href) ? "page" : undefined} title={label}><i>{icon}</i><span>{label}</span></Link>)}</nav>
      <footer>{identity ? <button className="app-user" onClick={() => { signOut(); setIdentity(null); router.push("/"); }} title="Sign out"><i>{identity.name.slice(0, 1).toUpperCase()}</i><span><b>{identity.name}</b><small>Sign out</small></span></button> : <Link href="/">Sign in</Link>}</footer>
    </aside>
    <div className="app-stage">
      <header className="app-topbar">
        <div className="switch-wrap"><button className="switch-button" onClick={() => setSwitching((open) => !open)}><small>Switch project</small><b>{current?.name || "All projects"}</b><span>⌄</span></button>{switching && <div className="switch-menu"><input autoFocus placeholder="Search projects…" value={projectQuery} onChange={(event) => setProjectQuery(event.target.value)} /><Link href="/projects">All projects</Link>{filtered.slice(0, 8).map((project) => <Link key={project.project_id} href={`/project/${project.project_id}`}>{project.name}<small>{project.you_are_owner ? "Owner" : project.you_can_upload ? "Editor" : "Guest"}</small></Link>)}</div>}</div>
        <form className="app-global-search" onSubmit={submitSearch}><span>⌕</span><input aria-label="Search shots and moments" placeholder="Search shots, moments, issues…" value={search} onChange={(event) => setSearch(event.target.value)} /></form>
        <div className="app-top-actions"><button aria-label="Notifications">○</button><span>{identity?.name.split(" ")[0] || "Guest"}</span></div>
      </header>
      <div className="app-scroll">{children}</div>
      <UploadTray />
    </div>
  </div>;
}
