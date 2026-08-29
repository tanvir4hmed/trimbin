"use client";

/**
 * The scene, assembled — a **stringout**.
 *
 * That is the word a cutting room uses, and it matters: this is not a screen we
 * invented. A stringout is what an assistant editor hands the editor — every
 * shot of the scene, in order, one take each, so it can be watched as a scene
 * instead of as a bin of ninety files. It is the actual deliverable of the job
 * this software does, and it was the screen the product was missing.
 *
 * It plays what the team decided, not what the panel recommended. An editor
 * override is the newest decision; a stringout showing the machine's picks after
 * a person changed them would be a report about the machine rather than a view
 * of the scene.
 *
 * It is not an edit. Nothing here decides where a cut goes, how long a shot
 * holds, or which angle a moment belongs to — those are story questions and the
 * system has no standing to answer them. A stringout is what an editor cuts
 * *from*.
 */

import { use, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { Stringout } from "@/lib/api";
import { ApiError, api } from "@/lib/api";

const FRAME_RATES = [23.976, 24, 25, 29.97, 30, 50, 60];

function clock(total: number): string {
  const m = Math.floor(total / 60);
  const s = Math.floor(total % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function ScenePage({
  params,
}: {
  params: Promise<{ id: string; scene: string }>;
}) {
  const { id, scene } = use(params);
  const projectId = Number(id);
  const sceneId = Number(scene);

  const [data, setData] = useState<Stringout | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [fps, setFps] = useState(24);
  const video = useRef<HTMLVideoElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.stringout(projectId, sceneId));
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.waking) {
        setError("The archive is still waking up.");
      } else {
        setError(e instanceof Error ? e.message : "Could not load this scene.");
      }
    } finally {
      setLoading(false);
    }
  }, [projectId, sceneId]);

  useEffect(() => {
    void load();
  }, [load]);

  const entry = data?.entries[index];

  // Seek to the shot's in-point whenever the shot changes. The archive holds an
  // in and an out per take; playing from zero would put the slate back in the
  // assembly, which is the thing the trim exists to remove.
  useEffect(() => {
    const el = video.current;
    if (!el || !entry) return;
    el.currentTime = entry.start_s;
    if (playing) void el.play().catch(() => setPlaying(false));
  }, [entry, playing]);

  // Stop at the out-point and roll on. Without this the player runs into the
  // tail of the take — the beat before somebody calls cut — and the assembly
  // reads as sloppy rather than as assembled.
  const onTime = () => {
    const el = video.current;
    if (!el || !entry) return;
    if (el.currentTime >= entry.end_s) {
      if (data && index < data.entries.length - 1) {
        setIndex((i) => i + 1);
      } else {
        el.pause();
        setPlaying(false);
      }
    }
  };

  if (loading) {
    return (
      <main className="shell">
        <p className="waiting">Loading — the archive may be waking up.</p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="shell">
        <p className="error">{error}</p>
        <Link href={`/project/${projectId}`}>Back to the project</Link>
      </main>
    );
  }

  if (!data || data.entries.length === 0) {
    return (
      <main className="shell">
        <div className="crumbs">
          <Link href={`/project/${projectId}`}>Back to the project</Link>
        </div>
        <h1>Scene {sceneId}</h1>
        <p className="hint">
          No shot in this scene has a take standing yet. Compare a shot and the
          scene assembles itself.
        </p>
      </main>
    );
  }

  return (
    <main className="shell stringout">
      <div className="crumbs">
        <Link href={`/project/${projectId}`}>Back to the project</Link>
      </div>

      <header className="dash-top">
        <div>
          <h1>Scene {sceneId}</h1>
          <p className="dim">
            {data.shots} shot{data.shots === 1 ? "" : "s"} ·{" "}
            {clock(data.duration_s)} · assembled from the takes that stand
          </p>
        </div>
        <div className="export-tools">
          <label className="picker">
            <span>Frame rate</span>
            <select value={fps} onChange={(e) => setFps(Number(e.target.value))}>
              {FRAME_RATES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
          <a className="ghost" href={api.edlUrl(projectId, sceneId, fps)}>
            EDL
          </a>
          <a className="ghost" href={api.markersUrl(projectId, sceneId, fps)}>
            Markers
          </a>
        </div>
      </header>

      {/* Said before anyone exports rather than discovered in a conform. Nothing
          in the archive records what the original was shot at — the proxies are
          normalised on the way in — so the rate is declared, not measured. */}
      <p className="hint small">
        The frame rate above is written into the EDL header. Nothing here
        measured it: set it to what the production shot at.
      </p>

      {(data.unresolved > 0 || data.disagreements > 0) && (
        <p className="disagreement">
          {data.unresolved > 0 && (
            <>
              {data.unresolved} shot{data.unresolved === 1 ? "" : "s"} here
              {data.unresolved === 1 ? " is" : " are"} still a close call nobody
              has confirmed.
            </>
          )}
          {data.disagreements > 0 && (
            <>
              {" "}
              {data.disagreements} use{data.disagreements === 1 ? "s" : ""} a
              take the director did not circle.
            </>
          )}{" "}
          Worth watching before this goes anywhere.
        </p>
      )}

      <div className="stringout-player">
        <video
          ref={video}
          className="player big"
          controls
          playsInline
          preload="metadata"
          poster={entry?.sprite_uri || undefined}
          onTimeUpdate={onTime}
          onEnded={() => {
            if (data && index < data.entries.length - 1) setIndex((i) => i + 1);
            else setPlaying(false);
          }}
        >
          {entry && (
            <source src={entry.proxy_uri} type="application/vnd.apple.mpegurl" />
          )}
          This browser cannot play HLS without a player library.
        </video>

        <div className="stringout-transport">
          <button
            type="button"
            className="ghost"
            onClick={() => setIndex((i) => Math.max(0, i - 1))}
            disabled={index === 0}
          >
            ← previous shot
          </button>
          <button
            type="button"
            className="primary"
            onClick={() => {
              setPlaying((p) => !p);
              const el = video.current;
              if (!el) return;
              if (playing) el.pause();
              else void el.play().catch(() => setPlaying(false));
            }}
          >
            {playing ? "Pause" : "Play the scene"}
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() =>
              setIndex((i) => Math.min(data.entries.length - 1, i + 1))
            }
            disabled={index >= data.entries.length - 1}
          >
            next shot →
          </button>
        </div>
      </div>

      <ol className="stringout-list">
        {data.entries.map((e, i) => (
          <li
            key={e.clip_id}
            className={`${i === index ? "current" : ""}${e.needs_review ? " unsettled" : ""}`}
          >
            <button type="button" onClick={() => setIndex(i)}>
              <span className="so-slug">{e.slug}</span>
              <span className="so-take">
                take {e.take_no}
                {e.differs_from_circle && (
                  <span
                    className="circle differs"
                    title={`The director circled take ${e.circled_take}`}
                  >
                    ◎{e.circled_take}
                  </span>
                )}
              </span>
              <span className="so-length">{clock(e.duration_s)}</span>
              <span className="so-reason">{e.reason}</span>
              <span className="so-by">
                {e.decided_by === "human" ? e.actor.split("@")[0] : "panel"}
                {e.needs_review && " · unconfirmed"}
              </span>
            </button>
            <Link
              className="linkish"
              href={`/project/${projectId}?scene=${e.scene}&shot=${e.shot}`}
            >
              open
            </Link>
          </li>
        ))}
      </ol>
    </main>
  );
}
