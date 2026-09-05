"use client";

import Link from "next/link";
import { useDashboard } from "@/lib/queries";
import { paths } from "@/lib/slug";
import { archiveLocal } from "@/lib/time";

export default function ActivityPage() {
  const query = useDashboard();
  if (query.isPending) return <main className="shell"><p className="waiting">Loading activity…</p></main>;
  if (!query.data) return <main className="shell"><p className="error">Activity could not be loaded.</p></main>;
  return <main className="shell activity-page"><header className="page-heading"><div><p className="eyebrow">WORKSPACE HISTORY</p><h1>Activity</h1><p>Recent ingest, placement, review and comment actions across your projects.</p></div></header><div className="activity-list">{query.data.activity.map((row, index) => <Link key={`${row.at}-${index}`} href={row.scene && row.shot ? `${paths.shot(row.project_id, row.scene, row.shot, row.project_name)}` : `${paths.project(row.project_id, row.project_name)}`}><time>{row.at ? archiveLocal(row.at) : ""}</time><span><b>{row.actor.split("@")[0] || "System"}</b><p>{row.verb.replaceAll("_", " ")}{row.detail ? ` · ${row.detail}` : ""}</p></span><i>Open →</i></Link>)}</div></main>;
}
