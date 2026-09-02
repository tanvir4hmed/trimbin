"use client";

/**
 * Adding a shoot day — and, because it is the same job, declaring where it goes.
 *
 * The scene and shot list used to live in the project rail, underneath the tree
 * of footage that had already arrived. Two menus in one narrow column: one
 * listing what exists, one a form for what is planned, with the form's
 * placeholders ("1B", "wide, Maya CU, reverse") reading as shots that did not
 * exist. They were not two views of one thing and they did not belong side by
 * side.
 *
 * Declaring structure belongs here, at the moment somebody needs a destination
 * to put footage into.
 */

import { use, useMemo } from "react";
import Link from "next/link";
import PlacementInbox from "@/components/PlacementInbox";
import Structure from "@/components/Structure";
import Upload from "@/components/Upload";
import { useProjectScreen } from "@/lib/queries";

export default function IngestPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const projectId = Number(id);
  const screen = useProjectScreen(projectId);

  // What actually arrived, so a planned shot with no footage is visibly
  // different from one that wrapped.
  const takesByShot = useMemo(() => {
    const counts = new Map<string, number>();
    for (const scene of screen.data?.tree.scenes ?? []) {
      for (const shot of scene.shots) counts.set(`${scene.scene}:${shot.shot}`, shot.takes);
    }
    return counts;
  }, [screen.data]);

  if (screen.isPending) {
    return (
      <main className="shell">
        <p className="waiting">Loading ingest workspace…</p>
      </main>
    );
  }
  if (screen.isError || !screen.data) {
    return (
      <main className="shell">
        <p className="error">Could not open ingest.</p>
      </main>
    );
  }

  const canCurate = screen.data.project.you_can_upload;

  return (
    <main className="ingest-page">
      <div className="ingest-page-crumb">
        <Link href={`/project/${projectId}`}>← {screen.data.project.name}</Link>
        <span>Footage ingest</span>
      </div>

      <Upload
        projectId={projectId}
        plan={screen.data.plan.scenes}
        canResolve={canCurate}
        onFinished={() => void screen.refetch()}
      />

      {canCurate && (
        <section className="ingest-plan">
          <header>
            <h2>Scenes and shots</h2>
            <p>
              Where footage can go. Declare them here, or let the slate sort
              clips into them.
            </p>
          </header>
          <Structure
            projectId={projectId}
            scenes={screen.data.plan.scenes}
            canEdit={canCurate}
            onChanged={() => void screen.refetch()}
            takesByShot={takesByShot}
          />
        </section>
      )}

      <PlacementInbox
        projectId={projectId}
        plan={screen.data.plan.scenes}
        canResolve={canCurate}
      />
    </main>
  );
}
