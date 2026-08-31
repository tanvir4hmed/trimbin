"use client";

/**
 * The scene, played two ways.
 *
 * **Full takes** is a stringout: every shot in order, one take each, its whole
 * usable range. It is what an assistant editor hands the editor and it is the
 * honest artefact — but on a scene with two angles and a minute of each, it
 * plays as two long clips rather than as a scene.
 *
 * **Rough cut** interleaves them: a few seconds of each shot in turn, round
 * robin, until every shot's usable range is spent. Two angles become A-B-A-B and
 * read as coverage. Nothing about it is an editorial decision — the cuts are a
 * fixed length and fall wherever the clock does — and the screen says so,
 * because a mechanical alternation presented as an edit would be a lie about the
 * one thing this system refuses to claim.
 */

import { use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import Player, { PlayerHandle } from "@/components/Player";
import type { Stringout, StringoutEntry } from "@/lib/api";
import { ApiError, api } from "@/lib/api";

const FRAME_RATES = [23.976, 24, 25, 29.97, 30, 50, 60];
const CUT_LENGTHS = [3, 5, 8, 12];

interface Segment {
  key: string;
  clip_id: string;
  proxy_uri: string;
  sprite_uri: string;
  slug: string;
  shot: number;
  take_no: number;
  from: number;
  to: number;
  reason: string;
  needs_review: boolean;
}

function clock(total: number): string {
  const m = Math.floor(total / 60);
  const s = Math.floor(total % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** Every shot in order, whole. */
function fullTakes(entries: StringoutEntry[]): Segment[] {
  return entries.map((e, i) => ({
    key: `${e.clip_id}-${i}`,
    clip_id: e.clip_id,
    proxy_uri: e.proxy_uri,
    sprite_uri: e.sprite_uri,
    slug: e.slug,
    shot: e.shot,
    take_no: e.take_no,
    from: e.start_s,
    to: e.end_s,
    reason: e.reason,
    needs_review: e.needs_review,
  }));
}

/**
 * A few seconds of each shot in turn, until every shot is spent.
 *
 * Round robin rather than random, so the pattern is predictable and a viewer can
 * tell what they are looking at. A shot whose usable range runs out drops out of
 * the rotation instead of repeating, which is why the last stretch of a scene
 * with uneven coverage is whichever angle had the most left.
 */
function roughCut(entries: StringoutEntry[], cut: number): Segment[] {
  const cursors = entries.map((e) => e.start_s);
  const segments: Segment[] = [];
  let n = 0;

  for (let guard = 0; guard < 500; guard++) {
    let moved = false;
    entries.forEach((e, i) => {
      const from = cursors[i];
      // Under half a second left is not a cut, it is a flash frame.
      if (from >= e.end_s - 0.5) return;
      const to = Math.min(e.end_s, from + cut);
      segments.push({
        key: `${e.clip_id}-${n++}`,
        clip_id: e.clip_id,
        proxy_uri: e.proxy_uri,
        sprite_uri: e.sprite_uri,
        slug: e.slug,
        shot: e.shot,
        take_no: e.take_no,
        from,
        to,
        reason: e.reason,
        needs_review: e.needs_review,
      });
      cursors[i] = to;
      moved = true;
    });
    if (!moved) break;
  }

  return segments;
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
  const [mode, setMode] = useState<"takes" | "rough">("rough");
  const [cut, setCut] = useState(5);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [fps, setFps] = useState(24);
  const player = useRef<PlayerHandle>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.stringout(projectId, sceneId));
      setError(null);
    } catch (e) {
      setError(
        e instanceof ApiError && e.waking
          ? "The archive is waking up."
          : e instanceof Error
            ? e.message
            : "Could not load this scene.",
      );
    } finally {
      setLoading(false);
    }
  }, [projectId, sceneId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (data?.export_fps) setFps(data.export_fps);
  }, [data?.export_fps]);

  const segments = useMemo(() => {
    if (!data) return [];
    return mode === "rough" ? roughCut(data.entries, cut) : fullTakes(data.entries);
  }, [data, mode, cut]);

  // Changing mode restarts, because segment 7 of a stringout and segment 7 of a
  // rough cut are different moments in the scene.
  useEffect(() => setIndex(0), [mode, cut]);

  const segment = segments[index];

  const seekToStart = useCallback(() => {
    if (segment) player.current?.seek(segment.from, playing);
  }, [segment, playing]);

  // A new segment on the same clip is a seek; a new clip is a load, and the
  // seek has to wait for it.
  useEffect(() => {
    seekToStart();
  }, [seekToStart]);

  const onTime = (t: number) => {
    if (!segment) return;
    if (t >= segment.to - 0.03) {
      if (index < segments.length - 1) setIndex((i) => i + 1);
      else {
        player.current?.element()?.pause();
        setPlaying(false);
      }
    }
  };

  const toggle = () => {
    const el = player.current?.element();
    if (!el) return;
    if (playing) {
      el.pause();
      setPlaying(false);
    } else {
      setPlaying(true);
      void el.play().catch(() => setPlaying(false));
    }
  };

  if (loading) return <main className="shell"><p className="waiting">Loading.</p></main>;

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

  const elapsed = segments
    .slice(0, index)
    .reduce((n, s) => n + (s.to - s.from), 0);

  return (
    <main className="shell stringout">
      <div className="crumbs">
        <Link href={`/project/${projectId}`}>Back to the project</Link>
      </div>

      <header className="dash-top">
        <div>
          <h1>Scene {sceneId}</h1>
          <p className="dim">
            {data.shots} shot{data.shots === 1 ? "" : "s"} · {clock(data.duration_s)} ·{" "}
            {segments.length} cut{segments.length === 1 ? "" : "s"}
          </p>
        </div>
        <div className="export-tools">
          <label className="picker">
            <span>Frame rate</span>
            <select value={fps} onChange={(e) => setFps(Number(e.target.value))}>
              {FRAME_RATES.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </label>
          <a className="ghost" href={api.edlUrl(projectId, sceneId, fps)}>EDL</a>
          <a className="ghost" href={api.markersUrl(projectId, sceneId, fps)}>Markers</a>
        </div>
      </header>

      <div className="mode-bar">
        <div className="modes">
          <button
            type="button"
            className={mode === "rough" ? "mode on" : "mode"}
            onClick={() => setMode("rough")}
          >
            Rough cut
          </button>
          <button
            type="button"
            className={mode === "takes" ? "mode on" : "mode"}
            onClick={() => setMode("takes")}
          >
            Full takes
          </button>
        </div>

        {mode === "rough" && (
          <label className="picker">
            <span>Cut every</span>
            <select value={cut} onChange={(e) => setCut(Number(e.target.value))}>
              {CUT_LENGTHS.map((c) => (
                <option key={c} value={c}>{c}s</option>
              ))}
            </select>
          </label>
        )}

        <span className="hint small">
          {mode === "rough"
            ? "Cuts between the shots on a fixed clock. Not an editorial decision — a way to watch the coverage as a scene."
            : "Every shot in order, whole. This is the stringout the EDL exports."}
        </span>
      </div>

      {(data.unresolved > 0 || data.disagreements > 0) && (
        <p className="disagreement">
          {data.unresolved > 0 && `${data.unresolved} unconfirmed. `}
          {data.disagreements > 0 &&
            `${data.disagreements} use a take the director did not circle.`}
        </p>
      )}

      <div className="stringout-player">
        <Player
          ref={player}
          className="player big"
          src={segment?.proxy_uri ?? ""}
          poster={segment?.sprite_uri}
          onTimeUpdate={onTime}
          onReady={seekToStart}
          onEnded={() => {
            if (index < segments.length - 1) setIndex((i) => i + 1);
            else setPlaying(false);
          }}
        />

        <div className="now-playing">
          <span className="np-slug">{segment?.slug}</span>
          <span className="np-take">take {segment?.take_no}</span>
          <span className="np-time mono">
            {clock(elapsed)} / {clock(data.duration_s)}
          </span>
        </div>

        <div className="stringout-transport">
          <button
            type="button"
            className="ghost"
            onClick={() => setIndex((i) => Math.max(0, i - 1))}
            disabled={index === 0}
          >
            ← previous
          </button>
          <button type="button" className="primary" onClick={toggle}>
            {playing ? "Pause" : "Play the scene"}
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => setIndex((i) => Math.min(segments.length - 1, i + 1))}
            disabled={index >= segments.length - 1}
          >
            next →
          </button>
        </div>

        {/* The shape of the assembly: one block per cut, coloured by shot, so
            an alternation is visible as an alternation. */}
        <div className="cutline">
          {segments.map((s, i) => (
            <button
              key={s.key}
              type="button"
              className={`cut shot-${s.shot % 6}${i === index ? " on" : ""}`}
              style={{ flexGrow: Math.max(0.4, s.to - s.from) }}
              onClick={() => setIndex(i)}
              title={`${s.slug} · take ${s.take_no} · ${clock(s.to - s.from)}`}
            />
          ))}
        </div>
      </div>

      <ol className="stringout-list">
        {data.entries.map((e) => (
          <li key={e.clip_id} className={e.needs_review ? "unsettled" : ""}>
            <button
              type="button"
              onClick={() => {
                const first = segments.findIndex((s) => s.clip_id === e.clip_id);
                if (first >= 0) setIndex(first);
              }}
            >
              <span className="so-slug">{e.slug}</span>
              <span className="so-take">
                take {e.take_no}
                {e.differs_from_circle && (
                  <span className="circle differs" title={`Director circled take ${e.circled_take}`}>
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
