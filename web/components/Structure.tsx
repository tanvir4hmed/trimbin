"use client";

/**
 * The scene and shot list, entered before any footage exists.
 *
 * A production is planned on paper: scene 12 has shots A to E and that is known
 * on day one. Declaring it gives an editor somewhere to upload into, and gives
 * ingest something to check a slate against.
 */

import { useState } from "react";
import type { PlannedScene } from "@/lib/api";
import { api } from "@/lib/api";

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

function letter(n: number): string {
  return n >= 1 && n <= 26 ? LETTERS[n - 1] : String(n);
}

export default function Structure({
  projectId,
  scenes,
  canEdit,
  onChanged,
  takesByShot,
}: {
  projectId: number;
  scenes: PlannedScene[];
  canEdit: boolean;
  onChanged: () => void;
  /**
   * How many takes have actually landed in each planned shot, keyed
   * `scene:shot`. A plan is what somebody intends to shoot and the tree is what
   * arrived; drawn without this they look like one list, and a scene planned
   * months ago is indistinguishable from one that wrapped yesterday.
   */
  takesByShot?: Map<string, number>;
}) {
  const [openScene, setOpenScene] = useState<number | null>(null);
  const [newScene, setNewScene] = useState("");
  const [heading, setHeading] = useState("");
  const [shotSlug, setShotSlug] = useState("");
  const [shotDesc, setShotDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addScene = async () => {
    const code = newScene.trim();
    if (!code) return;
    setBusy(true);
    try {
      await api.addScene(projectId, code, heading.trim());
      setNewScene("");
      setHeading("");
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add that scene.");
    } finally {
      setBusy(false);
    }
  };

  const addShot = async (scene: number) => {
    const existing = scenes.find((s) => s.scene === scene)?.shots ?? [];
    const next = Math.max(0, ...existing.map((s) => s.shot)) + 1;
    setBusy(true);
    try {
      await api.addShot(
        projectId,
        scene,
        next,
        shotSlug.trim() || `${scene}${letter(next)}`,
        shotDesc.trim(),
      );
      setShotSlug("");
      setShotDesc("");
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add that shot.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="structure">
      <div className="sect">
        Shot list
        {scenes.length === 0 && (
          <span className="note">
            Optional. Without one, slates decide where footage goes.
          </span>
        )}
      </div>

      {scenes.map((s) => (
        <div key={s.scene} className="plan-scene">
          <button
            type="button"
            className="plan-head"
            onClick={() => setOpenScene(openScene === s.scene ? null : s.scene)}
          >
            <span className="chev">{openScene === s.scene ? "▾" : "▸"}</span>
            <span className="code">SCENE {s.scene_code || s.scene}</span>
            <span className="desc">{s.heading}</span>
            <span className="scount">
              {s.shots.length} shot{s.shots.length === 1 ? "" : "s"}
              {takesByShot && (
                <em className="plan-footage">
                  {s.shots.reduce(
                    (total, h) => total + (takesByShot.get(`${s.scene}:${h.shot}`) ?? 0),
                    0,
                  ) === 0
                    ? " · no footage yet"
                    : ` · ${s.shots.reduce((total, h) => total + (takesByShot.get(`${s.scene}:${h.shot}`) ?? 0), 0)} takes`}
                </em>
              )}
            </span>
          </button>

          {openScene === s.scene && (
            <div className="plan-shots">
              {s.shots.map((h) => (
                <div key={h.shot} className="plan-shot">
                  <span className="mono">{h.slug || `${s.scene}${letter(h.shot)}`}</span>
                  <span className="desc">{h.description}</span>
                  {takesByShot && (
                    <span className="plan-takes">
                      {takesByShot.get(`${s.scene}:${h.shot}`)
                        ? `${takesByShot.get(`${s.scene}:${h.shot}`)} take${takesByShot.get(`${s.scene}:${h.shot}`) === 1 ? "" : "s"}`
                        : "empty"}
                    </span>
                  )}
                  {canEdit && (
                    <button
                      type="button"
                      className="linkish"
                      onClick={async () => {
                        try {
                          await api.removeShot(projectId, s.scene, h.shot);
                          onChanged();
                        } catch (e) {
                          setError(
                            e instanceof Error ? e.message : "Could not remove that.",
                          );
                        }
                      }}
                    >
                      remove
                    </button>
                  )}
                </div>
              ))}

              {canEdit && (
                <div className="plan-add">
                  <span className="plan-add-label">Add a shot</span>
                  <input
                    type="text"
                    value={shotSlug}
                    placeholder={`${s.scene}${letter(s.shots.length + 1)}`}
                    maxLength={40}
                    aria-label="Shot code, as written on the slate"
                    title="Shot code, as written on the slate"
                    onChange={(e) => setShotSlug(e.target.value)}
                  />
                  <input
                    type="text"
                    value={shotDesc}
                    placeholder="wide, Maya CU, reverse"
                    maxLength={200}
                    aria-label="What the shot is"
                    title="What the shot is"
                    onChange={(e) => setShotDesc(e.target.value)}
                  />
                  <button
                    type="button"
                    className="ghost small"
                    disabled={busy}
                    onClick={() => void addShot(s.scene)}
                  >
                    Add shot
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      ))}

      {canEdit && (
        <div className="plan-add">
          <span className="plan-add-label">Add a scene</span>
          <input
            type="text"
            value={newScene}
            placeholder="3, 12A-PU, A012C"
            aria-label="Scene code, as written on the slate"
            title="Scene code, as written on the slate"
            onChange={(e) => setNewScene(e.target.value)}
          />
          <input
            type="text"
            value={heading}
            placeholder="INT. APARTMENT — NIGHT"
            maxLength={200}
            aria-label="Scene heading, from the script"
            title="Scene heading, from the script"
            onChange={(e) => setHeading(e.target.value)}
          />
          <button
            type="button"
            className="ghost small"
            disabled={busy}
            onClick={() => void addScene()}
          >
            Add scene
          </button>
        </div>
      )}

      {error && <p className="error small">{error}</p>}
    </section>
  );
}
