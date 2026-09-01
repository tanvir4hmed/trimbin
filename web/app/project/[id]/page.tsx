"use client";

/**
 * One production: the tree on the left, one shot open on the right.
 *
 * One request. It made four — the tree, the project record, the shot plan, and
 * the caller's capabilities — each with its own loading state and its own
 * opinion about who you are, assembled here with the last one winning.
 *
 * Reachable without an account when the project is public. What changes with
 * sign-in is what is *possible*, never what is visible.
 */

import { use, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import AskArchive from "@/components/AskArchive";
import SceneTree from "@/components/SceneTree";
import ShotReviewCockpit from "@/components/ShotReviewCockpit";
import { ApiError } from "@/lib/api";
import { useProjectScreen } from "@/lib/queries";

export default function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const projectId = Number(id);
  const router = useRouter();
  const search = useSearchParams();

  const [selected, setSelected] = useState<{ scene: number; shot: number } | null>(null);
  const [camera, setCamera] = useState("");
  const [shootDay, setShootDay] = useState("");
  const [assignee, setAssignee] = useState("");

  const screen = useProjectScreen(projectId, {
    camera: camera || undefined,
    shoot_day: shootDay || undefined,
    assignee: assignee || undefined,
  });

  const data = screen.data;
  const tree = data?.tree;
  const project = data?.project;
  const me = data?.me;

  const teamEmails = useMemo(
    () =>
      project ? [project.owner_email, ...project.member_emails].filter(Boolean) : [],
    [project],
  );

  // What to open, derived rather than stored. A link from the queue names a
  // shot; otherwise the first thing that needs a person, because the point of
  // the queue is that it puts the work in front of you.
  const open = useMemo(() => {
    if (!tree) return null;
    if (selected) return selected;

    const wantScene = Number(search.get("scene"));
    const wantShot = Number(search.get("shot"));
    const asked =
      wantScene && wantShot
        ? tree.scenes.find((s) => s.scene === wantScene)?.shots.find((h) => h.shot === wantShot)
        : undefined;
    if (asked) return { scene: wantScene, shot: wantShot };

    const waiting = tree.scenes
      .flatMap((s) => s.shots.map((x) => ({ scene: s.scene, ...x })))
      .find(
        (s) =>
          s.status === "differs_from_circle" ||
          s.status === "needs_review" ||
          s.status === "not_judged",
      );
    if (waiting) return { scene: waiting.scene, shot: waiting.shot };

    const first = tree.scenes[0]?.shots[0];
    return first ? { scene: tree.scenes[0].scene, shot: first.shot } : null;
  }, [tree, selected, search]);

  const canComment = Boolean(me?.signed_in);
  // Told by the API rather than worked out here. A page that decides this by
  // comparing addresses is a second implementation of the permission rules.
  const canCurate = Boolean(project?.you_can_upload);

  if (screen.isPending) {
    return (
      <main className="workspace">
        <p className="waiting">Loading — the archive may be waking up.</p>
      </main>
    );
  }

  if (screen.isError) {
    const error = screen.error;
    const message =
      error instanceof ApiError && error.status === 401
        ? "Sign in to open this project."
        : error instanceof ApiError && error.status === 404
          ? "No such project."
          : error instanceof ApiError && error.waking
            ? "The archive is still waking up. It sleeps when nobody is using it."
            : "Could not load this project.";
    return (
      <main className="workspace">
        <p className="error">{message}</p>
        <Link href="/">Back</Link>
      </main>
    );
  }

  if (!data || !tree) return null;

  const empty = tree.scenes.length === 0;
  const filtered = Boolean(camera || shootDay || assignee);

  return (
    <main className="workspace">
      <header className="project-head">
        <div className="crumbs">
          <Link href={me?.signed_in ? "/dashboard" : "/"}>
            {me?.signed_in ? "Dashboard" : "Trimbin"}
          </Link>
          <span aria-hidden>›</span>
          <span>{project?.name ?? `Project ${projectId}`}</span>
          {open && (
            <>
              <span aria-hidden>›</span>
              <span>
                Scene {open.scene} · Shot {open.shot}
              </span>
            </>
          )}
        </div>

        <div className="project-tools">
          {open && (
            <Link className="ghost" href={`/project/${projectId}/scene/${open.scene}`}>
              Play scene {open.scene}
            </Link>
          )}
          {canCurate ? (
            <Link className="primary" href={`/project/${projectId}/ingest`}>Upload takes</Link>
          ) : (
            me?.signed_in && (
              <span className="hint small">
                Read and comment only. <Link href="/dashboard">Make a project</Link> to
                upload.
              </span>
            )
          )}
        </div>
      </header>

      {!empty && (
        <div className="filters">
          {tree.cameras.length > 0 && (
            <label>
              Camera
              <select value={camera} onChange={(e) => setCamera(e.target.value)}>
                <option value="">all</option>
                {tree.cameras.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
          )}
          {tree.shoot_days.length > 1 && (
            <label>
              Shoot day
              <select value={shootDay} onChange={(e) => setShootDay(e.target.value)}>
                <option value="">all</option>
                {tree.shoot_days.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            Assigned
            <select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
              <option value="">anyone</option>
              <option value="unassigned">unclaimed</option>
              {me?.email && <option value={me.email}>me</option>}
              {teamEmails
                .filter((t) => t !== me?.email)
                .map((t) => (
                  <option key={t} value={t}>
                    {t.split("@")[0]}
                  </option>
                ))}
            </select>
          </label>
          {filtered && (
            <button
              type="button"
              className="linkish"
              onClick={() => {
                setCamera("");
                setShootDay("");
                setAssignee("");
              }}
            >
              clear
            </button>
          )}
        </div>
      )}

      {!empty && (
        <AskArchive
          projectId={projectId}
          onOpen={(scene, shot, at, clipId) => router.push(`/project/${projectId}?scene=${scene}&shot=${shot}${at !== undefined ? `&at=${at}` : ""}${clipId ? `&clip=${clipId}` : ""}`)}
        />
      )}

      {empty ? (
        <div className="empty-project">
          <h2>{filtered ? "Nothing matches those filters" : "Nothing here yet"}</h2>
          {!filtered && <p>Drop a shoot folder to begin.</p>}
          {!filtered && canCurate && <Link className="primary" href={`/project/${projectId}/ingest`}>Add footage</Link>}
        </div>
      ) : (
        <div className="workspace-split">
          <SceneTree
            scenes={tree.scenes}
            selected={open}
            onSelect={(scene, shot) => setSelected({ scene, shot })}
            onOpenScene={(scene) => router.push(`/project/${projectId}/scene/${scene}`)}
          />

          <section className="pane">
            {open ? (
              <ShotReviewCockpit
                // Remounts when the shot changes, so no state leaks between two
                // shots — an expanded take from the last one staying open over a
                // different take's findings is a real confusion.
                key={`${open.scene}-${open.shot}`}
                projectId={projectId}
                scene={open.scene}
                shot={open.shot}
                canComment={canComment}
                canCurate={canCurate}
                you={me?.email ?? ""}
                teamEmails={teamEmails}
                initialClipId={search.get("clip") ?? ""}
                initialAt={Number(search.get("at") ?? 0)}
              />
            ) : (
              <p className="hint">Choose a shot.</p>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
