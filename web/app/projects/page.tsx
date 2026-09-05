"use client";

/**
 * Every project, when there are more than a screenful.
 *
 * A table rather than more cards, because past about six projects the question
 * changes from "which one shall I open" to "which one is behind". A table sorts;
 * cards do not.
 *
 * Built now rather than later, when the alternative is building it in a panic
 * the week somebody has fifteen productions open.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import NewProject from "@/components/NewProject";
import type { Limits, Project, Role } from "@/lib/api";
import { ApiError, api } from "@/lib/api";
import { paths } from "@/lib/slug";

type SortKey = "name" | "waiting" | "progress" | "created";

export default function ProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [role, setRole] = useState<Role>("guest");
  const [limits, setLimits] = useState<Limits | null>(null);
  const [you, setYou] = useState("");
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState<SortKey>("waiting");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [scope, setScope] = useState<"active" | "archived" | "trashed" | "deleted">("active");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const found = await api.projects(true, scope);
      setProjects(found.projects);
      setRole(found.role);
      setLimits(found.limits);
      setYou(found.you);
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        router.replace("/");
        return;
      }
      setError(e instanceof Error ? e.message : "Could not load your projects.");
    } finally {
      setLoading(false);
    }
  }, [router, scope]);

  useEffect(() => {
    // Signed-out visitors may browse public productions. The API redacts team
    // details and capabilities for them; forcing them back to the login door
    // made the "look without signing in" path a loop.
    void load();
  }, [load, router]);

  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const matched = needle
      ? projects.filter(
          (p) =>
            p.name.toLowerCase().includes(needle) ||
            p.owner_email.toLowerCase().includes(needle) ||
            p.member_emails.some((m) => m.toLowerCase().includes(needle)),
        )
      : projects;

    return [...matched].sort((a, b) => {
      switch (sort) {
        case "name":
          return a.name.localeCompare(b.name);
        case "progress":
          // Nulls last. A project with no footage has no progress, and sorting
          // it as zero would put every empty project at the top of "least
          // finished", which is the opposite of useful.
          return (b.progress_pct ?? -1) - (a.progress_pct ?? -1);
        case "created":
          return b.created_at.localeCompare(a.created_at);
        default:
          return (b.waiting ?? 0) - (a.waiting ?? 0);
      }
    });
  }, [projects, filter, sort]);

  const command = async (project: Project, action: "rename" | "archive" | "trash" | "restore" | "delete") => {
    let name = "";
    if (action === "rename") {
      name = window.prompt("Project name", project.name)?.trim() ?? "";
      if (!name || name === project.name) return;
    }
    if ((action === "trash" || action === "delete") && !window.confirm(action === "delete" ? "Remove this project from Trimbin?\n\nIt disappears from every list, and from the signed-out view if it was public. Its footage, decisions and audit records are all kept, and you can bring it back from the Removed tab." : "Move this project to Trash?")) return;
    try {
      await api.changeProject(project.project_id, { rev: project.rev, action, name });
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not update the project."); }
  };

  if (loading) {
    return (
      <main className="shell">
        <p className="waiting">Loading — the archive may be waking up.</p>
      </main>
    );
  }

  return (
    <main className="shell">
      <header className="dash-top">
        <div>
          <h1>Projects</h1>
          <p className="dim">
            {projects.length} project{projects.length === 1 ? "" : "s"} you can
            open
          </p>
        </div>
        {limits && you && (
          <NewProject
            limits={limits}
            role={role}
            owned={projects.filter((p) => p.you_are_owner).length}
            onCreated={(id) => router.push(`${paths.project(id)}`)}
          />
        )}
      </header>

      <nav className="project-scope-tabs" aria-label="Project state">
        {(["active", "archived", "trashed", "deleted"] as const).map((item) => <button key={item} className={scope === item ? "on" : ""} onClick={() => setScope(item)}>{item === "active" ? "Current" : item === "archived" ? "Archived" : item === "trashed" ? "Trash" : "Removed"}</button>)}
      </nav>

      {error && <p className="error">{error}</p>}

      <div className="table-controls">
        <input
          type="search"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by name or by who is on it"
          aria-label="Filter projects"
        />
        <label>
          Sort
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
          >
            <option value="waiting">what needs attention</option>
            <option value="progress">how far through</option>
            <option value="name">name</option>
            <option value="created">newest</option>
          </select>
        </label>
      </div>

      {shown.length === 0 ? (
        <p className="hint">
          {projects.length === 0
            ? you
              ? "No projects yet. Make one and add the first shoot day."
              : "No public projects are available. Sign in as Guest to open the working application."
            : "Nothing matches that."}
        </p>
      ) : <div className="project-showcase-grid">{shown.map((p, index) => <article className="project-showcase" key={p.project_id}><Link className={`project-cover cover-${index % 6}`} href={`${paths.project(p.project_id, p.name)}`}><span>{p.you_are_owner ? "Owner" : p.you_can_upload ? "Editor" : "Guest"}</span></Link><div className="project-showcase-body"><header><Link href={`${paths.project(p.project_id, p.name)}`}>{p.name}</Link>{p.is_public && <span className="tag">public</span>}</header><div className="project-facts"><span><b>{p.scenes ?? "—"}</b> scenes</span><span><b>{p.shots ?? "—"}</b> shots</span><span><b>{p.takes ?? "—"}</b> clips</span><span className={p.waiting ? "bad" : ""}><b>{p.waiting ?? 0}</b> decisions</span></div>{p.progress_pct !== null && p.progress_pct !== undefined && <div className="project-progress"><i style={{ width: `${p.progress_pct}%` }}/><span>{p.progress_pct}% settled</span></div>}<footer><small>{p.owner_email === you ? "You" : p.owner_email.split("@")[0]}{p.member_emails.length ? ` + ${p.member_emails.length} editors` : ""}</small><Link href={`${paths.project(p.project_id, p.name)}`}>Open project →</Link></footer>{p.you_are_owner && <div className="project-actions">{scope === "active" && <><button onClick={() => void command(p,"rename")}>Rename</button><button onClick={() => void command(p,"archive")}>Archive</button><button onClick={() => void command(p,"trash")}>Trash</button></>}{scope === "archived" && <><button onClick={() => void command(p,"restore")}>Restore</button><button onClick={() => void command(p,"trash")}>Trash</button></>}{scope === "trashed" && <><button onClick={() => void command(p,"restore")}>Restore</button><button className="danger" onClick={() => void command(p,"delete")}>Delete</button></>}{scope === "deleted" && <button onClick={() => void command(p,"restore")}>Restore</button>}</div>}</div></article>)}</div>}
    </main>
  );
}
