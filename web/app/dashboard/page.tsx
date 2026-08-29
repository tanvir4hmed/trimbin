"use client";

/**
 * Your work: the projects, and how much of each needs a person.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import NewProject from "@/components/NewProject";
import type { Dashboard } from "@/lib/api";
import { ApiError, api } from "@/lib/api";
import { currentIdentity } from "@/lib/auth";

const THUMBS = [
  "linear-gradient(135deg,#3a3226,#17140f)",
  "linear-gradient(135deg,#2a2f3a,#17140f)",
  "linear-gradient(135deg,#2c3a2e,#17140f)",
  "linear-gradient(135deg,#332a30,#17140f)",
];

function ago(iso: string | null): string {
  if (!iso) return "";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days}d ago`;
}

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.dashboard());
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        router.replace("/");
        return;
      }
      setError(
        e instanceof ApiError && e.waking
          ? "The archive is waking up."
          : e instanceof Error
            ? e.message
            : "Could not load your work.",
      );
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

  if (loading) return <main className="shell"><p className="waiting">Loading.</p></main>;

  if (error) {
    return (
      <main className="shell">
        <p className="error">{error}</p>
        <button type="button" className="ghost" onClick={() => void load()}>
          Try again
        </button>
      </main>
    );
  }

  if (!data) return null;

  const waiting = data.totals.waiting;

  return (
    <main className="shell dash">
      <div className="dash-top">
        <div>
          <h1>Your work</h1>
          <p className="dim">
            {data.projects.length} project{data.projects.length === 1 ? "" : "s"}
            {waiting > 0 && ` · ${waiting} shot${waiting === 1 ? "" : "s"} need you`}
          </p>
        </div>
        <div className="dash-actions">
          {waiting > 0 && (
            <Link href="/review" className="primary">
              Review {waiting}
            </Link>
          )}
          <NewProject
            limits={data.limits}
            role={data.role}
            owned={data.projects.filter((p) => p.you_are_owner).length}
            onCreated={(id) => router.push(`/project/${id}`)}
          />
        </div>
      </div>

      {data.projects.length === 0 ? (
        <div className="first-run">
          <h2>No projects yet</h2>
          <p>Make one and drop a shoot folder into it.</p>
        </div>
      ) : (
        <div className="pgrid">
          {data.projects.map((p, i) => (
            <Link key={p.project_id} href={`/project/${p.project_id}`} className="pcard">
              <div className="pthumb" style={{ background: THUMBS[i % THUMBS.length] }}>
                <span className="ptag">
                  {p.you_can_upload ? "yours" : "read & comment"}
                </span>
              </div>
              <div className="pinfo">
                <div className="pname">{p.name}</div>
                <div className="pmeta">
                  Scene · Shot · Take
                  {p.progress_pct !== null && ` · ${p.progress_pct}% settled`}
                </div>
                <div className="pstats">
                  <div className="st">
                    <span className="stn">{p.takes}</span>
                    <span className="stl">clips</span>
                  </div>
                  <div className="st">
                    <span className="stn">{p.shots}</span>
                    <span className="stl">shots</span>
                  </div>
                  <div className="st">
                    <span
                      className="stn"
                      style={{ color: p.waiting ? "var(--amber)" : "var(--faint)" }}
                    >
                      {p.waiting}
                    </span>
                    <span className="stl">need you</span>
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}

      {data.recent.length > 0 && (
        <section className="block">
          <div className="sect">Recent decisions</div>
          <ul className="activity">
            {data.recent.slice(0, 6).map((r, i) => (
              <li key={i}>
                <Link href={`/project/${r.project_id}?scene=${r.scene}&shot=${r.shot}`}>
                  <span className="who">
                    {r.decided_by === "human" ? r.actor.split("@")[0] : "Panel"}
                  </span>{" "}
                  <span className="what">take {r.take_no}</span>{" "}
                  <span className="where">
                    {r.project_name} · scene {r.scene}, shot {r.shot}
                  </span>
                </Link>
                <span className="ago">{ago(r.decided_at)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
