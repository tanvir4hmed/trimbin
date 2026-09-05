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

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import AskArchive from "@/components/AskArchive";
import PlacementBanner from "@/components/PlacementBanner";
import ProjectOverview from "@/components/ProjectOverview";
import ProjectTeam from "@/components/ProjectTeam";
import SceneTree from "@/components/SceneTree";
import ShotReviewCockpit from "@/components/ShotReviewCockpit";
import { ApiError } from "@/lib/api";
import { useProjectScreen } from "@/lib/queries";
import { paths } from "@/lib/slug";

export default function ProjectWorkspace({
  projectId,
  urlScene,
  urlShot,
}: {
  projectId: number;
  /** The scene in the path, or 0 for the production as a whole. */
  urlScene: number;
  /** The shot in the path, or 0 when no shot is open. */
  urlShot: number;
}) {
  const router = useRouter();
  // A search result links to a moment: which clip, and where in it. That is a
  // position inside the shot rather than another resource, so it stays a query
  // parameter while scene and shot became path segments.
  const query = useSearchParams();
  const deepLink = { clip: query.get("clip") ?? "", at: Number(query.get("at") ?? 0) };

  const [camera, setCamera] = useState("");
  const [shootDay, setShootDay] = useState("");
  const [assignee, setAssignee] = useState("");
  // Which scene the rail is showing. 0 is every scene, which is right for a
  // three-scene project and wrong for a thirty-scene one — so it is a choice
  // rather than a fixed answer.
  const [railScene, setRailScene] = useState(0);
  const [sceneQuery, setSceneQuery] = useState("");
  const [railTake, setRailTake] = useState(0);

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
  // Which shot the cockpit is on — or null, which means "show the production".
  //
  // This used to fall back to the first shot needing a person and, failing
  // that, simply the first shot. So opening a project dropped you into a
  // cockpit for a shot you had not chosen, with no view of what the project
  // contained. A shot is opened deliberately now: from the URL, or by picking
  // one.
  // Which shot the cockpit is on. The path says it; `selected` is the
  // in-page choice that has not been navigated to yet.
  const open = useMemo(() => {
    if (!tree) return null;
    if (!urlScene || !urlShot) return null;
    const asked = tree.scenes
      .find((s) => s.scene === urlScene)
      ?.shots.find((h) => h.shot === urlShot);
    return asked ? { scene: urlScene, shot: urlShot } : null;
  }, [tree, urlScene, urlShot]);

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
  const railScenes = useMemo(() => {
    if (!tree) return [];
    const wanted = railScene || urlScene;
    return wanted ? tree.scenes.filter((s) => s.scene === wanted) : tree.scenes;
  }, [tree, railScene, urlScene]);

  // Scenes matching what was typed, by number or by slugline.
  const searchedScenes = useMemo(() => {
    const q = sceneQuery.trim().toLowerCase();
    if (!q || !tree) return tree?.scenes ?? [];
    return tree.scenes.filter(
      (scene) =>
        String(scene.scene).includes(q) ||
        (scene.scene_code || "").toLowerCase().includes(q) ||
        (headings.get(scene.scene) || "").toLowerCase().includes(q),
    );
  }, [tree, sceneQuery, headings]);

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
          <Link className="crumb-project" href={`${paths.project(projectId, project?.name)}`}>
            <small>project</small>
            {project?.name ?? `Project ${projectId}`}
          </Link>
          {(open || urlScene) && (
            <>
              <span aria-hidden>›</span>
              {/* The scene is a choice, not a label. With one scene it read as
                  decoration; with several there was no way to move between them
                  from here at all. */}
              <label className="crumb-scene">
                <select
                  aria-label="Scene"
                  value={open?.scene ?? urlScene}
                  onChange={(event) => {
                    // Changing scene lands on the scene, not on a shot inside
                    // it that nobody picked.
                    setRailTake(0);
                    router.push(`${paths.scene(projectId, Number(event.target.value), project?.name)}`);
                  }}
                >
                  {tree.scenes.map((scene) => (
                    <option key={scene.scene} value={scene.scene}>
                      Scene {scene.scene_code || scene.scene}
                      {headings.get(scene.scene) ? ` · ${headings.get(scene.scene)}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              {open && (
                <>
                  <span aria-hidden>›</span>
                  <span className="crumb-shot">{openShot?.slug || `Shot ${open.shot}`}</span>
                  {/* Back to the scene, which otherwise needed the browser's
                      back button. */}
                  <button
                    type="button"
                    className="linkish crumb-close"
                    onClick={() => {
                      setRailTake(0);
                      router.push(`${paths.scene(projectId, open.scene, project?.name)}`);
                    }}
                  >
                    close shot
                  </button>
                </>
              )}
            </>
          )}
        </div>

        <div className="project-tools">
          {project && me && <ProjectTeam project={project} me={me} />}
          {open && (
            <Link className="ghost" href={`${paths.coverage(projectId, open.scene, project?.name)}`}>
              Play scene {open.scene}
            </Link>
          )}
          {canCurate ? (
            <Link className="primary" href={`${paths.ingest(projectId, project?.name)}`}>Upload takes</Link>
          ) : (
            me?.signed_in && (
              <span className="hint small">
                Read and comment only. <Link href="/home">Make a project</Link> to
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

      {/* A count and a route to the work, not the work itself. The whole inbox
          rendered here — every waiting clip with its slate frame and its three
          buttons — which is right for two clips and would bury the workspace
          under forty. Settling happens on the ingest page, once. */}
      <PlacementBanner projectId={projectId} />

      {!empty && (
        <AskArchive
          collapsible
          projectId={projectId}
          onOpen={(scene, shot, at, clipId) => router.push(`${paths.shot(projectId, scene, shot, project?.name)}${at !== undefined ? `?at=${at}` : ""}${clipId ? `${at !== undefined ? "&" : "?"}clip=${clipId}` : ""}`)}
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
          {!filtered && canCurate && <Link className="primary" href={`${paths.ingest(projectId, project?.name)}`}>Add scenes, shots &amp; footage</Link>}
        </div>
      ) : !open && !urlScene ? (
        // The production: its scenes. A scene is the unit people talk in.
        <ProjectOverview
          projectId={projectId}
          scenes={tree.scenes}
          headings={headings}
          canCurate={canCurate}
          scene={0}
        />
      ) : (
        <div className="workspace-split">
          <div className="rail">
            {/* Switching scene from the work, not only from the dashboard.
                Everything in this column belongs to one scene at a time, and
                the alternative was scrolling a flat list of every shot in the
                production to reach the next one. */}
            <div className="rail-scene">
              {tree.scenes.length > 6 && (
                // A dropdown is fine for six scenes and useless for sixty.
                <input
                  className="rail-scene-search"
                  type="search"
                  value={sceneQuery}
                  placeholder="Find a scene…"
                  onChange={(event) => setSceneQuery(event.target.value)}
                  aria-label="Find a scene"
                />
              )}
              <label>
                Scene
                <select
                  value={railScene}
                  onChange={(event) => setRailScene(Number(event.target.value))}
                >
                  <option value={0}>All scenes ({tree.scenes.length})</option>
                  {searchedScenes.map((scene) => (
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
                  href={`${paths.coverage(projectId, open.scene, project?.name)}`}
                >
                  Play
                </Link>
              )}
            </div>

            <SceneTree
              scenes={railScenes}
              selected={open}
              openTake={railTake}
              onSelect={(scene, shot) => { setRailTake(0); router.push(paths.shot(projectId, scene, shot, project?.name)); }}
              onSelectTake={(scene, shot, takeNo) => { setRailTake(takeNo); router.push(paths.shot(projectId, scene, shot, project?.name)); }}
              onOpenScene={(scene) => router.push(`${paths.coverage(projectId, scene, project?.name)}`)}
            />

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
                initialClipId={deepLink.clip}
                initialAt={deepLink.at}
                focusTake={railTake}
              />
            ) : (
              <ProjectOverview
                projectId={projectId}
                scenes={tree.scenes}
                headings={headings}
                canCurate={canCurate}
                scene={urlScene}
              />
            )}
          </section>
        </div>
      )}
    </main>
  );
}
