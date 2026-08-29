"use client";

/**
 * Scene → Setup, with a dot that says what is left to do.
 *
 * The dot is the whole navigation. A shoot day is dozens of setups and almost
 * all of them are settled; the point of this column is to make the handful that
 * are not findable at a glance, without opening anything.
 *
 * "Decided" and "confirmed" are deliberately different states. A verdict nobody
 * has looked at is not the same as one an editor agreed with, and showing them
 * alike would hide the only work actually remaining.
 */

import type { SceneNode, SetupStatus } from "@/lib/api";

const STATUS_LABEL: Record<SetupStatus, string> = {
  too_few_takes: "one take",
  not_judged: "not compared",
  needs_review: "needs you",
  decided: "decided",
  confirmed: "confirmed",
};

const STATUS_ORDER: SetupStatus[] = [
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
}: {
  scenes: SceneNode[];
  selected: { scene: number; setup: number } | null;
  onSelect: (scene: number, setup: number) => void;
}) {
  if (scenes.length === 0) {
    return (
      <nav className="tree empty">
        <p className="hint">No footage in this project yet.</p>
      </nav>
    );
  }

  const waiting = scenes
    .flatMap((s) => s.setups)
    .filter((s) => s.status === "needs_review" || s.status === "not_judged").length;

  return (
    <nav className="tree" aria-label="Scenes and setups">
      <p className="tree-summary">
        {waiting === 0 ? (
          // The empty-queue state, said where it will actually be read.
          <>Everything is decided.</>
        ) : (
          <>
            {waiting} setup{waiting === 1 ? "" : "s"} waiting
          </>
        )}
      </p>

      {scenes.map((scene) => (
        <section key={scene.scene}>
          <h3>Scene {scene.scene}</h3>
          <ul>
            {[...scene.setups]
              .sort(
                (a, b) =>
                  STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) ||
                  a.setup - b.setup,
              )
              .map((setup) => {
                const isOpen =
                  selected?.scene === scene.scene && selected?.setup === setup.setup;
                return (
                  <li key={setup.setup}>
                    <button
                      type="button"
                      className={isOpen ? "node open" : "node"}
                      onClick={() => onSelect(scene.scene, setup.setup)}
                      aria-current={isOpen ? "true" : undefined}
                    >
                      <span className={`dot ${setup.status}`} aria-hidden />
                      <span className="node-name">
                        Setup {setup.setup}
                        {setup.label && (
                          <span className="node-label">{setup.label}</span>
                        )}
                      </span>
                      <span className="node-meta">
                        {setup.takes} take{setup.takes === 1 ? "" : "s"}
                        {setup.unusable > 0 && (
                          // Never a silent gap. An editor who uploaded eight
                          // takes and sees six needs to know which two and why.
                          <span className="unusable">
                            {" "}
                            · {setup.unusable} unusable
                          </span>
                        )}
                      </span>
                      <span className="sr-only">{STATUS_LABEL[setup.status]}</span>
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
