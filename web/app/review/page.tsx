"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { currentIdentity } from "@/lib/auth";
import { useDashboard } from "@/lib/queries";

export default function ReviewQueuePage() {
  const router = useRouter();
  const dashboard = useDashboard();
  useEffect(() => { if (!currentIdentity()) router.replace("/"); }, [router]);
  if (dashboard.isPending) return <main className="shell"><p className="waiting">Loading review queue…</p></main>;
  if (dashboard.isError) return <main className="shell"><p className="error">Could not load the review queue.</p></main>;
  const queue = dashboard.data?.queue ?? [];
  return <main className="shell review-index">
    <header className="dash-top"><div><p className="eyebrow">TEAM REVIEW</p><h1>Shots that need a person</h1><p className="dim">Open a shot in the full cockpit. Decisions are never made from a two-card shortcut.</p></div><span className="review-total">{queue.length} waiting</span></header>
    {queue.length ? <div className="review-queue">{queue.map((item, index) => <Link href={`/project/${item.project_id}?scene=${item.scene}&shot=${item.shot}`} key={`${item.project_id}-${item.scene}-${item.shot}`}><span className="queue-rank">{String(index + 1).padStart(2, "0")}</span><span><b>{item.project_name}</b><strong>Scene {item.scene} / {item.slug || `Shot ${item.shot}`}</strong><small>{item.takes} takes · {item.reason.replaceAll("_", " ")}{item.open_comments ? ` · ${item.open_comments} open notes` : ""}</small></span><span className={`queue-state ${item.state || "needs_review"}`}>{item.state?.replaceAll("_", " ") || "needs review"}</span><i>Open cockpit →</i></Link>)}</div> : <div className="first-run"><h2>Nothing needs you</h2><p>Every shot is settled or already in somebody’s hands.</p><Link className="ghost" href="/dashboard">Back home</Link></div>}
  </main>;
}
