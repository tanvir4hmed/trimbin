"use client";

/**
 * A production: its scenes.
 *
 * The slug carries the name for the person reading the address bar and the id
 * for the router. See `lib/slug.ts` — a renamed project still opens from every
 * link ever shared, because only the trailing number resolves.
 */

import { use } from "react";
import ProjectWorkspace from "@/components/ProjectWorkspace";
import { projectIdFromSlug } from "@/lib/slug";

export default function ProjectPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  return <ProjectWorkspace projectId={projectIdFromSlug(slug)} urlScene={0} urlShot={0} />;
}
