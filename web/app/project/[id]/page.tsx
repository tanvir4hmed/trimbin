"use client";

/**
 * One production: the tree on the left, one shot open on the right.
 *
 * Reachable without an account when the project is public, because the argument
 * of this system is checkable and an argument you have to sign in to read is not
 * much of one. What changes with sign-in is what is *possible*, never what is
 * visible: a guest sees the upload button and is told why it is off, rather than
 * being sent somewhere the real users never go.
 *
 * The filters across the top are the axes a real bin is cut on — scene, camera,
 * shoot day, and who is on it. A tree with one axis cannot answer "everything
 * from Tuesday" or "everything on the B camera", and both are ordinary Monday
 * questions.
 */

import { use, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import AskArchive from "@/components/AskArchive";
import SceneTree from "@/components/SceneTree";
import ShotDetail from "@/components/ShotDetail";
import Structure from "@/components/Structure";
import Upload from "@/components/Upload";
import type { Me, PlannedScene, Project, Tree } from "@/lib/api";
import { ApiError, api } from "@/lib/api";

export default function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const projectId = Number(id);
  const router = useRouter();
  const search = useSearchParams();

  const [tree, setTree] = useState<Tree | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [selected, setSelected] = useState<{ scene: number; shot: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [plan, setPlan] = useState<PlannedScene[]>([]);

  const [camera, setCamera] = useState("");
  const [shootDay, setShootDay] = useState("");
  const [assignee, setAssignee] = useState("");

  const load = useCallback(async () => {
    setError(null);
    try {
      const found = await api.tree(projectId, {
        camera: camera || undefined,
        shoot_day: shootDay || undefined,
        assignee: assignee || undefined,
      });
      setTree(found);

      // A link from the dashboard names the shot it was about. Honouring it is
      // the difference between a queue that takes you somewhere and one that
      // takes you to a project and leaves you to find the row again.
      const wantScene = Number(search.get("scene"));
      const wantShot = Number(search.get("shot"));
      const asked =
        wantScene && wantShot
          ? found.scenes
              .find((s) => s.scene === wantScene)
              ?.shots.find((h) => h.shot === wantShot)
          : undefined;

      if (asked) {
        setSelected({ scene: wantScene, shot: wantShot });
        return;
      }

      // Otherwise open the first thing that needs a person, not the first thing
      // in the list. The point of the queue is that it puts the work in front
      // of you.
      const waiting = found.scenes
        .flatMap((s) => s.shots.map((x) => ({ scene: s.scene, ...x })))
        .find(
          (s) =>
            s.status === "differs_from_circle" ||
            s.status === "needs_review" ||
            s.status === "not_judged",
        );
      const first = found.scenes[0]?.shots[0];
      setSelected(
        waiting
          ? { scene: waiting.scene, shot: waiting.shot }
          : first
            ? { scene: found.scenes[0].scene, shot: first.shot }
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
  }, [projectId, camera, shootDay, assignee, search]);

  useEffect(() => {
    void load();
  }, [load]);

  // Asked rather than worked out. A page that decides whether to draw the
  // upload button by comparing an address against a list is a second
  // implementation of the permission rules, and the two will disagree.
  const loadPlan = useCallback(() => {
    void api
      .plan(projectId)
      .then((p) => setPlan(p.scenes))
      .catch(() => setPlan([]));
  }, [projectId]);

  useEffect(() => {
    void api.me().then(setMe).catch(() => setMe(null));
    void api
      .project(projectId)
      .then(setProject)
      .catch(() => setProject(null));
    loadPlan();
  }, [projectId, loadPlan]);

  const teamEmails = useMemo(
    () =>
      project
        ? [project.owner_email, ...project.member_emails].filter(Boolean)
        : [],
    [project],
  );

  const canComment = Boolean(me?.signed_in);
  // Running the panel, describing a shot, circling, assigning, statusing.
  // The same predicate the API uses for uploading, and told by the API rather
  // than worked out here — a page that decides this by comparing addresses is a
  // second implementation of the rules, and the two will disagree.
  const canCurate = Boolean(project?.you_can_upload);
  const canUpload = canCurate;

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
          {selected && (
            <>
              <span aria-hidden>›</span>
              <span>
                Scene {selected.scene} · Shot {selected.shot}
              </span>
            </>
          )}
        </div>

        <div className="project-tools">
          {selected && (
            <Link
              className="ghost"
              href={`/project/${projectId}/scene/${selected.scene}`}
            >
              Play scene {selected.scene}
            </Link>
          )}
          {canUpload ? (
            <button
              type="button"
              className="primary"
              onClick={() => setUploading((v) => !v)}
            >
              {uploading ? "Close" : "Upload takes"}
            </button>
          ) : (
            me?.signed_in && (
              <span className="hint small">
                Read and comment only. <Link href="/dashboard">Make a project</Link>{" "}
                to upload.
              </span>
            )
          )}
        </div>
      </header>

      {uploading && canUpload && (
        <>
          <Structure
            projectId={projectId}
            scenes={plan}
            canEdit={canCurate}
            onChanged={loadPlan}
          />
          <Upload
            projectId={projectId}
            plan={plan}
            onFinished={() => {
              void load();
              loadPlan();
            }}
          />
        </>
      )}

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
              <select
                value={shootDay}
                onChange={(e) => setShootDay(e.target.value)}
              >
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
            <select
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
            >
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
          onOpen={(scene, shot) => setSelected({ scene, shot })}
        />
      )}

      {empty ? (
        <div className="empty-project">
          <h2>{filtered ? "Nothing matches those filters" : "Nothing here yet"}</h2>
          {!filtered && <p>Drop a shoot folder to begin.</p>}
          {!filtered && canUpload && !uploading && (
            <>
              <Structure
                projectId={projectId}
                scenes={plan}
                canEdit={canCurate}
                onChanged={loadPlan}
              />
              <Upload
                projectId={projectId}
                plan={plan}
                onFinished={() => {
                  void load();
                  loadPlan();
                }}
              />
            </>
          )}
        </div>
      ) : (
        <div className="workspace-split">
          <SceneTree
            scenes={tree.scenes}
            selected={selected}
            onSelect={(scene, shot) => setSelected({ scene, shot })}
            onOpenScene={(scene) =>
              router.push(`/project/${projectId}/scene/${scene}`)
            }
          />

          <section className="pane">
            {selected ? (
              <ShotDetail
                // Remounts when the shot changes, so no state leaks between
                // two shots — an expanded take from the last one staying open
                // over a different take's findings is a real confusion.
                key={`${selected.scene}-${selected.shot}`}
                projectId={projectId}
                scene={selected.scene}
                shot={selected.shot}
                canComment={canComment}
                canCurate={canCurate}
                you={me?.email ?? ""}
                teamEmails={teamEmails}
                onDecided={() => void load()}
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
