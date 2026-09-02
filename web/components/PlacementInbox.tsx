"use client";

/**
 * Clips whose home nobody has agreed with.
 *
 * Ingest already noticed these — a clip sent to 12C whose slate reads 15B, a
 * file whose bytes are already here under another name — and had nowhere to put
 * them but a log line and a flag on a job that expires.
 *
 * Every row shows the evidence: the frame the board was read from, what it said
 * verbatim, and what the folder claimed. An editor deciding whether the slate or
 * the reader was wrong has to see the board; a confidence percentage is not a
 * substitute for looking at it.
 *
 * Nothing moves without somebody pressing something.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { PlannedScene } from "@/lib/api";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";

export default function PlacementInbox({
  projectId,
  plan,
  canResolve,
}: {
  projectId: number;
  plan: PlannedScene[];
  canResolve: boolean;
}) {
  const client = useQueryClient();
  const [target, setTarget] = useState<Record<string, { scene: number; shot: number }>>({});

  const inbox = useQuery({
    queryKey: ["project", projectId, "placements"],
    queryFn: () => api.placementInbox(projectId),
    refetchInterval: (query) =>
      // Poll while anything is waiting: the worker is still landing clips and
      // rows appear as it does. Stop once the inbox is clear.
      (query.state.data?.count ?? 0) > 0 ? 8000 : false,
  });

  const resolve = useMutation({
    mutationFn: ({
      clipId,
      body,
    }: {
      clipId: string;
      body: Parameters<typeof api.resolvePlacement>[2];
    }) => api.resolvePlacement(projectId, clipId, body),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["project", projectId, "placements"] }),
        // A moved clip changes the tree it lands in and the counts above it.
        client.invalidateQueries({ queryKey: keys.project(projectId) }),
        client.invalidateQueries({ queryKey: keys.dashboard() }),
      ]);
    },
  });

  const waiting = inbox.data?.waiting ?? [];
  if (inbox.isPending || waiting.length === 0) return null;

  return (
    <section className="inbox">
      <div className="sect">
        Needs a decision
        <span className="note">
          {waiting.length} clip{waiting.length === 1 ? "" : "s"} · nothing moves or
          deletes without confirmation
        </span>
      </div>

      {waiting.map((row) => {
        const chosen = target[row.clip_id] ?? {
          scene: row.declared_scene || row.scene,
          shot: row.declared_shot || row.shot,
        };
        const shots = plan.find((s) => s.scene === chosen.scene)?.shots ?? [];
        // Structural now, not a guess at the wording of `detail`. Empty when
        // the bytes exist only here, or when the other copy is itself still
        // unresolved — there is nothing settled yet to replace.
        const duplicate = Boolean(row.duplicate_of);

        return (
          <div key={row.clip_id} className="inbox-row">
            {/* The board itself. */}
            {row.slate_uri ? (
              <img className="slate-frame" src={row.slate_uri} alt="The slate on this clip" />
            ) : (
              <div className="slate-frame none">no board</div>
            )}

            <div className="inbox-main">
              <div className="ir-head">
                <span className="mono">{row.filename || row.clip_id.slice(0, 8)}</span>
                <span className={duplicate ? "pill dup" : "pill warn"}>
                  {duplicate ? "Duplicate" : "Needs review"}
                </span>
                {row.camera && <span className="pill quiet">CAM {row.camera}</span>}
                <span className="dim small">{row.duration_s.toFixed(0)}s</span>
              </div>

              <div className="ir-why">{row.detail}</div>

              <div className="ir-evidence">
                {row.slate_raw && (
                  <span className="chip-ev">
                    slate read <b className="mono">{row.slate_raw}</b>
                  </span>
                )}
                {row.declared_scene > 0 && (
                  <span className="chip-ev">
                    sent to <b className="mono">
                      {row.declared_scene}
                      {row.declared_shot ? `/${row.declared_shot}` : ""}
                    </b>
                  </span>
                )}
                {row.confidence > 0 && (
                  <span className="chip-ev">
                    confidence <b>{Math.round(row.confidence * 100)}%</b>
                  </span>
                )}
              </div>

              {canResolve && (
                <div className="ir-actions">
                  <label>
                    Scene
                    <select
                      value={chosen.scene}
                      onChange={(e) =>
                        setTarget({
                          ...target,
                          [row.clip_id]: { scene: Number(e.target.value), shot: 0 },
                        })
                      }
                    >
                      <option value={0}>unassigned</option>
                      {plan.map((s) => (
                        <option key={s.scene} value={s.scene}>
                          {s.scene}
                          {s.heading ? ` · ${s.heading}` : ""}
                        </option>
                      ))}
                      {/* The scene the slate names, even if nobody planned it.
                          Refusing to offer it would make the correct answer the
                          one option not on the menu. */}
                      {row.scene > 0 && !plan.some((s) => s.scene === row.scene) && (
                        <option value={row.scene}>{row.scene} · from the slate</option>
                      )}
                    </select>
                  </label>

                  <label>
                    Shot
                    <select
                      value={chosen.shot}
                      onChange={(e) =>
                        setTarget({
                          ...target,
                          [row.clip_id]: { ...chosen, shot: Number(e.target.value) },
                        })
                      }
                    >
                      <option value={0}>unassigned</option>
                      {shots.map((h) => (
                        <option key={h.shot} value={h.shot}>
                          {h.slug || `Shot ${h.shot}`}
                        </option>
                      ))}
                      {row.shot > 0 && !shots.some((h) => h.shot === row.shot) && (
                        <option value={row.shot}>{row.shot} · from the slate</option>
                      )}
                    </select>
                  </label>

                  <button
                    type="button"
                    className="primary small"
                    disabled={resolve.isPending}
                    onClick={() =>
                      resolve.mutate({
                        clipId: row.clip_id,
                        body: { action: "move", scene: chosen.scene, shot: chosen.shot },
                      })
                    }
                  >
                    Move here
                  </button>
                  <button
                    type="button"
                    className="ghost small"
                    disabled={resolve.isPending}
                    onClick={() =>
                      resolve.mutate({ clipId: row.clip_id, body: { action: "keep" } })
                    }
                  >
                    Keep where it is
                  </button>
                  <button
                    type="button"
                    className="ghost small"
                    disabled={resolve.isPending}
                    onClick={() =>
                      resolve.mutate({ clipId: row.clip_id, body: { action: "unassign" } })
                    }
                  >
                    Leave unassigned
                  </button>
                </div>
              )}

              {duplicate && (
                <div className="ir-duplicate">
                  <p className="hint small">
                    Same bytes as the clip already standing in{" "}
                    <b className="mono">
                      {row.duplicate_scene}/{row.duplicate_shot} take {row.duplicate_take}
                    </b>
                    . Kept, not deleted — replacing only changes which of the
                    two is current for that take.
                  </p>
                  {canResolve && (
                    <button
                      type="button"
                      className="ghost small"
                      disabled={resolve.isPending}
                      onClick={() =>
                        resolve.mutate({ clipId: row.clip_id, body: { action: "replace" } })
                      }
                    >
                      Replace the existing take with this one
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}

      {resolve.isError && (
        <p className="error small">
          {resolve.error instanceof Error
            ? resolve.error.message
            : "Could not settle that clip."}
        </p>
      )}
    </section>
  );
}
