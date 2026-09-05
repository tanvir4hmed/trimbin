"use client";

/**
 * A production, one level at a time.
 *
 * Projects lists productions. This lists a production's scenes, and then one
 * scene's shots. A shot opens the cockpit.
 *
 * It listed every shot of every scene at once to begin with, which is the same
 * mistake as opening straight into a cockpit, one step later: a page that
 * answers "what is in here" by showing all of it stops answering anything once
 * a production has forty shots. A scene is the unit people talk in — "how far
 * are we on scene 12" — so it is the unit this steps through.
 */

import Link from "next/link";
import type { SceneNode, ShotNode, ShotStatus } from "@/lib/api";
import { paths } from "@/lib/slug";

const STATUS_LABEL: Record<ShotStatus, string> = {
  too_few_takes: "choose a range",
  not_judged: "not compared",
  needs_review: "needs you",
  differs_from_circle: "differs from the circle",
  decided: "decided",
  confirmed: "settled",
};

/** Whether a shot still wants a person — the rule the queue and rail use. */
function unsettled(shot: ShotNode) {
  return (
    shot.segments === 0 ||
    shot.status === "needs_review" ||
    shot.status === "not_judged" ||
    shot.status === "differs_from_circle"
  );
}

/** What stands for a shot, said the way an editor would say it. */
function standing(shot: ShotNode) {
  if (!shot.segments) return STATUS_LABEL[shot.status];
  const ranges = `${shot.segments} range${shot.segments === 1 ? "" : "s"}`;
  // The tree knows how many ranges stand, not which takes they came from —
  // that needs the shot itself. "Chosen" is honest at this distance.
  return `${ranges} chosen`;
}

export default function ProjectOverview({
  projectId,
  scenes,
  headings,
  canCurate,
  scene,
}: {
  projectId: number;
  scenes: SceneNode[];
  /** Sluglines, which live on the plan rather than on the footage. */
  headings: Map<number, string>;
  canCurate: boolean;
  /** The scene being looked at, or 0 for the production as a whole. */
  scene: number;
}) {
  const open = scene ? scenes.find((item) => item.scene === scene) : undefined;

  // -- one scene: its shots ------------------------------------------------
  if (open) {
    return (
      <div className="project-overview">
        <div className="overview-stats">
          <span><b>{open.shots.length}</b> shot{open.shots.length === 1 ? "" : "s"}</span>
          <span><b>{open.shots.reduce((n, s) => n + s.takes, 0)}</b> takes</span>
          <span className={open.shots.filter(unsettled).length ? "overview-waiting" : ""}>
            <b>{open.shots.filter(unsettled).length}</b> waiting
          </span>
          <Link className="ghost small" href={`${paths.coverage(projectId, open.scene)}`}>
            Play scene
          </Link>
        </div>

        <div className="overview-shots">
          {open.shots.map((shot) => (
            <Link
              key={shot.shot}
              className="overview-shot"
              href={`${paths.shot(projectId, open.scene, shot.shot)}`}
            >
              <span className="overview-shot-head">
                <span className={`dot ${shot.status}`} aria-hidden />
                <b>{shot.slug || `Shot ${shot.shot}`}</b>
              </span>
              {shot.label && <small className="overview-shot-label">{shot.label}</small>}
              <span className="overview-shot-meta">
                {shot.takes} take{shot.takes === 1 ? "" : "s"}
                {shot.take_numbers.length > 1 &&
                  ` · ${shot.take_numbers.map((t) => `T${t}`).join(" ")}`}
              </span>
              <span className="overview-shot-state">{standing(shot)}</span>
              {shot.open_notes > 0 && (
                <span className="overview-shot-notes">{shot.open_notes} open notes</span>
              )}
            </Link>
          ))}
          {open.shots.length === 0 && (
            <p className="hint small">No shots declared in this scene yet.</p>
          )}
        </div>
      </div>
    );
  }

  // -- the production: its scenes ------------------------------------------
  const shots = scenes.flatMap((item) => item.shots);
  const takes = shots.reduce((total, shot) => total + shot.takes, 0);
  const waiting = shots.filter(unsettled).length;

  return (
    <div className="project-overview">
      <div className="overview-stats">
        <span><b>{scenes.length}</b> scene{scenes.length === 1 ? "" : "s"}</span>
        <span><b>{shots.length}</b> shot{shots.length === 1 ? "" : "s"}</span>
        <span><b>{takes}</b> take{takes === 1 ? "" : "s"}</span>
        <span className={waiting ? "overview-waiting" : ""}>
          <b>{waiting}</b> waiting
        </span>
      </div>

      <div className="scene-rows">
        {scenes.map((item) => {
          const sceneWaiting = item.shots.filter(unsettled).length;
          return (
            <Link
              key={item.scene}
              className="scene-row"
              href={`${paths.scene(projectId, item.scene)}`}
            >
              <span className="scene-row-name">
                <p className="eyebrow">SCENE {item.scene_code || item.scene}</p>
                <b>{headings.get(item.scene) || `Scene ${item.scene}`}</b>
              </span>
              <span className="scene-row-meta">
                {item.shots.length} shot{item.shots.length === 1 ? "" : "s"} ·{" "}
                {item.shots.reduce((n, s) => n + s.takes, 0)} takes
              </span>
              <span className={sceneWaiting ? "scene-row-waiting on" : "scene-row-waiting"}>
                {sceneWaiting ? `${sceneWaiting} waiting` : "settled"}
              </span>
              <i aria-hidden>›</i>
            </Link>
          );
        })}
      </div>

      {canCurate && (
        <Link className="ghost overview-add" href={`${paths.ingest(projectId)}`}>
          Add scenes, shots &amp; footage →
        </Link>
      )}
    </div>
  );
}
