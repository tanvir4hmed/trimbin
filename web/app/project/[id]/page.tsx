"use client";

/**
 * The workspace: the tree on the left, one setup open on the right.
 *
 * Reachable without an account when the project is public, because the demo is
 * the argument and an argument you have to sign in to read is not much of one.
 * Everything that writes is gated; everything that looks is not.
 */

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import AskArchive from "@/components/AskArchive";
import SceneTree from "@/components/SceneTree";
import ShotDetail from "@/components/ShotDetail";
import type { Project, Tree } from "@/lib/api";
import { ApiError, api } from "@/lib/api";
import { currentIdentity } from "@/lib/auth";

export default function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const projectId = Number(id);

  const [tree, setTree] = useState<Tree | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [selected, setSelected] = useState<{ scene: number; setup: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [canEdit, setCanEdit] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const found = await api.tree(projectId);
      setTree(found);

      // Open the first thing that needs a person, not the first thing in the
      // list. The point of the queue is that it puts the work in front of you.
      const waiting = found.scenes
        .flatMap((s) => s.setups.map((x) => ({ scene: s.scene, ...x })))
        .find((s) => s.status === "needs_review" || s.status === "not_judged");
      const first = found.scenes[0]?.setups[0];
      setSelected(
        waiting
          ? { scene: waiting.scene, setup: waiting.setup }
          : first
            ? { scene: found.scenes[0].scene, setup: first.setup }
            : null,
      );
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setError("Sign in to open this project.");
      } else if (e instanceof ApiError && e.status === 404) {
        setError("No such project.");
      } else if (e instanceof ApiError && e.waking) {
        setError(
          "The archive is still waking up. It sleeps when nobody is using it.",
        );
      } else {
        setError(e instanceof Error ? e.message : "Could not load this project.");
      }
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Membership decides what is writable. Asked separately from the tree because
  // a public project is readable by people who may not touch it, and drawing
  // an override button they cannot use is worse than drawing none.
  useEffect(() => {
    if (!currentIdentity()) {
      setCanEdit(false);
      setProject(null);
      return;
    }
    void api
      .projects()
      .then(({ projects }) => {
        const mine = projects.find((p) => p.project_id === projectId) ?? null;
        setProject(mine);
        setCanEdit(mine !== null);
      })
      .catch(() => setCanEdit(false));
  }, [projectId]);

  if (loading) {
    return (
      <main className="workspace">
        <p className="waiting">Loading — the archive may be waking up.</p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="workspace">
        <p className="error">{error}</p>
        <Link href="/">Back</Link>
      </main>
    );
  }

  const empty = !tree || tree.scenes.length === 0;

  return (
    <main className="workspace">
      <div className="crumbs">
        <Link href="/">Trimbin</Link>
        <span aria-hidden>›</span>
        <span>{project?.name ?? `Project ${projectId}`}</span>
        {selected && (
          <>
            <span aria-hidden>›</span>
            <span>
              Scene {selected.scene} · Setup {selected.setup}
            </span>
          </>
        )}
      </div>

      {!empty && (
        <AskArchive
          projectId={projectId}
          onOpen={(scene, setup) => setSelected({ scene, setup })}
        />
      )}

      {empty ? (
        <div className="empty-project">
          <h2>Nothing here yet</h2>
          <p>
            Drop a folder of takes to begin. Every clip is measured, read and
            compared against the others of its setup.
          </p>
          {!canEdit && (
            <p className="hint">
              You are looking at this project without being a member of it, so
              nothing here is editable.
            </p>
          )}
        </div>
      ) : (
        <div className="workspace-split">
          <SceneTree
            scenes={tree.scenes}
            selected={selected}
            onSelect={(scene, setup) => setSelected({ scene, setup })}
          />

          <section className="pane">
            {selected ? (
              <ShotDetail
                // Remounts when the setup changes, so no state leaks between
                // two shots — an expanded take from the last one staying open
                // over a different take's findings is a real confusion.
                key={`${selected.scene}-${selected.setup}`}
                projectId={projectId}
                scene={selected.scene}
                setup={selected.setup}
                canEdit={canEdit}
                onDecided={() => void load()}
              />
            ) : (
              <p className="hint">Choose a setup.</p>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
