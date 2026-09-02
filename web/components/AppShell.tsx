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
  const [settingsOpen, setSettingsOpen] = useState(false);

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
  useEffect(() => { setSwitching(false); setSettingsOpen(false); }, [pathname]);

  // Escape, and a click anywhere else. An open menu that only closes by
  // pressing the same button again traps whoever opened it by accident.
  useEffect(() => {
    if (!switching && !settingsOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setSwitching(false); setSettingsOpen(false); }
    };
    const onDown = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest(".switch-wrap")) return;
      if (target?.closest(".app-sidebar footer")) return;
      setSwitching(false);
      setSettingsOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onDown);
    };
  }, [switching, settingsOpen]);

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
      <footer>
        {/* Clicking your own name signed you out with no warning and no way
            back. It opens your account now; signing out is a separate,
            deliberate row underneath it. */}
        {identity ? <>
          {settingsOpen && <div className="app-settings">
            <p className="eyebrow">ACCOUNT</p>
            <label>Name<input value={identity.name} readOnly /></label>
            <label>Email<input value={identity.email} readOnly /></label>
            {/* Deliberately inert. The field is here so the shape of the screen
                is honest about what will live on it; changing a password is not
                built, and a control that looks live and does nothing is worse
                than one that says so. */}
            <label>New password<input type="password" value="" placeholder="Not available yet" disabled readOnly /></label>
            <p className="policy-note">Your name and address come from the sign-in you used. Changing them, and setting a password, are not built yet.</p>
            <button className="ghost small" onClick={() => { signOut(); setIdentity(null); router.push("/"); }}>Sign out</button>
          </div>}
          <button className="app-user" onClick={() => setSettingsOpen((open) => !open)} title="Account and settings" aria-expanded={settingsOpen}>
            <i>{identity.name.slice(0, 1).toUpperCase()}</i>
            <span><b>{identity.name}</b><small>Account &amp; settings</small></span>
          </button>
        </> : <Link href="/">Sign in</Link>}
        {/* A second collapse control down here, because the first one is at the
            top of a full-height column and this is where the cursor already is. */}
        <button
          className="app-collapse-foot"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={() => { const next = !collapsed; setCollapsed(next); localStorage.setItem("trimbin.sidebar.collapsed", next ? "1" : "0"); }}
        >
          {collapsed ? "»" : "«  Collapse"}
        </button>
      </footer>
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
