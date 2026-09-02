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
import PlacementInbox from "@/components/PlacementInbox";
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
  // Which scene the rail is showing. 0 is every scene, which is right for a
  // three-scene project and wrong for a thirty-scene one — so it is a choice
  // rather than a fixed answer.
  const [railScene, setRailScene] = useState(0);

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

  // The slugline lives on the plan, not on the tree — the tree is what footage
  // says exists, the plan is what the production declared.
  const headings = useMemo(
    () => new Map((data?.plan.scenes ?? []).map((s) => [s.scene, s.heading])),
    [data],
  );

  // What actually arrived, keyed the way the plan asks for it. The plan lists
  // what somebody intends to shoot; without this the two read as one list and
  // a scene nobody has shot looks identical to one that wrapped.
  const takesByShot = useMemo(() => {
    const counts = new Map<string, number>();
    for (const scene of tree?.scenes ?? []) {
      for (const shot of scene.shots) counts.set(`${scene.scene}:${shot.shot}`, shot.takes);
    }
    return counts;
  }, [tree]);

  const openScene = tree?.scenes.find((s) => s.scene === open?.scene);
  const openShot = openScene?.shots.find((s) => s.shot === open?.shot);

  // The rail's scenes, narrowed to one when a scene is chosen. The tree keeps
  // every shot of it; narrowing the column is about finding a scene quickly,
  // not about hiding work.
  const railScenes = useMemo(
    () =>
      !tree ? [] : railScene ? tree.scenes.filter((s) => s.scene === railScene) : tree.scenes,
    [tree, railScene],
  );

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
          {/* The way back is the list this project came from, not the home
              screen. The first crumb used to be Dashboard, which is a jump out
              of the production rather than a step up from the shot. */}
          <Link href={me?.signed_in ? "/projects" : "/"}>
            {me?.signed_in ? "Projects" : "Trimbin"}
          </Link>
          <span aria-hidden>›</span>
          {/* Labelled, because these productions are *named* after scenes —
              "Scene 2 - two perspectives" holding scene 1 put two different
              scene numbers side by side in one line and read as a fault.
              A link, because it is the step back from a shot to its project. */}
          <Link className="crumb-project" href={`/project/${projectId}`}>
            <small>project</small>
            {project?.name ?? `Project ${projectId}`}
          </Link>
          {open && (
            <>
              <span aria-hidden>›</span>
              <span className="crumb-shot">
                Scene {openScene?.scene_code || open.scene} ·{" "}
                {openShot?.slug || `Shot ${open.shot}`}
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

      {/* Draws nothing until a clip is actually waiting, so it costs an empty
          project nothing and cannot be missed on a project where ingest found
          a file in the wrong folder. */}
      <PlacementInbox
        projectId={projectId}
        plan={data.plan.scenes}
        canResolve={canCurate}
      />

      {!empty && (
        <AskArchive
          collapsible
          projectId={projectId}
          onOpen={(scene, shot, at, clipId) => router.push(`/project/${projectId}?scene=${scene}&shot=${shot}${at !== undefined ? `&at=${at}` : ""}${clipId ? `&clip=${clipId}` : ""}`)}
        />
      )}

      {empty ? (
        <div className="empty-project">
          <h2>{filtered ? "Nothing matches those filters" : "Nothing here yet"}</h2>
          {!filtered && (
            <p>
              Declare the scenes and shots, then upload into them — or upload
              first and let the slate sort the footage.
            </p>
          )}
          {!filtered && canCurate && <Link className="primary" href={`/project/${projectId}/ingest`}>Add scenes, shots &amp; footage</Link>}
        </div>
      ) : (
        <div className="workspace-split">
          <div className="rail">
            {/* Switching scene from the work, not only from the dashboard.
                Everything in this column belongs to one scene at a time, and
                the alternative was scrolling a flat list of every shot in the
                production to reach the next one. */}
            <div className="rail-scene">
              <label>
                Scene
                <select
                  value={railScene}
                  onChange={(event) => setRailScene(Number(event.target.value))}
                >
                  <option value={0}>All scenes ({tree.scenes.length})</option>
                  {tree.scenes.map((scene) => (
                    <option key={scene.scene} value={scene.scene}>
                      {scene.scene_code || `Scene ${scene.scene}`}
                      {headings.get(scene.scene) ? ` · ${headings.get(scene.scene)}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              {open && (
                <Link
                  className="ghost small"
                  href={`/project/${projectId}/scene/${open.scene}`}
                >
                  Play
                </Link>
              )}
            </div>

            <SceneTree
              scenes={railScenes}
              selected={open}
              onSelect={(scene, shot) => setSelected({ scene, shot })}
              onOpenScene={(scene) => router.push(`/project/${projectId}/scene/${scene}`)}
            />

            {canCurate && (
              // Declaring scenes and shots now lives with adding footage,
              // which is when a destination is actually needed. Two menus in
              // one column — a tree of what exists and a form for what is
              // planned — read as one confused list, and the form's placeholder
              // rows looked like real shots.
              <Link className="rail-plan-link" href={`/project/${projectId}/ingest`}>
                Add scenes, shots &amp; footage →
              </Link>
            )}
          </div>

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
