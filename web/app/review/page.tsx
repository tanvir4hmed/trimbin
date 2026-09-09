"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { currentIdentity } from "@/lib/auth";
import { useDashboard } from "@/lib/queries";
import { paths } from "@/lib/slug";
import { queueShotDisplayName } from "@/lib/labels";
import PlacementTasks from "@/components/PlacementTasks";

export default function ReviewQueuePage() {
  const router = useRouter();
  const projectId = Number(useSearchParams().get("project") || 0);
  const dashboard = useDashboard();
  useEffect(() => {
    if (!currentIdentity()) router.replace("/");
  }, [router]);
  if (dashboard.isPending)
    return (
      <main className="shell">
        <p className="waiting">Loading review queue…</p>
      </main>
    );
  if (dashboard.isError)
    return (
      <main className="shell">
        <p className="error">Could not load the review queue.</p>
      </main>
    );
  const queue = (dashboard.data?.queue ?? []).filter(
    (item) => !projectId || item.project_id === projectId,
  );
  // "Everything is settled" and "there is nothing here yet" are different
  // answers, and saying the first to somebody with an empty account describes
  // work they have never done.
  const projects = (dashboard.data?.projects ?? []).filter(
    (item) => !projectId || item.project_id === projectId,
  );
  const shotsExist = projects.some((project) => (project.shots ?? 0) > 0);
  const placementCount = (dashboard.data?.placements ?? [])
    .filter((task) => !projectId || task.project_id === projectId)
    .reduce((total, task) => total + task.count, 0);
  return (
    <main className="shell review-index">
      <header className="dash-top">
        <div>
          <p className="eyebrow">TEAM REVIEW</p>
          <h1>Review queue</h1>
          <p className="dim">
            Place footage, then review its shot and selected portions.
          </p>
        </div>
        <span className="review-total">{queue.length} shots · {placementCount} clips to place</span>
      </header>
      <PlacementTasks projectId={projectId} />
      {queue.length ? (
        <div className="review-queue">
          {queue.map((item, index) => (
            <Link
              href={`${paths.shot(item.project_id, item.scene, item.shot, item.project_name)}?clip=${encodeURIComponent(item.clip_id || "")}&review=1`}
              key={`${item.project_id}-${item.scene}-${item.shot}`}
            >
              <span className="queue-rank">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span>
                <b>{item.project_name}</b>
                <strong>
                  Scene {item.scene} / {queueShotDisplayName(item.scene, item.slug, item.shot)}
                </strong>
                <small>
                  {item.take_no ? `Take ${item.take_no} · ` : ""}{item.takes} takes · {item.reason.replaceAll("_", " ")}
                  {item.open_comments
                    ? ` · ${item.open_comments} open notes`
                    : ""}
                </small>
              </span>
              <span className={`queue-state ${item.state || "needs_review"}`}>
                {item.state?.replaceAll("_", " ") || "needs review"}
              </span>
              <i>Open cockpit →</i>
            </Link>
          ))}
        </div>
      ) : placementCount ? (
        <p className="hint">Assign and commit the clips above to begin shot review.</p>
      ) : shotsExist ? (
        <div className="first-run">
          <h2>Nothing needs you</h2>
          <p>Every shot is settled or already in somebody’s hands.</p>
          <Link className="ghost" href="/home">
            Back home
          </Link>
        </div>
      ) : projects.length ? (
        <div className="first-run">
          <h2>No footage yet</h2>
          <p>
            This queue fills itself as takes arrive. Upload a shoot day and the
            shots that need a person appear here.
          </p>
          <Link
            className="primary"
            href={`${paths.ingest(projects[0].project_id, projects[0].name)}`}
          >
            Add footage
          </Link>
        </div>
      ) : (
        <div className="first-run">
          <h2>No projects yet</h2>
          <p>
            Make a project, declare its scenes and shots, then upload the
            day&rsquo;s takes.
          </p>
          <Link className="primary" href="/home">
            Make a project
          </Link>
        </div>
      )}
    </main>
  );
}
