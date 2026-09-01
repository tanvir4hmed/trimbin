"use client";

import { use } from "react";
import Link from "next/link";
import PlacementInbox from "@/components/PlacementInbox";
import Upload from "@/components/Upload";
import { useProjectScreen } from "@/lib/queries";

export default function IngestPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const projectId = Number(id);
  const screen = useProjectScreen(projectId);
  if (screen.isPending) return <main className="shell"><p className="waiting">Loading ingest workspace…</p></main>;
  if (screen.isError || !screen.data) return <main className="shell"><p className="error">Could not open ingest.</p></main>;
  return <main className="ingest-page"><div className="ingest-page-crumb"><Link href={`/project/${projectId}`}>← {screen.data.project.name}</Link><span>Footage ingest</span></div><Upload projectId={projectId} plan={screen.data.plan.scenes} canResolve={screen.data.project.you_can_upload} /><PlacementInbox projectId={projectId} plan={screen.data.plan.scenes} canResolve={screen.data.project.you_can_upload} /></main>;
}
