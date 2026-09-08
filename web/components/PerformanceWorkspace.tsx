"use client";

import { useEffect, useRef, useState } from "react";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import Player, { type PlayerHandle } from "./Player";
import {
  api,
  type AttemptItem,
  type AttemptState,
  type Take,
  type TakeAnalysis,
} from "@/lib/api";
import { currentIdentity } from "@/lib/auth";

const key = (project: number, clip: string) =>
  ["project", project, "attempts", clip] as const;
const time = (n: number) =>
  `${Math.floor(n / 60)}:${(n % 60).toFixed(2).padStart(5, "0")}`;
type Candidate = {
  item: AttemptItem;
  take: Take;
  data: AttemptState;
  risk: number | null;
};
const identity = (c: Candidate) => `${c.take.clip_id}/${c.item.id}`;
const processing = (state?: string) =>
  ["pending", "queued", "processing"].includes(state ?? "");
type Transport = { sequence: number; action: "play" | "pause" | "restart" };

function validDraft(value: unknown): value is AttemptItem[] {
  return (
    Array.isArray(value) &&
    value.length <= 200 &&
    value.every(
      (row) =>
        row &&
        typeof row.id === "string" &&
        typeof row.label === "string" &&
        Number.isFinite(row.start_s) &&
        Number.isFinite(row.end_s) &&
        typeof row.note === "string" &&
        [
          "proposed",
          "reviewed",
          "clean",
          "shortlisted",
          "director_choice",
          "rejected",
        ].includes(row.state),
    )
  );
}

function flaggedFraction(item: AttemptItem, analysis?: TakeAnalysis) {
  if (!analysis?.coverage_complete) return null;
  const spans = analysis.findings
    .filter((f) => f.severity !== "note")
    .map((f) => [
      Math.max(item.start_s, f.start_s),
      Math.min(item.end_s, f.end_s),
    ])
    .filter(([a, b]) => b > a)
    .sort((a, b) => a[0] - b[0]);
  let end = item.start_s,
    total = 0;
  for (const [a, b] of spans) {
    total += Math.max(0, b - Math.max(a, end));
    end = Math.max(end, b);
  }
  return total / (item.end_s - item.start_s);
}

