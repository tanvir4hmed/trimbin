"use client";

/**
 * The core screen: every take of one setup, why each landed where it did, and
 * the part of each that is safe to use.
 *
 * Three decisions carry this screen.
 *
 * **Findings are links, not labels.** An editor told "unstable" has to go and
 * find it; an editor told "unstable, 4.2s" and given a click that seeks there
 * has been saved the search. That is most of the value of measuring anything.
 *
 * **The safe range is shaded on the scrubber, not written underneath.** A range
 * expressed as numbers is a range someone has to translate; shaded, it is the
 * shape of the take.
 *
 * **Every take is openable, including the rejected ones.** "Why not that one?"
 * is the question this whole system exists to answer, and a screen that shows
 * only the winner cannot answer it.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Take, Verdicts } from "@/lib/api";
import { ApiError, api } from "@/lib/api";

/** Offered as one-tap chips because a free-text box gets skipped.
 *
 * Drawn from what editors actually say when they overrule a technical
 * assessment: almost always that something the measurements cannot see mattered
 * more than the flaw they can. */
const REASONS = [
  "better performance",
  "director's preference",
  "cuts better with the next shot",
  "stronger emotional read",
  "matches the scene's rhythm",
] as const;

/** Codes that removed time, rendered as a sentence rather than an identifier. */
const TRIM_LABELS: Record<string, string> = {
  "slate.present": "the slate is in shot",
  "action.pre_roll": "the action has not started",
  "focus.lost": "focus is gone",
  "clip.black": "the frame is black",
  "frames.frozen": "the frame is frozen",
  "frame.boom_visible": "the boom is in shot",
  "frame.crew_visible": "crew are in shot",
  "frame.subject_exits": "the subject leaves frame",
};

const CRITERION_LABELS: Record<string, string> = {
  focus: "Focus",
  exposure: "Exposure",
  stability: "Stability",
  audio: "Audio",
  completion: "Completion",
  continuity: "Continuity",
};

/** Which axes a machine measured, so the reader knows what they are trusting. */
const MEASURED = new Set(["focus", "exposure", "stability", "audio"]);

function seconds(value: number): string {
  const m = Math.floor(value / 60);
  const s = value % 60;
  return m > 0 ? `${m}:${s.toFixed(1).padStart(4, "0")}` : `${s.toFixed(1)}s`;
}

export default function ShotDetail({
  projectId,
  scene,
  setup,
  canEdit,
  onDecided,
}: {
  projectId: number;
  scene: number;
  setup: number;
  canEdit: boolean;
  onDecided?: () => void;
}) {
  const [data, setData] = useState<Verdicts | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const found = await api.verdicts(projectId, scene, setup);
      setData(found);
      setOpen(found.recommended ?? found.takes[0]?.clip_id ?? null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        // Not an error. A setup nobody has judged is a normal state with an
        // obvious next action, and showing it as a failure hides that.
        setData(null);
        setError(null);
      } else if (e instanceof ApiError && e.waking) {
        // Named, so the reader knows to wait rather than to give up.
        setError(
          "The archive is still waking up. It sleeps when nobody is using it.",
        );
      } else {
        setError(e instanceof Error ? e.message : "Could not load this shot.");
      }
    } finally {
      setLoading(false);
    }
  }, [projectId, scene, setup]);

  useEffect(() => {
    void load();
  }, [load]);

  const judge = async () => {
    setSaving(true);
    setNote("Comparing the takes. This can take a minute — the panel watches them.");
    try {
      await api.judge(projectId, scene, setup);
      await load();
      onDecided?.();
      setNote(null);
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Could not run the comparison.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="shot-detail">
        {/* Named rather than a bare spinner. The database idles to save credit
            and the first request after a quiet period pays for waking it, which
            is a wait with a reason rather than a stall. */}
        <p className="waiting">Loading — the archive may be waking up.</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="shot-detail">
        <p className="error">{error}</p>
        <button type="button" onClick={() => void load()}>
          Try again
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="shot-detail empty">
        <h2>
          Scene {scene} · Setup {setup}
        </h2>
        <p>No comparison has been run for this setup yet.</p>
        {canEdit ? (
          <>
            <button type="button" onClick={() => void judge()} disabled={saving}>
              {saving ? "Comparing…" : "Compare the takes"}
            </button>
            {note && <p className="waiting">{note}</p>}
          </>
        ) : (
          <p className="hint">Sign in as a member of this project to run it.</p>
        )}
      </div>
    );
  }

  return (
    <div className="shot-detail">
      <header className="shot-head">
        <h2>
          Scene {scene} · Setup {setup}
        </h2>
        <p className="shot-sub">
          {data.takes.length} takes ·{" "}
          {data.recommended ? (
            <>
              take{" "}
              {data.takes.find((t) => t.clip_id === data.recommended)?.take_no}{" "}
              recommended
            </>
          ) : (
            "nothing recommended"
          )}
        </p>
      </header>

      {note && <p className="waiting">{note}</p>}

      <CriteriaTable takes={data.takes} />

      <ol className="takes">
        {data.takes.map((take) => (
          <TakeRow
            key={take.clip_id}
            take={take}
            isRecommended={take.clip_id === data.recommended}
            expanded={open === take.clip_id}
            onToggle={() =>
              setOpen(open === take.clip_id ? null : take.clip_id)
            }
            canEdit={canEdit}
            onChoose={async (reason) => {
              setSaving(true);
              try {
                const result = await api.select(projectId, scene, setup, {
                  clip_id: take.clip_id,
                  reason,
                });
                setNote(
                  result.agreed_with_panel
                    ? "Recorded — you agreed with the panel."
                    : "Recorded — your choice replaces the panel's.",
                );
                await load();
                onDecided?.();
              } catch (e) {
                setNote(e instanceof Error ? e.message : "Could not record that.");
              } finally {
                setSaving(false);
              }
            }}
          />
        ))}
      </ol>
    </div>
  );
}

