"use client";

/** One scene: its shots. */

import { use } from "react";
import ProjectWorkspace from "@/components/ProjectWorkspace";
import { projectIdFromSlug } from "@/lib/slug";

export default function ScenePage({
  params,
}: {
  params: Promise<{ slug: string; scene: string }>;
}) {
  const { slug, scene } = use(params);
  return (
    <ProjectWorkspace
      projectId={projectIdFromSlug(slug)}
      urlScene={Number(scene) || 0}
      urlShot={0}
    />
  );
}
