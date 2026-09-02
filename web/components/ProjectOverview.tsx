"use client";

/**
 * What a production looks like before you start working on it.
 *
 * Opening a project used to put you straight into a shot cockpit — whichever
 * shot the code decided needed a person most — with no view of the production
 * you had just opened. That is the right screen once you know what you are
 * doing and the wrong one for arriving: it answers "what should I do next"
 * while skipping "what is here".
 *
 * So this is the step the hierarchy was missing. Projects lists productions;
 * this lists a production's scenes and their shots; a shot opens the cockpit.
 * Every card is a way in, so nothing is lost by stopping here first.
 */

import Link from "next/link";
import type { SceneNode, ShotNode, ShotStatus } from "@/lib/api";

const STATUS_LABEL: Record<ShotStatus, string> = {
  too_few_takes: "choose a range",
  not_judged: "not compared",
  needs_review: "needs you",
  differs_from_circle: "differs from the circle",
  decided: "decided",
  confirmed: "settled",
};

function shotHref(projectId: number, scene: number, shot: number) {
  return `/project/${projectId}?scene=${scene}&shot=${shot}`;
}

export default function ProjectOverview({
  projectId,
  scenes,
  headings,
  canCurate,
}: {
  projectId: number;
  scenes: SceneNode[];
  /** Sluglines, which live on the plan rather than on the footage. */
  headings: Map<number, string>;
  canCurate: boolean;
}) {
  const shots = scenes.flatMap((scene) => scene.shots);
  const takes = shots.reduce((total, shot) => total + shot.takes, 0);
  // The same rule the rail and the queue use: a shot with no chosen source
  // ranges still wants a person.
  const waiting = shots.filter(
    (shot) =>
      shot.segments === 0 ||
      shot.status === "needs_review" ||
      shot.status === "not_judged" ||
      shot.status === "differs_from_circle",
  ).length;

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

      {scenes.map((scene) => (
        <section className="overview-scene" key={scene.scene}>
          <header>
            <div>
              <p className="eyebrow">SCENE {scene.scene_code || scene.scene}</p>
              <h2>{headings.get(scene.scene) || `Scene ${scene.scene}`}</h2>
            </div>
            <Link className="ghost small" href={`/project/${projectId}/scene/${scene.scene}`}>
              Play scene
            </Link>
          </header>

          <div className="overview-shots">
            {scene.shots.map((shot: ShotNode) => (
              <Link
                key={shot.shot}
                className="overview-shot"
                href={shotHref(projectId, scene.scene, shot.shot)}
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
                <span className="overview-shot-state">
                  {shot.segments > 0
                    ? `${shot.segments} range${shot.segments === 1 ? "" : "s"} chosen`
                    : STATUS_LABEL[shot.status]}
                </span>
                {shot.open_notes > 0 && (
                  <span className="overview-shot-notes">{shot.open_notes} open notes</span>
                )}
              </Link>
            ))}

            {scene.shots.length === 0 && (
              <p className="hint small">No shots declared in this scene yet.</p>
            )}
          </div>
        </section>
      ))}

      {canCurate && (
        <Link className="ghost overview-add" href={`/project/${projectId}/ingest`}>
          Add scenes, shots &amp; footage →
        </Link>
      )}
    </div>
  );
}
