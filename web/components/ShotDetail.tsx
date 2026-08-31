"use client";

/**
 * The core screen: every take of one shot, why each landed where it did, and
 * the part of each that is safe to use.
 *
 * Four decisions carry this screen.
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
 *
 * **The circle is shown and never fed in.** The take the room preferred is the
 * strongest prior about a shot that exists, and telling the panel about it would
 * end the measurement — it would agree, and the agreement would be reported as
 * independent confirmation of a judgement it was handed. So it is displayed
 * beside the verdict instead, where a person can weigh both.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import Comments from "@/components/Comments";
import Player, { PlayerHandle } from "@/components/Player";
import ShotBrief from "@/components/ShotBrief";
import type { Brief, ShotState, Take } from "@/lib/api";
import { ApiError } from "@/lib/api";
import {
  conflictMessage,
  useJudge,
  useShotEdits,
  useShotScreen,
  useUndo,
  useChooseTake,
} from "@/lib/queries";

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

const STATE_LABELS: { value: ShotState; label: string }[] = [
  { value: "", label: "unset" },
  { value: "needs_review", label: "needs review" },
  { value: "in_progress", label: "in progress" },
  { value: "approved", label: "approved" },
];

function seconds(value: number): string {
  const m = Math.floor(value / 60);
  const s = value % 60;
  return m > 0 ? `${m}:${s.toFixed(1).padStart(4, "0")}` : `${s.toFixed(1)}s`;
}

export default function ShotDetail({
  projectId,
  scene,
  shot,
  canComment,
  canCurate,
  you,
  teamEmails,
}: {
  projectId: number;
  scene: number;
  shot: number;
  /** Say something, or choose a different take. Anyone signed in, on anything
   *  they can read — including a guest on our productions, which is the whole
   *  demonstration. */
  canComment: boolean;
  /** Run the panel, describe the shot, record a circle, assign it, set its
   *  state. The editors' work on the editors' footage; a guest gets all of it
   *  inside a project they made. */
  canCurate: boolean;
  you: string;
  teamEmails: string[];
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [commentAt, setCommentAt] = useState<{ clipId: string; at: number } | null>(null);

  // One request for the whole screen, from the cache every other screen reads.
  // Every mutation below invalidates it, which is why the dashboard count moves
  // when a take is chosen here.
  const screen = useShotScreen(projectId, scene, shot);
  const data = screen.data?.verdicts ?? null;
  const brief = screen.data?.brief ?? null;

  const chooseTake = useChooseTake(projectId, scene, shot, data?.rev ?? 0);
  const judgeShot = useJudge(projectId, scene, shot);
  const undoChange = useUndo(projectId, scene, shot, data?.rev ?? 0);
  const edits = useShotEdits(projectId, scene, shot, brief ?? undefined);

  // The recommended take opens by default, and only until somebody picks
  // another. Deriving it every render would slam an expanded row shut whenever
  // the cache refreshed underneath.
  useEffect(() => {
    setOpen((current) =>
      current ?? data?.recommended ?? data?.takes[0]?.clip_id ?? null,
    );
  }, [data]);

  const saving =
    chooseTake.isPending ||
    judgeShot.isPending ||
    undoChange.isPending ||
    edits.circle.isPending ||
    edits.assign.isPending ||
    edits.setState.isPending;

  const judge = async () => {
    setNote("Comparing the takes. This can take a minute — the panel watches them.");
    try {
      await judgeShot.mutateAsync();
      setNote(null);
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Could not run the comparison.");
    }
  };

  const undo = async () => {
    try {
      await undoChange.mutateAsync();
      setNote("Put back. The change is still in the archive — nothing was deleted.");
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Could not undo that.");
    }
  };

  /** A stale edit is refused rather than allowed to overwrite. */
  const report = (e: unknown) =>
    setNote(
      conflictMessage(e) ??
        (e instanceof Error ? e.message : "Could not record that."),
    );

  const label = brief?.slug || `Shot ${shot}`;

  if (screen.isPending) {
    return (
      <div className="shot-detail">
        {/* Named rather than a bare spinner. The database idles to save credit
            and the first request after a quiet period pays for waking it, which
            is a wait with a reason rather than a stall. */}
        <p className="waiting">Loading — the archive may be waking up.</p>
      </div>
    );
  }

  if (screen.isError) {
    const waking = screen.error instanceof ApiError && screen.error.waking;
    return (
      <div className="shot-detail">
        <p className="error">
          {waking
            ? "The archive is still waking up. It sleeps when nobody is using it."
            : "Could not load this shot."}
        </p>
        <button type="button" onClick={() => void screen.refetch()}>
          Try again
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="shot-detail empty">
        <h2>
          Scene {scene} · {label}
        </h2>
        <p>No comparison has been run for this shot yet.</p>
        {canCurate ? (
          <>
            <button type="button" onClick={() => void judge()} disabled={saving}>
              {saving ? "Comparing…" : "Compare the takes"}
            </button>
            {note && <p className="waiting">{note}</p>}
          </>
        ) : (
          <p className="hint">
            {canComment
              ? "Only the editors who own this project can run the comparison."
              : "Sign in to take part."}
          </p>
        )}
        {brief && (
          <ShotBrief
            projectId={projectId}
            scene={scene}
            shot={shot}
            brief={brief}
            canEdit={canCurate}
            onSave={(fields) => edits.saveBrief.mutateAsync(fields)}
          />
        )}
      </div>
    );
  }

  const chosen = data.takes.find((t) => t.clip_id === data.recommended);
  const humanDecided = data.takes.some(
    (t) => t.outcome === "selected" && t.decided_by === "human",
  );

  return (
    <div className="shot-detail">
      <header className="shot-head">
        <div>
          <h2>
            Scene {scene} · {label}
          </h2>
          <p className="shot-sub">
            {data.takes.length} takes ·{" "}
            {chosen ? (
              <>take {chosen.take_no} standing</>
            ) : (
              "nothing recommended"
            )}
            {data.takes[0]?.camera && <> · camera {data.takes[0].camera}</>}
          </p>
        </div>

        <div className="shot-actions">
          <Assignment
            value={data.assignee}
            you={you}
            options={teamEmails}
            disabled={!canCurate}
            onChange={(value) => edits.assign.mutateAsync(value).catch(report)}
          />
          <StatePicker
            value={data.state}
            disabled={!canCurate}
            onChange={(value) => edits.setState.mutateAsync(value).catch(report)}
          />
        </div>
      </header>

      {data.differs_from_circle && (
        // The most interesting row in the archive, said as loudly as it deserves
        // and without a verdict attached. Neither side is wrong: the circle
        // knows about the performance, which this system deliberately does not
        // judge, and the measurements know about the frame.
        <p className="disagreement">
          The director circled <strong>take {data.circled_take}</strong>; the
          measurements chose <strong>take {chosen?.take_no}</strong>. Both are
          worth watching.
        </p>
      )}

      {note && <p className="waiting">{note}</p>}

      <CriteriaTable takes={data.takes} circled={data.circled_take} />

      <ol className="takes">
        {data.takes.map((take) => (
          <TakeRow
            key={take.clip_id}
            take={take}
            isRecommended={take.clip_id === data.recommended}
            isCircled={data.circled_take === take.take_no}
            expanded={open === take.clip_id}
            onToggle={() =>
              setOpen(open === take.clip_id ? null : take.clip_id)
            }
            canEdit={canComment}
            canCurate={canCurate}
            onNoteAt={(at) => setCommentAt({ clipId: take.clip_id, at })}
            onCircle={() =>
              edits.circle
                .mutateAsync(data.circled_take === take.take_no ? 0 : take.take_no)
                .then(() => undefined)
                .catch(report)
            }
            onChoose={async (reason, span) => {
              try {
                const result = await chooseTake.mutateAsync({
                  clip_id: take.clip_id,
                  reason,
                  ...(span ? { in_point_s: span.from, out_point_s: span.to } : {}),
                });
                setNote(
                  result.agreed_with_panel
                    ? "Recorded — you agreed with the panel."
                    : "Recorded — your choice replaces the panel's.",
                );
              } catch (e) {
                report(e);
              }
            }}
          />
        ))}
      </ol>

      <div className="shot-footer">
        {canCurate && (
          <button
            type="button"
            className="ghost"
            onClick={() => void judge()}
            disabled={saving}
            title="Compare the takes again — useful after describing the shot"
          >
            Compare again
          </button>
        )}
        {canComment && humanDecided && (
          <button
            type="button"
            className="ghost"
            onClick={() => void undo()}
            disabled={saving}
            title="Put back what stood before the last change. Nothing is deleted."
          >
            Undo the last change
          </button>
        )}
      </div>

      {brief && (
        <ShotBrief
          projectId={projectId}
          scene={scene}
          shot={shot}
          brief={brief}
          canEdit={canCurate}
          onSave={(fields) => edits.saveBrief.mutateAsync(fields)}
        />
      )}

      <Comments
        projectId={projectId}
        scene={scene}
        shot={shot}
        canComment={canComment}
        comments={screen.data?.comments ?? []}
        takes={data.takes.map((t) => ({ clip_id: t.clip_id, take_no: t.take_no }))}
        pending={commentAt}
        onConsumedPending={() => setCommentAt(null)}
      />
    </div>
  );
}

