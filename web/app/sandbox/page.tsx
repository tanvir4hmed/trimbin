"use client";

/**
 * The page for someone with three minutes and no account.
 *
 * Upload at the top, and whatever the pipeline made of it directly below. The
 * two are on one page rather than two on purpose: a visitor who has to navigate
 * to see the result usually does not, and the result is the whole argument.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import SandboxUpload from "@/components/SandboxUpload";
import SceneTree from "@/components/SceneTree";
import ShotDetail from "@/components/ShotDetail";
import type { Tree } from "@/lib/api";
import { ApiError, api } from "@/lib/api";

interface Limits {
  project_id: number;
  max_clips: number;
  max_seconds: number;
  retention_hours: number;
}

export default function SandboxPage() {
  const [limits, setLimits] = useState<Limits | null>(null);
  const [tree, setTree] = useState<Tree | null>(null);
  const [selected, setSelected] = useState<{ scene: number; setup: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadTree = useCallback(
    async (projectId: number) => {
      try {
        const found = await api.tree(projectId);
        setTree(found);
        const first = found.scenes[0]?.setups[0];
        if (first && !selected) {
          setSelected({ scene: found.scenes[0].scene, setup: first.setup });
        }
      } catch (e) {
        if (e instanceof ApiError && e.waking) {
          setError("The archive is waking up. It sleeps when nobody is using it.");
        }
        // Anything else is not worth showing here. An empty sandbox and a
        // failed read look the same to a visitor, and the empty case is far
        // more likely — they have not uploaded anything yet.
      }
    },
    [selected],
  );

  useEffect(() => {
    api
      .sandboxLimits()
      .then((l) => {
        setLimits(l);
        void loadTree(l.project_id);
      })
      .catch(() => setError("Could not reach the sandbox."));
    // Deliberately once. loadTree changes identity with `selected`, and
    // depending on it here would refetch the tree every time someone clicks a
    // different setup.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!limits) {
    return (
      <main className="shell">
        <p className="waiting">{error ?? "Loading…"}</p>
      </main>
    );
  }

  const hasFootage = tree !== null && tree.scenes.length > 0;

  return (
    <main className="shell">
      <section style={{ paddingTop: 48 }}>
        <span className="eyebrow">No account needed</span>
        <h1>Put your own takes through it</h1>
        <p className="lede">
          Shoot the same shot two or three times on a phone — same framing, and
          change one thing between takes. Trimbin measures each one, reads a
          slate if there is one, compares them, and shows you which part of each
          is safe to use and why it preferred one.
        </p>
      </section>

      <SandboxUpload
        projectId={limits.project_id}
        limits={{ clips: limits.max_clips, seconds: limits.max_seconds }}
        onFinished={() => void loadTree(limits.project_id)}
      />

      {hasFootage && (
        <section>
          <h2>What is in the sandbox now</h2>
          <p className="dim small">
            Shared, and swept every hour — anything older than{" "}
            {limits.retention_hours} hours is gone, including yours. For work you
            want to keep,{" "}
            <Link href="/project/1">a real project</Link> is the place.
          </p>

          <div className="workspace-split" style={{ marginTop: 18 }}>
            <SceneTree
              scenes={tree.scenes}
              selected={selected}
              onSelect={(scene, setup) => setSelected({ scene, setup })}
            />
            <section className="pane">
              {selected && (
                <ShotDetail
                  key={`${selected.scene}-${selected.setup}`}
                  projectId={limits.project_id}
                  scene={selected.scene}
                  setup={selected.setup}
                  // The sandbox takes writes from anyone. That is what it is
                  // for, and its limits are enforced by the API rather than by
                  // hiding the buttons.
                  canEdit
                  onDecided={() => void loadTree(limits.project_id)}
                />
              )}
            </section>
          </div>
        </section>
      )}

      {!hasFootage && (
        <section>
          <p className="dim small">
            Nothing in the sandbox at the moment. Upload something above, or{" "}
            <Link href="/project/1">look at the demo project</Link> — twelve
            takes from a published dataset, already measured and compared.
          </p>
        </section>
      )}
    </main>
  );
}
