"use client";

/**
 * Scene → Shot, with a dot that says what is left to do.
 *
 * The dot is the whole navigation. A shoot day is dozens of shots and almost
 * all of them are settled; the point of this column is to make the handful that
 * are not findable at a glance, without opening anything.
 *
 * "Decided" and "confirmed" are deliberately different states. A verdict nobody
 * has looked at is not the same as one an editor agreed with, and showing them
 * alike would hide the only work actually remaining.
 *
 * The newest state is "differs from the circle", and it outranks a close call.
 * A shot where the room circled take 3 and the measurements chose take 1 needs
 * a person whether or not the numbers were close — the circle knows about
 * performance, which this system deliberately does not judge.
 */

import type { SceneNode, ShotStatus } from "@/lib/api";

const STATUS_LABEL: Record<ShotStatus, string> = {
  too_few_takes: "one take",
  not_judged: "not compared",
  needs_review: "needs you",
  differs_from_circle: "differs from the circle",
  decided: "decided",
  confirmed: "confirmed",
};

const STATUS_ORDER: ShotStatus[] = [
  "differs_from_circle",
  "needs_review",
  "not_judged",
  "decided",
  "confirmed",
  "too_few_takes",
];

export default function SceneTree({
  scenes,
  selected,
  onSelect,
  onOpenScene,
}: {
  scenes: SceneNode[];
  selected: { scene: number; shot: number } | null;
  onSelect: (scene: number, shot: number) => void;
  onOpenScene?: (scene: number) => void;
}) {
  if (scenes.length === 0) {
    return (
      <nav className="tree empty">
        <p className="hint">Nothing matches those filters.</p>
      </nav>
    );
  }

  const waiting = scenes
    .flatMap((s) => s.shots)
    .filter(
      (s) =>
        s.status === "needs_review" ||
        s.status === "not_judged" ||
        s.status === "differs_from_circle",
    ).length;

  return (
    <nav className="tree" aria-label="Scenes and shots">
      <p className="tree-summary">
        {waiting === 0 ? (
          // The empty-queue state, said where it will actually be read.
          <>Everything is decided.</>
        ) : (
          <>
            {waiting} shot{waiting === 1 ? "" : "s"} waiting
          </>
        )}
      </p>

      {scenes.map((scene) => (
        <section key={scene.scene}>
          <h3>
            <span>Scene {scene.scene}</span>
            {onOpenScene && (
              <button
                type="button"
                className="linkish"
                onClick={() => onOpenScene(scene.scene)}
                title="Watch the scene from the takes that stand"
              >
                play
              </button>
            )}
          </h3>
          <ul>
            {[...scene.shots]
              .sort(
                (a, b) =>
                  STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) ||
                  a.shot - b.shot,
              )
              .map((shot) => {
                const isOpen =
                  selected?.scene === scene.scene && selected?.shot === shot.shot;
                return (
                  <li key={shot.shot}>
                    <button
                      type="button"
                      className={isOpen ? "node open" : "node"}
                      onClick={() => onSelect(scene.scene, shot.shot)}
                      aria-current={isOpen ? "true" : undefined}
                    >
                      <span className={`dot ${shot.status}`} aria-hidden />
                      <span className="node-name">
                        {/* The slug the slate carries, when there is one. "12A"
                            reads as a shot; "Shot 1" reads as a database row. */}
                        {shot.slug || `Shot ${shot.shot}`}
                        {shot.label && (
                          <span className="node-label">{shot.label}</span>
                        )}
                      </span>
                      <span className="node-meta">
                        {shot.takes} take{shot.takes === 1 ? "" : "s"}
                        {shot.cameras.length > 1 && (
                          <span className="node-cam">
                            {" "}
                            · {shot.cameras.filter(Boolean).join("/")}
                          </span>
                        )}
                        {shot.unusable > 0 && (
                          // Never a silent gap. An editor who uploaded eight
                          // takes and sees six needs to know which two and why.
                          <span className="unusable">
                            {" "}
                            · {shot.unusable} unusable
                          </span>
                        )}
                      </span>
                      <span className="node-marks">
                        {shot.circled_take > 0 && (
                          <span
                            className={
                              shot.differs_from_circle ? "circle differs" : "circle"
                            }
                            title={
                              shot.differs_from_circle
                                ? `The director circled take ${shot.circled_take}; take ${shot.chosen_take} is standing`
                                : `The director circled take ${shot.circled_take}`
                            }
                          >
                            ◎{shot.circled_take}
                          </span>
                        )}
                        {shot.open_notes > 0 && (
                          <span className="notes" title={`${shot.open_notes} open notes`}>
                            {shot.open_notes}
                          </span>
                        )}
                        {shot.assignee && (
                          <span className="who" title={shot.assignee}>
                            {shot.assignee.slice(0, 2)}
                          </span>
                        )}
                      </span>
                      <span className="sr-only">{STATUS_LABEL[shot.status]}</span>
                    </button>
                  </li>
                );
              })}
          </ul>
        </section>
      ))}
    </nav>
  );
}