/** Whose shot this is. Anyone who can comment can assign, including to
 * themselves — a gate here would make the lead editor the only person who can
 * pick up a shot, which is how a queue stops moving on a Friday afternoon. */
function Assignment({
  value,
  you,
  options,
  disabled,
  onChange,
}: {
  value: string;
  you: string;
  options: string[];
  disabled: boolean;
  onChange: (assignee: string) => void;
}) {
  const people = useMemo(() => {
    const set = new Set(options.filter(Boolean));
    if (you) set.add(you);
    if (value) set.add(value);
    return Array.from(set).sort();
  }, [options, you, value]);

  return (
    <label className="picker">
      <span>Assigned</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">unclaimed</option>
        {people.map((p) => (
          <option key={p} value={p}>
            {p === you ? `${p.split("@")[0]} (you)` : p.split("@")[0]}
          </option>
        ))}
      </select>
    </label>
  );
}

/** What a person says the state is, alongside what the system derived.
 *
 * They answer different questions. Derived status says how sure the system is;
 * this says whether anybody is still working on it, and only the second one is
 * asked at a standup. */
function StatePicker({
  value,
  disabled,
  onChange,
}: {
  value: ShotState;
  disabled: boolean;
  onChange: (state: ShotState) => void;
}) {
  return (
    <label className="picker">
      <span>State</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value as ShotState)}
      >
        {STATE_LABELS.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/**
 * Per-criterion scores across every take, side by side.
 *
 * A table rather than a badge per take, because the useful reading is
 * *comparative* — which axis separates these takes — and that is a column, not
 * a cell.
 */
function CriteriaTable({ takes, circled }: { takes: Take[]; circled: number }) {
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
              <th key={t.clip_id} className={circled === t.take_no ? "circled" : undefined}>
                Take {t.take_no}
                {circled === t.take_no && (
                  <span className="circle" title="The director circled this take">
                    ◎
                  </span>
                )}
              </th>
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
  isCircled,
  expanded,
  onToggle,
  canEdit,
  canCurate,
  onChoose,
  onCircle,
  onNoteAt,
}: {
  take: Take;
  isRecommended: boolean;
  isCircled: boolean;
  expanded: boolean;
  onToggle: () => void;
  canEdit: boolean;
  canCurate: boolean;
  onChoose: (reason: string, span?: { from: number; to: number }) => Promise<void>;
  onCircle: () => Promise<void>;
  onNoteAt: (at: number) => void;
}) {
  const player = useRef<PlayerHandle>(null);
  const [reason, setReason] = useState("");

  // Starts where the panel put it, so doing nothing keeps its answer.
  const [span, setSpan] = useState({
    from: take.usable_from_s,
    to: take.usable_to_s > take.usable_from_s ? take.usable_to_s : take.duration_s,
  });
  const narrowed =
    Math.abs(span.from - take.usable_from_s) > 0.05 ||
    Math.abs(span.to - (take.usable_to_s || take.duration_s)) > 0.05;

  /** Seek and play. The whole point of a timecoded finding. */
  const seekTo = (at: number) => player.current?.seek(at, true);

  /**
   * J, K, L and the arrow keys, on the player.
   *
   * The transport every editor already has in their hands: K stops, L plays and
   * doubles on each press, J does the same backwards, and the arrows step a
   * frame. Uses the measured source rate; legacy clips fall back to 24fps and
   * are explicitly represented as unmeasured in the API.
   */
  const transport = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const el = player.current?.element();
    if (!el) return;
    const key = e.key.toLowerCase();

    if (key === "k") {
      e.preventDefault();
      el.pause();
      el.playbackRate = 1;
    } else if (key === "l") {
      e.preventDefault();
      el.playbackRate = el.paused ? 1 : Math.min(8, el.playbackRate * 2);
      void el.play().catch(() => {});
    } else if (key === "j") {
      e.preventDefault();
      // No negative playbackRate in any browser worth targeting, so J steps
      // back rather than pretending to reverse-play.
      el.pause();
      el.currentTime = Math.max(0, el.currentTime - 1);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      el.currentTime = Math.max(0, el.currentTime - 1 / (take.fps || 24));
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      el.currentTime = Math.min(take.duration_s, el.currentTime + 1 / (take.fps || 24));
    }
  };

  const trimmed = take.trim_reasons
    .map((c) => TRIM_LABELS[c] ?? c)
    .join(", ");

  return (
    <li
      className={`take${isRecommended ? " recommended" : ""}${isCircled ? " circled" : ""}`}
    >
      <button
        type="button"
        className="take-head"
        onClick={onToggle}
        aria-expanded={expanded}
      >
        <span className="take-no">
          Take {take.take_no}
          {isCircled && (
            <span className="circle" title="The director circled this take">
              ◎
            </span>
          )}
        </span>
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
          {/* Wrapped so the transport keys work wherever the focus is inside
              the take, not only on the element itself. */}
          <div onKeyDown={transport} role="group" aria-label="Player">
            <Player
              ref={player}
              className="player"
              src={take.proxy_uri}
              poster={take.sprite_uri}
            />
          </div>

          <SafeRangeBar
            take={take}
            onSeek={seekTo}
            span={canEdit ? span : undefined}
            onSpan={
              canEdit
                ? (from, to) => {
                    setSpan({ from, to });
                    player.current?.seek(from);
                  }
                : undefined
            }
          />

          <div className="range-key">
            <span className="rk">
              in <b className="mono">{seconds(span.from)}</b>
            </span>
            <span className="rk">
              out <b className="mono">{seconds(span.to)}</b>
            </span>
            <span className="rk">
              {seconds(Math.max(0, span.to - span.from))} used
            </span>
            {canEdit && (
              <span className="rk shuttle">
                {narrowed ? (
                  <button
                    type="button"
                    className="linkish"
                    onClick={() =>
                      setSpan({
                        from: take.usable_from_s,
                        to: take.usable_to_s || take.duration_s,
                      })
                    }
                  >
                    reset
                  </button>
                ) : (
                  <>drag the handles to narrow</>
                )}
              </span>
            )}
            <span className="rk hint">
              <kbd>J</kbd> <kbd>K</kbd> <kbd>L</kbd> shuttle · <kbd>←</kbd>
              <kbd>→</kbd> frame
            </span>
          </div>

          {trimmed && <p className="trimmed">Shortened because {trimmed}.</p>}

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
                        <span className={`code sev-${f.severity || "unrecorded"}`}>
                          {f.code}
                        </span>
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

          {canEdit && (
            <div className="take-tools">
              <button
                type="button"
                className="ghost small"
                onClick={() =>
                  onNoteAt(Math.max(0, player.current?.element()?.currentTime ?? 0))
                }
              >
                Note here
              </button>
              {/* The one field here that claims something about the world
                  rather than about the software — what happened in the room on
                  the day. A guest inventing one on our footage would be
                  inventing evidence, so it belongs to the editors who were
                  there. */}
              {canCurate && (
                <button
                  type="button"
                  className={isCircled ? "ghost small on" : "ghost small"}
                  onClick={() => void onCircle()}
                  title={
                    isCircled
                      ? "Remove the circle"
                      : "Record that the director circled this take on the day"
                  }
                >
                  {isCircled ? "◎ circled" : "Mark as circled"}
                </button>
              )}
            </div>
          )}

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
                onClick={() => void onChoose(reason.trim(), narrowed ? span : undefined)}
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
                onClick={() =>
                  void onChoose(
                    narrowed
                      ? "confirmed the recommendation, narrowed the range"
                      : "confirmed the recommendation",
                    narrowed ? span : undefined,
                  )
                }
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
/**
 * The take as a bar, and the two handles that narrow it.
 *
 * Reading the safe range is half of it; the other half is disagreeing with it.
 * The panel trims to what it can measure — a slate at the head, a jolt in the
 * middle — and an editor routinely wants two seconds less at the top because of
 * something no measurement sees. Dragging is how that is said.
 *
 * The handles start where the panel put them, so doing nothing keeps its
 * answer. What they set travels with the override as in and out points, which
 * the API has always accepted and nothing has ever sent.
 */
function SafeRangeBar({
  take,
  onSeek,
  span,
  onSpan,
}: {
  take: Take;
  onSeek: (at: number) => void;
  span?: { from: number; to: number };
  onSpan?: (from: number, to: number) => void;
}) {
  const total = take.duration_s || 1;
  const pct = (v: number) => `${Math.min(100, Math.max(0, (v / total) * 100))}%`;
  const bar = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<"from" | "to" | null>(null);

  const at = (clientX: number): number => {
    const box = bar.current?.getBoundingClientRect();
    if (!box || box.width === 0) return 0;
    return Math.min(total, Math.max(0, ((clientX - box.left) / box.width) * total));
  };

  useEffect(() => {
    if (!dragging || !span || !onSpan) return;

    const move = (e: PointerEvent) => {
      const value = at(e.clientX);
      // A quarter second of daylight between them. Handles that can cross
      // produce an out point before the in point, which every reader of an EDL
      // interprets differently and none of them usefully.
      if (dragging === "from") onSpan(Math.min(value, span.to - 0.25), span.to);
      else onSpan(span.from, Math.max(value, span.from + 0.25));
    };
    const up = () => setDragging(null);

    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [dragging, span, onSpan, total]);

  const nudge = (which: "from" | "to", by: number) => {
    if (!span || !onSpan) return;
    if (which === "from") onSpan(Math.min(Math.max(0, span.from + by), span.to - 0.25), span.to);
    else onSpan(span.from, Math.max(Math.min(total, span.to + by), span.from + 0.25));
  };

  return (
    <div
      className="range-bar"
      ref={bar}
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
              className={`mark sev-${f.severity || "unrecorded"}`}
              style={{ left: pct(at), width: pct(Math.max(to - at, total * 0.004)) }}
              onClick={() => onSeek(at)}
              title={`${f.code} at ${seconds(at)}`}
            />
          );
        })}

      {span && onSpan && (
        <>
          <span
            className="trimmed-out"
            style={{ left: 0, width: pct(span.from) }}
            aria-hidden
          />
          <span
            className="trimmed-out"
            style={{ left: pct(span.to), width: pct(total - span.to) }}
            aria-hidden
          />
          {(["from", "to"] as const).map((which) => (
            <button
              key={which}
              type="button"
              className={`handle ${which}`}
              style={{ left: pct(span[which]) }}
              onPointerDown={(e) => {
                e.preventDefault();
                setDragging(which);
              }}
              onKeyDown={(e) => {
                if (e.key === "ArrowLeft") nudge(which, -0.25);
                if (e.key === "ArrowRight") nudge(which, 0.25);
              }}
              aria-label={`${which === "from" ? "In" : "Out"} point, ${seconds(span[which])}`}
              title={`${which === "from" ? "In" : "Out"} ${seconds(span[which])} — drag, or arrow keys`}
            />
          ))}
        </>
      )}

      {take.safe_ranges.length === 0 && (
        <span className="nothing-usable">Nothing usable in this take</span>
      )}
    </div>
  );
}
