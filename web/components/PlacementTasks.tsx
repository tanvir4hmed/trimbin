"use client";

import Link from "next/link";
import { useDashboard } from "@/lib/queries";
import { paths } from "@/lib/slug";

export default function PlacementTasks({ projectId = 0 }: { projectId?: number }) {
  const dashboard = useDashboard();
  const tasks = (dashboard.data?.placements ?? []).filter((task) => !projectId || task.project_id === projectId);
  if (!tasks.length) return null;
  return <section className="placement-tasks" aria-label="Needs placement">
    <h2>Needs placement</h2>
    {tasks.map((task) => <Link className="placement-banner" key={task.project_id}
      href={paths.ingest(task.project_id, task.project_name)}>
      <span className="placement-banner-count">{task.count}</span>
      <span><b>{task.project_name}</b><small>Assign uploaded clips, then commit for shot review</small></span>
      <span>Open footage →</span>
    </Link>)}
  </section>;
}
