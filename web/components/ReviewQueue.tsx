"use client";

/**
 * The review queue — the first thing an editor sees.
 *
 * Not a file tree and not a dashboard of numbers. The front door is the short
 * list of decisions waiting for a person, because that is the whole claim: six
 * of sixty-eight shots need your eye, and the other sixty-two were handled.
 *
 * Two design choices carry most of the weight here.
 *
 * The competing takes sit side by side at the same moment, because that is how
 * the comparison is actually made. Opening them one after another turns a
 * five-second decision into a minute of clicking back and forth.
 *
 * The reason for an override is captured in one keystroke. If it took ten
 * seconds people would skip it, and the reason is the only record anywhere of a
 * human editorial judgement — the thing this entire system exists to keep.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { Finding, ReviewItem, Take } from "@/lib/api";
import { api } from "@/lib/api";

/**
 * Offered as one-tap chips because a free-text box gets skipped.
 *
 * Drawn from what editors actually say when they overrule a technical
 * assessment: almost always that the performance mattered more than the flaw.
 */
const REASONS = [
  "better performance",
  "director's preference",
  "cuts better with the next shot",
  "stronger emotional read",
  "matches the scene's rhythm",
] as const;

const REASON_LABELS: Record<ReviewItem["reason"], string> = {
  narrow_margin: "Close call",
  no_winner: "Nothing usable",
  blocking: "Problem in the best take",
  inferred_grouping: "Grouping was guessed",
};

interface Props {
  projectId: number;
  onOpenAssembly: () => void;
}

export function ReviewQueue({ projectId, onOpenAssembly }: Props) {
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .reviewQueue(projectId)
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  }, [projectId]);

  const item = items?.[index];

  const choose = useCallback(
    async (take: Take, reason: string) => {
      if (!item || saving) return;
      setSaving(true);
      try {
        await api.override(projectId, item.subgroup_id, take.clip_id, reason);
        // Advance rather than refetching: the queue was correct when it loaded,
        // and reloading it under someone mid-review moves the ground.
        setIndex((i) => i + 1);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setSaving(false);
      }
    },
    [item, projectId, saving],
  );

  if (error) {
    return (
      <Empty
        title="Could not load the queue"
        detail={error}
        action={{ label: "Try again", onClick: () => location.reload() }}
      />
    );
  }

  if (items === null) return <Loading />;

  if (items.length === 0) {
    return (
      <Empty
        title="Everything is decided"
        detail="No shot in this project needs a second opinion."
        action={{ label: "Watch the cut", onClick: onOpenAssembly }}
      />
    );
  }

  if (!item) {
    return (
      <Empty
        title={`${items.length} shot${items.length === 1 ? "" : "s"} reviewed`}
        detail="The queue is clear."
        action={{ label: "Watch the cut", onClick: onOpenAssembly }}
      />
    );
  }

  return (
    <div className="queue">
      <header className="queue-head">
        <div>
          <span className="eyebrow">{REASON_LABELS[item.reason]}</span>
          <h2>{item.scene_slug}</h2>
          <p className="detail">{item.detail}</p>
        </div>
        {/* Progress, so the end is visible. An open-ended queue feels endless
            even when it is six items long. */}
        <div className="progress mono">
          {index + 1} of {items.length}
        </div>
      </header>

      {item.reviewed_by && (
        <p className="already-seen">
          {item.reviewed_by} has already looked at this shot.
        </p>
      )}

      <div className="takes">
        {item.takes.map((take) => (
          <TakeCard
            key={take.clip_id}
            take={take}
            disabled={saving}
            onChoose={(reason) => choose(take, reason)}
          />
        ))}
      </div>

      <footer className="queue-foot">
        <button
          className="ghost"
          onClick={() => setIndex((i) => i + 1)}
          disabled={saving}
        >
          Decide later
        </button>
        <span className="hint">
          <kbd>J</kbd> <kbd>K</kbd> <kbd>L</kbd> to shuttle · number keys to choose
        </span>
      </footer>
    </div>
  );
}

function TakeCard({
  take,
  disabled,
  onChoose,
}: {
  take: Take;
  disabled: boolean;
  onChoose: (reason: string) => void;
}) {
  const [choosing, setChoosing] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  /** Jump the player to a finding. This is what makes a timecode worth having. */
  const seekTo = (seconds: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = seconds;
    void video.play();
  };

  return (
    <article className={`take ${take.is_selected ? "selected" : ""}`}>
      <div className="take-head">
        <span className="mono take-no">Take {take.take_no}</span>
        {take.is_selected && <span className="badge">system pick</span>}
        <span className="mono score">{Math.round(take.score * 100)}%</span>
      </div>

      <video
        ref={videoRef}
        className="take-video"
        controls
        preload="metadata"
        poster={take.sprite_uri || undefined}
      >
        <source src={take.playlist_uri} type="application/vnd.apple.mpegurl" />
      </video>

      <p className="take-reason">{take.reason}</p>

      {take.findings.length > 0 && (
        <ul className="findings">
          {take.findings.map((finding, i) => (
            <FindingRow key={i} finding={finding} onSeek={seekTo} />
          ))}
        </ul>
      )}

      {choosing ? (
        <div className="reasons">
          <span className="reasons-label">Why?</span>
          {REASONS.map((reason) => (
            <button
              key={reason}
              className="reason-chip"
              disabled={disabled}
              onClick={() => onChoose(reason)}
            >
              {reason}
            </button>
          ))}
        </div>
      ) : (
        <button
          className="choose"
          disabled={disabled}
          onClick={() => setChoosing(true)}
        >
          Use this take
        </button>
      )}
    </article>
  );
}

function FindingRow({
  finding,
  onSeek,
}: {
  finding: Finding;
  onSeek: (seconds: number) => void;
}) {
  const at = finding.where?.start_s;

  // A finding with a timecode is a destination; one without is a note. The
  // difference has to be visible before it is clicked, or people learn that
  // half of them do nothing.
  if (at === undefined || at === null) {
    return (
      <li className={`finding ${finding.severity}`}>
        <span>{finding.detail}</span>
      </li>
    );
  }

  return (
    <li className={`finding ${finding.severity}`}>
      <button className="seek" onClick={() => onSeek(at)}>
        <span>{finding.detail}</span>
        <span className="mono at">{formatTime(at)}</span>
      </button>
    </li>
  );
}

function Loading() {
  return (
    <div className="state">
      <p>Loading the queue…</p>
    </div>
  );
}

function Empty({
  title,
  detail,
  action,
}: {
  title: string;
  detail: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="state">
      <h2>{title}</h2>
      <p>{detail}</p>
      {action && (
        <button className="primary" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  );
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
}
