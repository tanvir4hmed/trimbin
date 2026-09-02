"use client";

/**
 * What people said, anchored to a second of a take.
 *
 * The archive has always held what was measured and what was decided. It has
 * never held what anyone *said* — and in every tool an editor already uses, the
 * timecoded comment is where the day is spent: pause, type, the note sticks to
 * that frame.
 *
 * Threads are one level deep on purpose. An editing note that needs a nested
 * argument needs a phone call.
 *
 * Nothing is edited and nothing is deleted. Resolving writes a second row, for
 * the same reason an override does: the disagreement is the data.
 */

import { useEffect, useState } from "react";
import type { Comment } from "@/lib/api";
import { useComment } from "@/lib/queries";

function seconds(value: number): string {
  const m = Math.floor(value / 60);
  const s = Math.floor(value % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function when(iso: string): string {
  if (!iso) return "";
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.round(ms / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

export default function Comments({
  projectId,
  scene,
  shot,
  canComment,
  comments,
  takes,
  pending,
  onConsumedPending,
  hideOwnTrigger = false,
}: {
  projectId: number;
  scene: number;
  shot: number;
  canComment: boolean;
  /** Handed down from the shot screen rather than fetched again. It arrived in
   *  the same request as the verdicts; asking for it a second time made the
   *  notes appear a beat after the takes. */
  comments: Comment[];
  takes: { clip_id: string; take_no: number }[];
  /** A timecode handed over from the player, so "note at 0:04" lands here. */
  pending: { clipId: string; at: number } | null;
  onConsumedPending: () => void;
  /**
   * The caller already draws an "add a note" control — the cockpit's carries
   * the playhead timecode, which this one cannot. Two buttons for one job, a
   * few pixels apart, was the clutter.
   */
  hideOwnTrigger?: boolean;
}) {
  const [body, setBody] = useState("");
  const [anchor, setAnchor] = useState<{ clipId: string; at: number } | null>(null);
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [replyBody, setReplyBody] = useState("");
  const [showResolved, setShowResolved] = useState(false);
  const [composing, setComposing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { add, resolve } = useComment(projectId, scene, shot);

  // A timecode arriving from the player fills the box and focuses it. The note
  // is the point; the timecode is a convenience that should not become a step.
  useEffect(() => {
    if (!pending) return;
    setAnchor(pending);
    setComposing(true);
    onConsumedPending();
    document.getElementById("comment-body")?.focus();
  }, [pending, onConsumedPending]);

  const post = async () => {
    if (body.trim().length === 0) return;
    try {
      await add.mutateAsync({
        body: body.trim(),
        clip_id: anchor?.clipId ?? null,
        at_s: anchor?.at ?? 0,
        to_s: anchor ? anchor.at + 2 : 0,
      });
      setBody("");
      setAnchor(null);
      setComposing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save that note.");
    }
  };

  const reply = async (parentId: string) => {
    if (replyBody.trim().length === 0) return;
    try {
      await add.mutateAsync({ body: replyBody.trim(), parent_id: parentId });
      setReplyBody("");
      setReplyTo(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not reply.");
    }
  };

  const takeOf = (clipId: string | null) =>
    clipId ? takes.find((t) => t.clip_id === clipId)?.take_no : undefined;

  const shown = showResolved ? comments : comments.filter((c) => !c.resolved);
  const resolvedCount = comments.length - comments.filter((c) => !c.resolved).length;

  return (
    <section className="comments">
      <h3>
        Notes
        {comments.length > 0 && (
          <span className="count">
            {comments.filter((c) => !c.resolved).length} open
          </span>
        )}
        {resolvedCount > 0 && (
          <button
            type="button"
            className="linkish"
            onClick={() => setShowResolved((v) => !v)}
          >
            {showResolved ? "hide" : "show"} {resolvedCount} resolved
          </button>
        )}
      </h3>

      {error && <p className="error small">{error}</p>}

      {shown.length === 0 ? (
        <p className="hint">
          No notes.{canComment && " Pause a take to anchor one to a moment."}
        </p>
      ) : (
        <ul className="comment-list">
          {shown.map((c) => (
            <li
              key={c.comment_id}
              className={`${c.is_reply ? "reply" : ""}${c.resolved ? " resolved" : ""}`}
            >
              <div className="c-head">
                <span className="c-who">{c.author.split("@")[0]}</span>
                {c.author_role === "guest" && (
                  <span className="tag quiet">guest</span>
                )}
                {c.clip_id && (
                  <span className="c-where">
                    take {takeOf(c.clip_id) ?? "?"}
                    {!c.whole_take && ` · ${seconds(c.at_s)}`}
                  </span>
                )}
                <span className="ago">{when(c.created_at)}</span>
              </div>
              <p className="c-body">{c.body}</p>
              {c.resolved ? (
                <p className="c-done">
                  Marked dealt with by {c.resolved_by.split("@")[0]}
                </p>
              ) : (
                canComment && (
                  <div className="c-actions">
                    {!c.is_reply && (
                      <button
                        type="button"
                        className="linkish"
                        onClick={() =>
                          setReplyTo(replyTo === c.comment_id ? null : c.comment_id)
                        }
                      >
                        reply
                      </button>
                    )}
                    <button
                      type="button"
                      className="linkish"
                      onClick={() => void resolve.mutateAsync(c.comment_id)}
                    >
                      mark dealt with
                    </button>
                  </div>
                )
              )}

              {replyTo === c.comment_id && (
                <div className="c-reply">
                  <input
                    type="text"
                    value={replyBody}
                    onChange={(e) => setReplyBody(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void reply(c.comment_id);
                      if (e.key === "Escape") setReplyTo(null);
                    }}
                    placeholder="Reply"
                    aria-label="Reply"
                  />
                  <button
                    type="button"
                    className="ghost small"
                    disabled={add.isPending || replyBody.trim().length === 0}
                    onClick={() => void reply(c.comment_id)}
                  >
                    Send
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {canComment && !composing && hideOwnTrigger ? null : canComment && !composing ? (
        // One line until it is wanted. The box, its anchor line and its button
        // used to sit open permanently at the bottom of the inspector, taking
        // the same room whether or not anybody was writing anything.
        <button
          type="button"
          className="ghost comment-open"
          onClick={() => {
            setComposing(true);
            window.setTimeout(() => document.getElementById("comment-body")?.focus(), 0);
          }}
        >
          ＋ Add a note{anchor ? ` at ${seconds(anchor.at)}` : ""}
        </button>
      ) : canComment ? (
        <div className="comment-new">
          {anchor && (
            <p className="c-anchor">
              On take {takeOf(anchor.clipId)} at {seconds(anchor.at)}
              <button
                type="button"
                className="linkish"
                onClick={() => setAnchor(null)}
              >
                make it about the shot instead
              </button>
            </p>
          )}
          <textarea
            id="comment-body"
            value={body}
            rows={2}
            maxLength={2000}
            onChange={(e) => setBody(e.target.value)}
            placeholder={
              anchor
                ? "What happens here?"
                : "A note about this shot. Pause a take to anchor it to a moment."
            }
            aria-label="New note"
          />
          <div className="comment-new-actions">
            <button
              type="button"
              className="primary"
              disabled={add.isPending || body.trim().length === 0}
              onClick={() => void post()}
            >
              {add.isPending ? "Saving…" : "Leave the note"}
            </button>
            <button
              type="button"
              className="linkish"
              onClick={() => {
                setComposing(false);
                setBody("");
                setAnchor(null);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <p className="hint">Sign in to leave a note.</p>
      )}
    </section>
  );
}