export default function PerformanceWorkspace({
  projectId,
  takes,
  analyses,
  canEdit,
  onAddRange,
}: {
  projectId: number;
  takes: Take[];
  analyses: TakeAnalysis[];
  canEdit: boolean;
  onAddRange: (take: Take, item: AttemptItem, revision: number) => void;
}) {
  const client = useQueryClient();
  const previousStates = useRef<Record<string, string>>({});
  const [limit, setLimit] = useState(8);
  const [recording, setRecording] = useState(takes[0]?.clip_id ?? "");
  const [selected, setSelected] = useState<string[]>([]);
  const [ranked, setRanked] = useState(false);
  const [statusFilter, setStatusFilter] = useState("all");
  const [audio, setAudio] = useState("");
  const [notice, setNotice] = useState("");
  const [transport, setTransport] = useState<Transport>({
    sequence: 0,
    action: "pause",
  });
  const loaded = takes.slice(0, limit);
  const queries = useQueries({
    queries: loaded.map((take) => ({
      queryKey: key(projectId, take.clip_id),
      queryFn: () => api.attempts(projectId, take.clip_id),
      staleTime: 30_000,
      refetchInterval: (query: { state: { data?: AttemptState } }) =>
        processing(query.state.data?.analysis_state) ? 5000 : false,
    })),
  });
  const taskStates = JSON.stringify(
    queries.map((q, i) => [loaded[i].clip_id, q.data?.analysis_state ?? ""]),
  );
  useEffect(() => {
    const states = Object.fromEntries(JSON.parse(taskStates)) as Record<
      string,
      string
    >;
    if (
      Object.entries(states).some(
        ([clip, state]) =>
          processing(previousStates.current[clip]) && !processing(state),
      )
    ) {
      void client.invalidateQueries({
        queryKey: ["project", projectId],
        predicate: (q) => q.queryKey[2] !== "attempts",
      });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
    }
    previousStates.current = states;
  }, [taskStates, client, projectId]);
  const candidates = queries.flatMap((query, i) =>
    (query.data?.items ?? []).map((item) => ({
      item,
      take: loaded[i],
      data: query.data!,
      risk: flaggedFraction(
        item,
        analyses.find((a) => a.clip_id === loaded[i].clip_id),
      ),
    })),
  );
  const ordered = ranked
    ? [...candidates].sort((a, b) => (a.risk ?? 2) - (b.risk ?? 2))
    : candidates;
  const comparing = selected
    .map((id) => candidates.find((c) => identity(c) === id))
    .filter((c): c is Candidate => Boolean(c));
  const activeAudio = comparing.some((c) => identity(c) === audio)
    ? audio
    : comparing[0]
      ? identity(comparing[0])
      : "";
  const toggle = (id: string) => {
    if (!selected.includes(id) && selected.length >= 4) {
      setNotice(
        "Four simultaneous viewers maximum. Remove one to compare another; all candidates remain available.",
      );
      return;
    }
    setSelected(
      selected.includes(id)
        ? selected.filter((value) => value !== id)
        : [...selected, id],
    );
  };
  return (
    <section
      className="performance-workspace"
      aria-label="Performance attempts"
    >
      <header>
        <div>
          <p className="eyebrow">PERFORMANCE ATTEMPTS</p>
          <h2>One recording can contain several alternatives</h2>
        </div>
        <label>
          <input
            type="checkbox"
            checked={ranked}
            onChange={(e) => setRanked(e.target.checked)}
          />{" "}
          Order by least flagged time
        </label>
      </header>
      <label>
        Review status{" "}
        <select
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
        >
          <option value="all">All candidates</option>
          <option value="proposed">Unresolved</option>
          <option value="reviewed">Reviewed</option>
          <option value="clean">Reviewed clean</option>
          <option value="shortlisted">Shortlisted</option>
          <option value="director_choice">Director choice</option>
          <option value="rejected">Rejected / not preferred</option>
        </select>
      </label>
      <p className="policy-note">
        Compare any candidates, including portions of the same recording. Flags
        are evidence to review, not artistic scores. Shortlist and director
        choice do not automatically change shot selects.
      </p>
      {notice && <p role="status">{notice}</p>}
      {queries.some((q) => q.isPending) && (
        <p role="status">Loading performance candidates…</p>
      )}
      {queries.some((q) => q.isError) && (
        <p role="alert">
          Some recordings could not load.{" "}
          <button
            onClick={() =>
              queries.filter((q) => q.isError).forEach((q) => void q.refetch())
            }
          >
            Retry failed loads
          </button>
        </p>
      )}
      {!candidates.length && !queries.some((q) => q.isPending) && (
        <p>
          No attempt boundaries yet. Mark performances below, or run the updated
          analysis. A full recording is not automatically a clean take.
        </p>
      )}
      <div className="performance-candidates">
        {ordered
          .filter(
            (c) =>
              statusFilter === "all" ||
              (statusFilter === "reviewed"
                ? c.item.state !== "proposed"
                : c.item.state === statusFilter),
          )
          .map((c) => {
            const id = identity(c),
              evidence = c.data.proposals.find(
                (p) => p.attempt_id === c.item.proposal_id,
              );
            return (
              <article
                key={id}
                className={selected.includes(id) ? "active" : ""}
              >
                <label>
                  <input
                    type="checkbox"
                    checked={selected.includes(id)}
                    onChange={() => toggle(id)}
                  />{" "}
                  <strong>{c.item.label}</strong>
                </label>
                <small>
                  {c.take.take_no
                    ? `Slate take ${c.take.take_no}`
                    : "Unnumbered recording"}{" "}
                  · {time(c.item.start_s)}–{time(c.item.end_s)}
                </small>
                <span>
                  {c.item.state.replaceAll("_", " ")} ·{" "}
                  {c.risk === null
                    ? "analysis incomplete"
                    : `${Math.round(c.risk * 100)}% flagged time`}
                </span>
                {evidence && (
                  <details>
                    <summary>Evidence & interpretation</summary>
                    <p>
                      <b>Observed:</b> {evidence.observation}
                    </p>
                    <p>
                      <b>Interpretation:</b> {evidence.interpretation}
                    </p>
                    <p>
                      <b>Review suggestion:</b> {evidence.recommendation}
                    </p>
                    <p>
                      Intent: {evidence.intent}. Model confidence{" "}
                      {Math.round(evidence.confidence * 100)}% — uncalibrated.
                    </p>
                    {(evidence.starts_before_window ||
                      evidence.ends_after_window) && (
                      <p>
                        Boundary incomplete at an analysis-window edge; review
                        or merge manually.
                      </p>
                    )}
                  </details>
                )}
                <button
                  disabled={!canEdit}
                  onClick={() => onAddRange(c.take, c.item, c.data.rev)}
                >
                  Add portion to shot draft
                </button>
              </article>
            );
          })}
      </div>
      {limit < takes.length && (
        <button onClick={() => setLimit((n) => n + 8)}>
          Load next recordings ({takes.length - limit} remaining)
        </button>
      )}
      {comparing.length > 0 && (
        <div
          className="performance-actions"
          aria-label="Group comparison transport"
        >
          <button
            onClick={() =>
              setTransport((t) => ({
                sequence: t.sequence + 1,
                action: "restart",
              }))
            }
          >
            Play from aligned starts
          </button>
          <button
            onClick={() =>
              setTransport((t) => ({
                sequence: t.sequence + 1,
                action: "pause",
              }))
            }
          >
            Pause all
          </button>
          <button
            onClick={() =>
              setTransport((t) => ({
                sequence: t.sequence + 1,
                action: "play",
              }))
            }
          >
            Resume all
          </button>
          <small>
            Set each start offset to the same action or dialogue beat. Browser
            preview, not frame-locked playback.
          </small>
        </div>
      )}
      {comparing.length > 0 && (
        <div className="performance-viewers">
          {comparing.map((c) => (
            <CandidateViewer
              key={identity(c)}
              candidate={c}
              audible={activeAudio === identity(c)}
              onAudio={() => setAudio(identity(c))}
              transport={transport}
            />
          ))}
        </div>
      )}
      <details className="performance-boundaries">
        <summary>Edit boundaries, shortlist or restore a decision</summary>
        <label>
          Recording{" "}
          <select
            value={recording}
            onChange={(e) => setRecording(e.target.value)}
          >
            {takes.map((t) => (
              <option key={t.clip_id} value={t.clip_id}>
                {t.filename || `Slate take ${t.take_no}`} · {time(t.duration_s)}
              </option>
            ))}
          </select>
        </label>
        {recording && (
          <BoundaryEditor
            key={`${projectId}/${recording}`}
            projectId={projectId}
            clipId={recording}
            canEdit={canEdit}
          />
        )}
      </details>
    </section>
  );
}

