"use client";

import Link from "next/link";
import { useDashboard } from "@/lib/queries";

export default function ActivityPage() {
  const query = useDashboard();
  if (query.isPending) return <main className="shell"><p className="waiting">Loading activity…</p></main>;
  if (!query.data) return <main className="shell"><p className="error">Activity could not be loaded.</p></main>;
  return <main className="shell activity-page"><header className="page-heading"><div><p className="eyebrow">WORKSPACE HISTORY</p><h1>Activity</h1><p>Recent ingest, placement, review and comment actions across your projects.</p></div></header><div className="activity-list">{query.data.activity.map((row, index) => <Link key={`${row.at}-${index}`} href={row.scene && row.shot ? `/project/${row.project_id}?scene=${row.scene}&shot=${row.shot}` : `/project/${row.project_id}`}><time>{row.at ? new Date(row.at).toLocaleString() : ""}</time><span><b>{row.actor.split("@")[0] || "System"}</b><p>{row.verb.replaceAll("_", " ")}{row.detail ? ` · ${row.detail}` : ""}</p></span><i>Open →</i></Link>)}</div></main>;
}
