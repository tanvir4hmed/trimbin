"use client";

/** One shot: the review cockpit. */

import { use } from "react";
import ProjectWorkspace from "@/components/ProjectWorkspace";
import { projectIdFromSlug } from "@/lib/slug";

export default function ShotPage({
  params,
}: {
  params: Promise<{ slug: string; scene: string; shot: string }>;
}) {
  const { slug, scene, shot } = use(params);
  return (
    <ProjectWorkspace
      projectId={projectIdFromSlug(slug)}
      urlScene={Number(scene) || 0}
      urlShot={Number(shot) || 0}
    />
  );
}
