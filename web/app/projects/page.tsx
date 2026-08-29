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
import { currentIdentity } from "@/lib/auth";

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

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const found = await api.projects(true);
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
  }, [router]);

  useEffect(() => {
    if (!currentIdentity()) {
      router.replace("/");
      return;
    }
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
        {limits && (
          <NewProject
            limits={limits}
            role={role}
            owned={projects.filter((p) => p.you_are_owner).length}
            onCreated={(id) => router.push(`/project/${id}`)}
          />
        )}
      </header>

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
            ? "No projects yet. Make one, or open one of ours from the front page."
            : "Nothing matches that."}
        </p>
      ) : (
        <div className="scroll-x">
          <table className="projects">
            <thead>
              <tr>
                <th>Project</th>
                <th>Scenes</th>
                <th>Shots</th>
                <th>Takes</th>
                <th>Progress</th>
                <th>Waiting</th>
                <th>Who</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((p) => (
                <tr key={p.project_id}>
                  <th scope="row">
                    <Link href={`/project/${p.project_id}`}>{p.name}</Link>
                    {p.is_public && <span className="tag">public</span>}
                    {!p.you_can_upload && (
                      // Said rather than discovered at the upload button. A
                      // guest reading our productions should know which ones
                      // they can add footage to before they try.
                      <span className="tag quiet">read and comment</span>
                    )}
                  </th>
                  <td>{p.scenes ?? "—"}</td>
                  <td>{p.shots ?? "—"}</td>
                  <td>{p.takes ?? "—"}</td>
                  <td>
                    {p.progress_pct === null || p.progress_pct === undefined ? (
                      <span className="dim">—</span>
                    ) : (
                      <>
                        <span className="bar inline">
                          <span style={{ width: `${p.progress_pct}%` }} />
                        </span>{" "}
                        {p.progress_pct}%
                      </>
                    )}
                  </td>
                  <td className={p.waiting ? "bad" : ""}>{p.waiting ?? 0}</td>
                  <td className="dim small">
                    {p.owner_email === you ? "you" : p.owner_email.split("@")[0]}
                    {p.member_emails.length > 0 &&
                      ` +${p.member_emails.length}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
