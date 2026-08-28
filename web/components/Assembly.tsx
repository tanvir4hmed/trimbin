"use client";

/**
 * The cut, playing as one continuous film.
 *
 * The selected spans stream from a single manifest stitched at request time, so
 * there is no render and no export — change a take and the next play reflects
 * it. For a director this is the entire product; for a visitor it is the moment
 * the idea becomes obvious in a way no screenshot manages.
 *
 * The timeline underneath is the part editors actually reach for. It shows every
 * shot boundary, every flagged moment and every note as a marker, so the health
 * of the whole picture reads at a glance rather than shot by shot.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { Cut, CutEntry } from "@/lib/api";
import { api } from "@/lib/api";

interface Props {
  projectId: number;
  readOnly?: boolean;
  onOpenShot?: (subgroupId: number) => void;
}

export function Assembly({ projectId, readOnly = false, onOpenShot }: Props) {
  const [cut, setCut] = useState<Cut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    api.cut(projectId).then(setCut).catch((e: Error) => setError(e.message));
  }, [projectId]);

  const current = cut?.entries.find(
    (e) => position >= e.start_s && position < e.end_s,
  );

  const seek = useCallback((seconds: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = seconds;
    setPosition(seconds);
  }, []);

  /**
   * J / K / L, because that is how every editor alive shuttles.
   *
   * A review surface that requires a mouse feels foreign to the people it is
   * for, and slows down the work it claims to speed up.
   */
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const video = videoRef.current;
      if (!video) return;
      if (event.target instanceof HTMLInputElement) return;

      switch (event.key.toLowerCase()) {
        case "j":
          video.playbackRate = 2;
          video.currentTime = Math.max(0, video.currentTime - 2);
          break;
        case "k":
          video.paused ? void video.play() : video.pause();
          break;
        case "l":
          video.playbackRate = video.paused ? 1 : Math.min(4, video.playbackRate * 2);
          void video.play();
          break;
        case "arrowleft":
          video.currentTime -= event.shiftKey ? 5 : 1 / 25;
          break;
        case "arrowright":
          video.currentTime += event.shiftKey ? 5 : 1 / 25;
          break;
        default:
          return;
      }
      event.preventDefault();
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (error) {
    return (
      <div className="state">
        <h2>Could not load the cut</h2>
        <p>{error}</p>
      </div>
    );
  }

  if (!cut) return <div className="state"><p>Assembling…</p></div>;

  if (cut.entries.length === 0) {
    return (
      <div className="state">
        <h2>Nothing to play yet</h2>
        <p>No shot in this project has a selected take.</p>
      </div>
    );
  }

  return (
    <div className="assembly">
      <div className="player-frame">
        <video
          ref={videoRef}
          className="player"
          controls
          preload="metadata"
          onTimeUpdate={(e) => setPosition(e.currentTarget.currentTime)}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
        >
          <source src={cut.playlist_uri} type="application/vnd.apple.mpegurl" />
        </video>

        {/* Reads from the entry list rather than tracking position separately,
            which drifts once playback rate changes. */}
        {current && (
          <div className="now-playing">
            <span className="mono">{current.scene_slug}</span>
            <span className="mono dim">Take {current.take_no}</span>
            {current.needs_review && <span className="flag">needs review</span>}
          </div>
        )}
      </div>

      <Timeline
        entries={cut.entries}
        duration={cut.duration_s}
        position={position}
        onSeek={seek}
        onOpenShot={onOpenShot}
      />

      {current && (
        <div className="current-detail">
          <p className="reason">{current.reason}</p>
          {!readOnly && onOpenShot && (
            <button
              className="ghost"
              onClick={() => {
                videoRef.current?.pause();
                onOpenShot(current.subgroup_id);
              }}
            >
              See the other takes
            </button>
          )}
        </div>
      )}

      <p className="hint">
        <kbd>K</kbd> play or pause · <kbd>J</kbd> <kbd>L</kbd> shuttle ·{" "}
        <kbd>←</kbd> <kbd>→</kbd> step a frame
        {playing ? "" : " · paused"}
      </p>
    </div>
  );
}

/**
 * The whole picture's health in one strip.
 *
 * Every shot is a segment, flagged ones are marked, and notes appear where they
 * were left. Scanning this is how an editor decides where to spend attention —
 * a list of sixty-eight shots does not answer "where are the problems" at all.
 */
function Timeline({
  entries,
  duration,
  position,
  onSeek,
  onOpenShot,
}: {
  entries: CutEntry[];
  duration: number;
  position: number;
  onSeek: (seconds: number) => void;
  onOpenShot?: (subgroupId: number) => void;
}) {
  const pct = (seconds: number) => (duration > 0 ? (seconds / duration) * 100 : 0);

  return (
    <div className="timeline" role="group" aria-label="Cut timeline">
      <div className="track">
        {entries.map((entry) => (
          <button
            key={`${entry.group_id}-${entry.subgroup_id}`}
            className={`shot ${entry.needs_review ? "flagged" : ""}`}
            style={{
              left: `${pct(entry.start_s)}%`,
              width: `${pct(entry.end_s - entry.start_s)}%`,
            }}
            title={`${entry.scene_slug} · Take ${entry.take_no}\n${entry.reason}`}
            onClick={() => onSeek(entry.start_s)}
            onDoubleClick={() => onOpenShot?.(entry.subgroup_id)}
          >
            {entry.note_count > 0 && (
              <span className="note-dot" aria-label={`${entry.note_count} notes`} />
            )}
          </button>
        ))}

        <div className="playhead" style={{ left: `${pct(position)}%` }} />
      </div>

      <div className="scale mono">
        <span>{formatClock(position)}</span>
        <span>{formatClock(duration)}</span>
      </div>
    </div>
  );
}

function formatClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