function CandidateViewer({
  candidate: c,
  audible,
  onAudio,
  transport,
}: {
  candidate: Candidate;
  audible: boolean;
  onAudio: () => void;
  transport: Transport;
}) {
  const player = useRef<PlayerHandle>(null);
  const [offset, setOffset] = useState(0);
  const offsetRef = useRef(offset);
  offsetRef.current = offset;
  useEffect(() => {
    const el = player.current?.element();
    if (!el) return;
    if (transport.action === "pause") el.pause();
    else if (transport.action === "restart")
      player.current?.seek(c.item.start_s + offsetRef.current, true);
    else void el.play().catch(() => {});
  }, [transport, c.item.start_s]);
  useEffect(() => {
    const el = player.current?.element();
    if (el) el.muted = !audible;
  }, [audible]);
  return (
    <section>
      <header>
        <strong>{c.item.label}</strong>
        <button aria-pressed={audible} onClick={onAudio}>
          Listen here
        </button>
      </header>
      <Player
        ref={player}
        src={c.take.proxy_uri}
        onReady={() => {
          const el = player.current?.element();
          if (el) el.muted = !audible;
          player.current?.seek(c.item.start_s + offset);
        }}
        onTimeUpdate={(at) => {
          if (at >= c.item.end_s) player.current?.element()?.pause();
        }}
        onPlay={() => {
          const el = player.current?.element();
          if (
            el &&
            (el.currentTime < c.item.start_s || el.currentTime >= c.item.end_s)
          )
            player.current?.seek(c.item.start_s + offset, true);
        }}
      />
      <label>
        Start offset (seconds){" "}
        <input
          type="number"
          min="0"
          max={Math.max(0, c.item.end_s - c.item.start_s - 0.05)}
          step="0.01"
          value={offset}
          onChange={(e) =>
            setOffset(
              Math.max(
                0,
                Math.min(
                  Number(e.target.value),
                  c.item.end_s - c.item.start_s - 0.05,
                ),
              ),
            )
          }
        />
      </label>
      <button
        onClick={() => player.current?.seek(c.item.start_s + offset, true)}
      >
        Play this attempt
      </button>
      <small>
        Source {time(c.item.start_s)}–{time(c.item.end_s)} · independent
        transport; group controls available above
      </small>
    </section>
  );
}

