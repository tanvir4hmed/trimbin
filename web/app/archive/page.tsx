"use client";

/**
 * The archive, as a screen of its own.
 *
 * The question box has lived inside a project until now, which is the wrong
 * scope for most of the questions worth asking. "Which takes did we reject for
 * continuity?" is not a question about one production — it is the question that
 * makes an archive worth keeping, and it needs somewhere to be asked from.
 *
 * A project has to be chosen because the search is scoped to one: reading across
 * every production somebody can open would mean a query that widens with the
 * company and answers slower every month. The picker is the scope, said out
 * loud.
 */

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import AskArchive from "@/components/AskArchive";
import type { Project } from "@/lib/api";
import { ApiError, api } from "@/lib/api";
import { currentIdentity } from "@/lib/auth";

export default function ArchivePage() {
  return (
    <Suspense
      fallback={
        <main className="shell">
          <p className="waiting">Loading.</p>
        </main>
      }
    >
      <Archive />
    </Suspense>
  );
}

function Archive() {
  const router = useRouter();
  const search = useSearchParams();
  const asked = search.get("q") ?? undefined;

  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const found = await api.projects();
      setProjects(found.projects);
      // The project with the most in it, rather than the newest. A search box
      // pointed at an empty project answers "no match" to every question and
      // reads as a broken feature.
      setProjectId(found.projects[0]?.project_id ?? null);
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
          <h1>Archive</h1>
          <p className="dim">
            Every take ever considered, every measurement, every reason, every
            override — with the query that found them.
          </p>
        </div>
        {projects.length > 1 && (
          <label className="picker">
            <span>In</span>
            <select
              value={projectId ?? ""}
              onChange={(e) => setProjectId(Number(e.target.value))}
            >
              {projects.map((p) => (
                <option key={p.project_id} value={p.project_id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </header>

      {error && <p className="error">{error}</p>}

      {projectId === null ? (
        <p className="hint">
          Nothing to search yet. Make a project and put some footage in it, or{" "}
          <Link href="/project/1">open one of ours</Link>.
        </p>
      ) : (
        <AskArchive
          // Remounts when the project changes, so an answer about one
          // production never sits under the name of another.
          key={`${projectId}-${asked ?? ""}`}
          projectId={projectId}
          initialQuestion={asked}
          onOpen={(scene, shot, at, clipId) =>
            router.push(`/project/${projectId}?scene=${scene}&shot=${shot}${at !== undefined ? `&at=${at}` : ""}${clipId ? `&clip=${clipId}` : ""}`)
          }
        />
      )}

      <section className="block">
        <h2>What it can answer</h2>
        <p className="dim">
          The reply carries the SQL that ran, every time. A result somebody can
          check is worth more than one they have to trust, and that is the
          argument this whole system rests on.
        </p>
      </section>
    </main>
  );
}