/**
 * Per-criterion scores across every take, side by side.
 *
 * A table rather than a badge per take, because the useful reading is
 * *comparative* — which axis separates these takes — and that is a column, not
 * a cell.
 */
function CriteriaTable({ takes }: { takes: Take[] }) {
  const axes = useMemo(() => {
    const seen = new Set<string>();
    takes.forEach((t) => Object.keys(t.criteria).forEach((a) => seen.add(a)));
    return Array.from(seen);
  }, [takes]);

  if (axes.length === 0) return null;

  return (
    <div className="criteria-wrap">
      <table className="criteria">
        <thead>
          <tr>
            <th>Criterion</th>
            {takes.map((t) => (
              <th key={t.clip_id}>Take {t.take_no}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {axes.map((axis) => {
            const values = takes.map((t) => t.criteria[axis] ?? null);
            const best = Math.max(...values.map((v) => v ?? 0));
            return (
              <tr key={axis}>
                <th scope="row">
                  {CRITERION_LABELS[axis] ?? axis}
                  {/* Said, not implied. An editor deciding whether to trust a
                      number should know whether a machine measured it or a
                      model claimed it. */}
                  <span className="basis">
                    {MEASURED.has(axis) ? "measured" : "observed"}
                  </span>
                </th>
                {values.map((v, i) => (
                  <td
                    key={takes[i].clip_id}
                    className={v !== null && v === best ? "best" : undefined}
                  >
                    {v === null ? "—" : v.toFixed(2)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function TakeRow({
  take,
  isRecommended,
  expanded,
  onToggle,
  canEdit,
  onChoose,
}: {
  take: Take;
  isRecommended: boolean;
  expanded: boolean;
  onToggle: () => void;
  canEdit: boolean;
  onChoose: (reason: string) => Promise<void>;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const [reason, setReason] = useState("");

  /** Seek and play. The whole point of a timecoded finding. */
  const seekTo = (at: number) => {
    const el = video.current;
    if (!el) return;
    el.currentTime = Math.max(0, at);
    void el.play().catch(() => {
      /* Autoplay refused. The seek still happened, which is the useful half. */
    });
  };

  const trimmed = take.trim_reasons
    .map((c) => TRIM_LABELS[c] ?? c)
    .join(", ");

  return (
    <li className={`take${isRecommended ? " recommended" : ""}`}>
      <button
        type="button"
        className="take-head"
        onClick={onToggle}
        aria-expanded={expanded}
      >
        <span className="take-no">Take {take.take_no}</span>
        <span className={`outcome ${take.outcome}`}>
          {take.outcome === "selected"
            ? take.decided_by === "human"
              ? "chosen by editor"
              : "recommended"
            : take.outcome === "runner_up"
              ? "alternative"
              : "not selected"}
        </span>
        <span className="take-reason">{take.reason}</span>
        <span className="chevron" aria-hidden>
          {expanded ? "−" : "+"}
        </span>
      </button>

      {expanded && (
        <div className="take-body">
          <video
            ref={video}
            className="player"
            controls
            preload="metadata"
            playsInline
            poster={take.sprite_uri || undefined}
          >
            <source src={take.proxy_uri} type="application/vnd.apple.mpegurl" />
            {/* Safari plays HLS natively; everywhere else needs a player
                library. Said plainly rather than shown as a black rectangle. */}
            This browser cannot play HLS without a player library.
          </video>

          <SafeRangeBar take={take} onSeek={seekTo} />

          {trimmed && (
            <p className="trimmed">
              Shortened because {trimmed}.
            </p>
          )}

          {take.findings.length > 0 ? (
            <ul className="findings">
              {[...take.findings]
                .sort((a, b) => a.start_s - b.start_s)
                .map((f, i) => {
                  // A finding with no span applies to the whole take. That is
                  // still somewhere to go — the top — and making it clickable
                  // costs nothing while a dead row costs the reader a moment
                  // working out why this one does not respond.
                  const anchored = f.end_s > f.start_s;
                  const at = f.start_s;
                  return (
                    <li key={`${f.code}-${i}`}>
                      <button
                        type="button"
                        className="finding"
                        onClick={() => seekTo(anchored ? at : 0)}
                        title={
                          anchored
                            ? "Play from here"
                            : "Applies to the whole take — plays from the start"
                        }
                      >
                        <span className="at">
                          {anchored ? seconds(at) : "throughout"}
                        </span>
                        <span className="code">{f.code}</span>
                        {f.detail && <span className="detail">{f.detail}</span>}
                      </button>
                    </li>
                  );
                })}
            </ul>
          ) : (
            <p className="hint">Nothing found in this take.</p>
          )}

          <p className="provenance">
            {take.decided_by === "human" ? (
              <>Chosen by {take.actor}</>
            ) : (
              <>
                {take.panel_convened ? "Panel" : "Measurements"} ·{" "}
                {take.model_id || "no model"} · {take.prompt_version}
              </>
            )}
          </p>

          {canEdit && !isRecommended && (
            <div className="choose">
              <p>Use this take instead?</p>
              <div className="reasons">
                {REASONS.map((r) => (
                  <button
                    key={r}
                    type="button"
                    className={reason === r ? "chip on" : "chip"}
                    onClick={() => setReason(r)}
                  >
                    {r}
                  </button>
                ))}
              </div>
              <input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="or say why in your own words"
                aria-label="Reason"
              />
              <button
                type="button"
                className="primary"
                disabled={reason.trim().length < 3}
                onClick={() => void onChoose(reason.trim())}
              >
                Use take {take.take_no}
              </button>
            </div>
          )}

          {canEdit && isRecommended && take.decided_by === "agent" && (
            <div className="choose">
              <p>Agree with this?</p>
              <button
                type="button"
                className="primary"
                onClick={() => void onChoose("confirmed the recommendation")}
              >
                Confirm take {take.take_no}
              </button>
              {/* Recorded on purpose. "The editor agreed" is evidence; silence
                  is not, and a system that only writes down disagreements
                  cannot tell a good decision from an unexamined one. */}
            </div>
          )}
        </div>
      )}
    </li>
  );
}

/**
 * The take as a bar: usable stretches solid, removed time hollow, findings
 * marked where they happen.
 *
 * Clickable along its length, because once the shape of the take is visible the
 * next thing anyone wants is to jump into it.
 */
function SafeRangeBar({
  take,
  onSeek,
}: {
  take: Take;
  onSeek: (at: number) => void;
}) {
  const total = take.duration_s || 1;
  const pct = (v: number) => `${Math.min(100, Math.max(0, (v / total) * 100))}%`;

  return (
    <div
      className="range-bar"
      role="group"
      aria-label={`Usable parts of take ${take.take_no}`}
    >
      {take.safe_ranges.map((r, i) => (
        <button
          key={i}
          type="button"
          className="safe"
          style={{ left: pct(r.start_s), width: pct(r.end_s - r.start_s) }}
          onClick={() => onSeek(r.start_s)}
          title={`Usable ${seconds(r.start_s)} – ${seconds(r.end_s)}`}
        />
      ))}

      {take.findings
        .filter((f) => f.end_s > f.start_s)
        .map((f, i) => {
          const at = f.start_s;
          const to = f.end_s;
          return (
            <button
              key={`${f.code}-${i}`}
              type="button"
              className={`mark sev-${f.severity ?? "attention"}`}
              style={{ left: pct(at), width: pct(Math.max(to - at, total * 0.004)) }}
              onClick={() => onSeek(at)}
              title={`${f.code} at ${seconds(at)}`}
            />
          );
        })}

      {take.safe_ranges.length === 0 && (
        <span className="nothing-usable">Nothing usable in this take</span>
      )}
    </div>
  );
}