function BoundaryEditor({
  projectId,
  clipId,
  canEdit,
}: {
  projectId: number;
  clipId: string;
  canEdit: boolean;
}) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: key(projectId, clipId),
    queryFn: () => api.attempts(projectId, clipId),
    refetchInterval: (query) =>
      processing(query.state.data?.analysis_state) ? 5000 : false,
  });
  const [base, setBase] = useState<AttemptState | null>(null);
  const [draft, setDraft] = useState<AttemptItem[]>([]);
  const [undo, setUndo] = useState<AttemptItem[][]>([]),
    [redo, setRedo] = useState<AttemptItem[][]>([]);
  const [saving, setSaving] = useState(false),
    [message, setMessage] = useState("");
  const [history, setHistory] = useState<{ rev: number; count: number }[]>([]);
  const [recovered, setRecovered] = useState<AttemptItem[] | null>(null);
  const storageKey = `trimbin:attempt-draft:${currentIdentity()?.email ?? "anonymous"}:${projectId}:${clipId}`;
  const dirty =
    base !== null && JSON.stringify(draft) !== JSON.stringify(base.items);
  useEffect(() => {
    if (!query.data || base) return;
    setBase(query.data);
    setDraft(query.data.items);
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) || "null");
      if (saved && saved.rev === query.data.rev && validDraft(saved.items))
        setRecovered(saved.items);
      else if (saved)
        setMessage(
          "An older browser draft exists but its revision is stale; it was not applied.",
        );
    } catch {
      /* Storage is optional, server revisions are authoritative. */
    }
  }, [query.data, base, storageKey]);
  useEffect(() => {
    if (!base) return;
    if (!dirty) {
      if (!recovered) {
        try {
          sessionStorage.removeItem(storageKey);
        } catch {
          /* optional storage */
        }
      }
      return;
    }
    try {
      sessionStorage.setItem(
        storageKey,
        JSON.stringify({ rev: base.rev, items: draft }),
      );
    } catch {
      /* unavailable/quota */
    }
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [draft, dirty, base, storageKey, recovered]);
  const edit = (items: AttemptItem[]) => {
    setUndo((stack) => [...stack.slice(-49), draft]);
    setRedo([]);
    setDraft(items);
  };
  const update = (id: string, changes: Partial<AttemptItem>) =>
    edit(draft.map((row) => (row.id === id ? { ...row, ...changes } : row)));
  const valid =
    base &&
    draft.length <= 200 &&
    draft.every(
      (r) =>
        r.label.trim() &&
        Number.isFinite(r.start_s) &&
        Number.isFinite(r.end_s) &&
        r.start_s >= 0 &&
        r.end_s > r.start_s &&
        r.end_s <= base.duration_s,
    );
  const retry = useRef<{ fingerprint: string; id: string } | null>(null);
  const save = async () => {
    if (!base || !valid) return;
    setSaving(true);
    setMessage("");
    const fingerprint = JSON.stringify({ rev: base.rev, items: draft });
    if (retry.current?.fingerprint !== fingerprint)
      retry.current = { fingerprint, id: crypto.randomUUID() };
    try {
      const result = await api.saveAttempts(projectId, clipId, {
        rev: base.rev,
        command_id: retry.current!.id,
        items: draft,
      });
      setBase(result);
      setDraft(result.items);
      setUndo([]);
      setRedo([]);
      setRecovered(null);
      try {
        sessionStorage.removeItem(storageKey);
      } catch {
        /* Saved on the server. */
      }
      client.setQueryData(key(projectId, clipId), result);
      setMessage(
        "Saved. Source footage and existing shot/film portions are unchanged.",
      );
    } catch (error) {
      setMessage(
        `${error instanceof Error ? error.message : "Save failed"} Your draft is retained.`,
      );
    } finally {
      setSaving(false);
    }
  };
  if (query.isPending) return <p>Loading boundaries…</p>;
  if (query.isError)
    return (
      <p role="alert">
        Could not load boundaries.{" "}
        <button onClick={() => void query.refetch()}>Retry</button>
      </p>
    );
  if (!base) return null;
  return (
    <div>
      {message && <p role="status">{message}</p>}
      {query.data?.analysis_state && (
        <p role="status">
          Analysis: {query.data.analysis_state.replaceAll("_", " ")}
          {query.data.analysis_error ? ` — ${query.data.analysis_error}` : ""}.
          Existing decisions stay intact.
        </p>
      )}
      {(query.data?.analysis_changed ||
        (query.data && query.data.rev !== base.rev)) && (
        <p role="status">
          Analysis or saved decisions changed. This draft has not been
          overwritten.
        </p>
      )}
      {recovered && (
        <button
          onClick={() => {
            edit(recovered);
            setRecovered(null);
          }}
        >
          Recover this browser&apos;s unsaved draft
        </button>
      )}
      <fieldset disabled={!canEdit || saving}>
        <div className="performance-actions">
          <button
            disabled={processing(query.data?.analysis_state)}
            onClick={async () => {
              try {
                await api.analyseAttempts(projectId, clipId);
                setMessage(
                  "Full-recording analysis queued. Progress and proposals refresh automatically. Your boundary draft stays intact.",
                );
                await client.invalidateQueries({
                  queryKey: key(projectId, clipId),
                });
              } catch (e) {
                setMessage(
                  e instanceof Error ? e.message : "Could not queue analysis",
                );
              }
            }}
          >
            Analyse performances
          </button>
          <button onClick={() => void query.refetch()}>Refresh evidence</button>
          <button
            onClick={async () => {
              const latest = await query.refetch();
              if (latest.data) {
                setBase(latest.data);
                setDraft(latest.data.items);
                setUndo([]);
                setRedo([]);
                setRecovered(null);
                setMessage(
                  "Loaded the latest saved boundaries; local draft discarded.",
                );
              }
            }}
          >
            Discard draft & load saved
          </button>
          <button
            disabled={!query.data?.proposals.length}
            onClick={() => {
              const ids = new Set(draft.map((r) => r.proposal_id));
              const fresh = (query.data?.proposals ?? []).filter(
                (p) => !ids.has(p.attempt_id),
              );
              if (draft.length + fresh.length > 200) {
                setMessage(
                  "This would exceed 200 candidate boundaries. Review or remove unwanted proposals first.",
                );
                return;
              }
              edit([
                ...draft,
                ...fresh.map((p, i) => ({
                  id: p.attempt_id,
                  proposal_id: p.attempt_id,
                  label: `Attempt ${draft.length + i + 1}`,
                  start_s: p.start_s,
                  end_s: p.end_s,
                  state: "proposed" as const,
                  note: "",
                })),
              ]);
            }}
          >
            Add new proposals to draft
          </button>
          <button
            disabled={!undo.length}
            onClick={() => {
              setRedo((s) => [...s, draft]);
              setDraft(undo[undo.length - 1]);
              setUndo((s) => s.slice(0, -1));
            }}
          >
            Undo draft
          </button>
          <button
            disabled={!redo.length}
            onClick={() => {
              setUndo((s) => [...s, draft]);
              setDraft(redo[redo.length - 1]);
              setRedo((s) => s.slice(0, -1));
            }}
          >
            Redo
          </button>
          <button
            disabled={draft.length >= 200}
            onClick={() =>
              edit([
                ...draft,
                {
                  id: crypto.randomUUID(),
                  proposal_id: null,
                  label: `Attempt ${draft.length + 1}`,
                  start_s: 0,
                  end_s: base.duration_s,
                  state: "proposed",
                  note: "Manually marked; review boundaries.",
                },
              ])
            }
          >
            Mark an attempt
          </button>
          <button
            className="primary"
            disabled={!valid || !dirty}
            onClick={() => void save()}
          >
            {saving ? "Saving…" : "Save boundaries & choices"}
          </button>
        </div>
        {!valid && (
          <p role="alert">
            Use non-empty labels and ranges within the recording, with end after
            start.
          </p>
        )}
        <div className="performance-edit-list">
          {draft.map((row, index) => (
            <div key={row.id}>
              <input
                aria-label={`Attempt ${index + 1} name`}
                maxLength={100}
                value={row.label}
                onChange={(e) => update(row.id, { label: e.target.value })}
              />
              <label>
                In{" "}
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={row.start_s}
                  onChange={(e) =>
                    update(row.id, { start_s: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                Out{" "}
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={row.end_s}
                  onChange={(e) =>
                    update(row.id, { end_s: Number(e.target.value) })
                  }
                />
              </label>
              <select
                aria-label={`${row.label} decision`}
                value={row.state}
                onChange={(e) =>
                  update(row.id, {
                    state: e.target.value as AttemptItem["state"],
                  })
                }
              >
                <option value="proposed">Needs review</option>
                <option value="reviewed">Reviewed</option>
                <option value="clean">Reviewed clean</option>
                <option value="shortlisted">Shortlist</option>
                <option value="director_choice">Director choice</option>
                <option value="rejected">Not preferred</option>
              </select>
              <input
                aria-label={`${row.label} human reason`}
                maxLength={1000}
                placeholder="Human reason / intended technique"
                value={row.note}
                onChange={(e) => update(row.id, { note: e.target.value })}
              />
              <button
                onClick={() => {
                  const middle = (row.start_s + row.end_s) / 2;
                  edit(
                    draft.flatMap((r) =>
                      r.id === row.id
                        ? [
                            { ...r, end_s: middle },
                            {
                              ...r,
                              id: crypto.randomUUID(),
                              label: `${r.label} B`.slice(0, 100),
                              start_s: middle,
                            },
                          ]
                        : [r],
                    ),
                  );
                }}
              >
                Split at midpoint
              </button>
              <button
                disabled={index === draft.length - 1}
                onClick={() => {
                  const next = draft[index + 1];
                  edit(
                    draft.flatMap((r) =>
                      r.id === row.id
                        ? [
                            {
                              ...r,
                              start_s: Math.min(r.start_s, next.start_s),
                              end_s: Math.max(r.end_s, next.end_s),
                              proposal_id: null,
                              note: `Merged: ${r.label} + ${next.label}. ${r.note}`.slice(
                                0,
                                1000,
                              ),
                            },
                          ]
                        : r.id === next.id
                          ? []
                          : [r],
                    ),
                  );
                }}
              >
                Merge with next row
              </button>
              <button
                onClick={() => edit(draft.filter((r) => r.id !== row.id))}
              >
                Remove boundary
              </button>
            </div>
          ))}
        </div>
      </fieldset>
      <p className="policy-note">
        Removing or merging boundaries does not delete video. Splits start at
        the midpoint; set exact in/out above. Overlapping candidates are
        allowed.
      </p>
      <button
        onClick={async () => {
          try {
            setHistory((await api.attemptHistory(projectId, clipId)).versions);
          } catch (e) {
            setMessage(e instanceof Error ? e.message : "History unavailable");
          }
        }}
      >
        Saved decision history
      </button>
      <button
        disabled={!canEdit || saving}
        onClick={async () => {
          try {
            const record = await api.editorialEvidence(projectId, clipId);
            const url = URL.createObjectURL(
              new Blob([JSON.stringify(record, null, 2)], {
                type: "application/json",
              }),
            );
            const link = document.createElement("a");
            link.href = url;
            link.download = `editorial-evidence-${clipId}.json`;
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
            setMessage(
              "Evidence exported without media URLs. Training rights are unverified; this is not a training-ready dataset.",
            );
          } catch (e) {
            setMessage(e instanceof Error ? e.message : "Export unavailable");
          }
        }}
      >
        Export editorial evidence
      </button>
      {history.map((v) => (
        <button
          key={v.rev}
          disabled={!canEdit || saving}
          onClick={async () => {
            try {
              const old = await api.attemptVersion(projectId, clipId, v.rev);
              edit(old.items);
              setMessage(
                `Revision ${v.rev} loaded into draft. Save to restore as a new revision.`,
              );
            } catch (e) {
              setMessage(
                e instanceof Error ? e.message : "Version unavailable",
              );
            }
          }}
        >
          Restore r{v.rev} ({v.count} attempts)
        </button>
      ))}
    </div>
  );
}
