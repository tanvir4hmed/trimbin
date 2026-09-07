"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import Player, { type PlayerHandle } from "@/components/Player";
import {
  api,
  type FilmSource,
  type FilmState,
  type FilmRange,
} from "@/lib/api";
import { currentIdentity } from "@/lib/auth";
import { paths, projectIdFromSlug } from "@/lib/slug";

const clock = (s: number) =>
  `${Math.floor(s / 60)
    .toString()
    .padStart(2, "0")}:${(s % 60).toFixed(2).padStart(5, "0")}`;
const label = (s: FilmSource) =>
  `Scene ${s.scene_code} · Shot ${s.shot_code} · Take ${s.take_no}`;

export default function FilmPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  return <FilmWorkspace key={slug} projectId={projectIdFromSlug(slug)} />;
}

function FilmWorkspace({ projectId }: { projectId: number }) {
  const [saved, setSaved] = useState<FilmState | null>(null);
  const [rows, setRows] = useState<FilmRange[]>([]);
  const [name, setName] = useState("Film sequence");
  const [sources, setSources] = useState<FilmSource[]>([]);
  const [catalog, setCatalog] = useState<FilmSource[]>([]);
  const [offset, setOffset] = useState(0);
  const [more, setMore] = useState(false);
  const [sourceId, setSourceId] = useState("");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [editing, setEditing] = useState(false);
  const [position, setPosition] = useState(0);
  const [canEdit, setCanEdit] = useState(false);
  const [versions, setVersions] = useState<{ rev: number; name: string }[]>([]);
  const [coverageMode, setCoverageMode] = useState(false);
  const [omissions, setOmissions] = useState<
    Awaited<ReturnType<typeof api.filmCoverage>>["omissions"]
  >([]);
  const [localDraft, setLocalDraft] = useState<{
    name: string;
    rows: FilmRange[];
    rev: number;
  } | null>(null);
  const player = useRef<PlayerHandle>(null);
  const advancing = useRef(false);
  const command = useRef<string | null>(null);
  const active = rows[index];
  const source = sources.find((s) => s.clip_id === active?.clip_id);
  const total = rows.reduce(
    (sum, r) => sum + Math.max(0, r.end_s - r.start_s),
    0,
  );
  const draftKey = () =>
    `trimbin.film-draft.${currentIdentity()?.email ?? "anonymous"}.${projectId}`;
  const recordStart = rows
    .slice(0, index)
    .reduce((sum, r) => sum + Math.max(0, r.end_s - r.start_s), 0);

  function adopt(data: FilmState) {
    setEditing(false);
    setCoverageMode(false);
    setOmissions([]);
    setSaved(data);
    setName(data.name);
    setRows(
      (data.entries ?? []).map(
        ({
          id,
          clip_id,
          start_s,
          end_s,
          note,
          attempt_id,
          attempt_revision,
        }) => ({
          id,
          clip_id,
          attempt_id,
          attempt_revision,
          start_s,
          end_s,
          note,
        }),
      ),
    );
    setSources((old) =>
      Array.from(
        new Map(
          [
            ...old,
            ...(data.entries ?? []).flatMap((e) =>
              e.source ? [e.source] : [],
            ),
          ].map((s) => [s.clip_id, s]),
        ).values(),
      ),
    );
    setDirty(false);
    setIndex(0);
    setPlaying(false);
    command.current = null;
    void api
      .filmHistory(projectId)
      .then((history) => setVersions(history.versions))
      .catch(() => {});
  }
  useEffect(() => {
    let cancelled = false;
    setCanEdit(Boolean(currentIdentity()));
    try {
      const stored = JSON.parse(localStorage.getItem(draftKey()) || "null");
      if (stored && Array.isArray(stored.rows) && stored.rows.length <= 1000)
        setLocalDraft(stored);
    } catch {
      /* An unreadable local draft must not block the saved project. */
    }
    void api
      .film(projectId)
      .then(async (data) => {
        if (cancelled) return;
        adopt(data);
        if (data.rev === 0) {
          setBusy(true);
          try {
            const coverage = await api.filmCoverage(projectId);
            if (!cancelled) showCoverage(coverage, false);
          } finally {
            if (!cancelled) setBusy(false);
          }
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);
  useEffect(() => {
    if (!dirty) return;
    try {
      localStorage.setItem(
        draftKey(),
        JSON.stringify({ name, rows, rev: saved?.rev ?? 0 }),
      );
    } catch {
      /* The visible save warning still applies when local storage is full. */
    }
    const leave = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", leave);
    return () => window.removeEventListener("beforeunload", leave);
  }, [dirty, name, rows, saved?.rev]);
  useEffect(() => {
    advancing.current = false;
    setPosition(active?.start_s ?? 0);
    if (active && source) player.current?.seek(active.start_s, playing);
  }, [active?.id, active?.start_s, source?.clip_id]);
  function edit(next: FilmRange[]) {
    player.current?.element()?.pause();
    setPlaying(false);
    setRows(next);
    setDirty(true);
    command.current = null;
    setMessage("");
    setError("");
    setIndex((i) => Math.min(i, Math.max(0, next.length - 1)));
  }
  function advance() {
    if (!playing || advancing.current) return;
    advancing.current = true;
    player.current?.element()?.pause();
    if (index + 1 < rows.length) setIndex(index + 1);
    else {
      setPlaying(false);
      setMessage("End of sequence.");
    }
  }
  useEffect(() => {
    if (!playing || !active) return;
    let frame = 0;
    const tick = () => {
      const video = player.current?.element();
      if (video && video.currentTime >= active.end_s) advance();
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, index, active?.end_s]);
  const invalid = rows.find((row) => {
    const media = sources.find((s) => s.clip_id === row.clip_id);
    return (
      !media?.proxy_uri ||
      !Number.isFinite(row.start_s) ||
      !Number.isFinite(row.end_s) ||
      row.start_s < 0 ||
      row.end_s <= row.start_s ||
      row.end_s > media.duration_s + 0.001
    );
  });
  async function save() {
    if (!saved || invalid) return;
    setBusy(true);
    setError("");
    command.current ??= crypto.randomUUID();
    try {
      const next = await api.saveFilm(projectId, {
        rev: saved.rev,
        command_id: command.current,
        name,
        ranges: rows,
      });
      adopt(next);
      setMessage(`Saved revision ${next.rev}. Shot selections are unchanged.`);
      try {
        localStorage.removeItem(draftKey());
      } catch {
        /* Saved server state remains authoritative. */
      }
      setLocalDraft(null);
    } catch (e) {
      setError(
        `${e instanceof Error ? e.message : "Could not save."} Your edits are still here. If another editor saved first, reload the saved version before making a new edit.`,
      );
    } finally {
      setBusy(false);
    }
  }
  async function loadSources(nextOffset: number) {
    setBusy(true);
    setError("");
    try {
      const list = await api.filmSources(projectId, nextOffset);
      setCatalog(list.sources);
      setMore(list.more);
      setOffset(nextOffset);
      setSources((old) =>
        Array.from(
          new Map(
            [...old, ...list.sources].map((s) => [s.clip_id, s]),
          ).values(),
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load sources.");
    } finally {
      setBusy(false);
    }
  }
  async function restoreDraft() {
    if (!localDraft || !saved || localDraft.rev !== saved.rev) return;
    setBusy(true);
    setError("");
    try {
      const resolved = await api.resolveFilmSources(
        projectId,
        Array.from(new Set(localDraft.rows.map((r) => r.clip_id))),
      );
      setSources((old) =>
        Array.from(
          new Map(
            [...old, ...resolved.sources].map((s) => [s.clip_id, s]),
          ).values(),
        ),
      );
      setName(localDraft.name);
      edit(localDraft.rows);
      setEditing(true);
      setLocalDraft(null);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not restore source references.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function importCoverage() {
    if (
      !saved ||
      (dirty &&
        !window.confirm(
          "Replace this unsaved draft with the current confirmed selects? The saved sequence stays unchanged.",
        ))
    )
      return;
    setBusy(true);
    setError("");
    try {
      showCoverage(await api.filmCoverage(projectId), false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not import coverage.");
    } finally {
      setBusy(false);
    }
  }
  function showCoverage(
    coverage: Awaited<ReturnType<typeof api.filmCoverage>>,
    asDraft: boolean,
  ) {
    const entries = coverage.preview.entries ?? [];
    setEditing(false);
    player.current?.element()?.pause();
    setPlaying(false);
    setIndex(0);
    setRows(
      entries.map(
        ({
          id,
          clip_id,
          start_s,
          end_s,
          note,
          attempt_id,
          attempt_revision,
        }) => ({
          id,
          clip_id,
          attempt_id,
          attempt_revision,
          start_s,
          end_s,
          note,
        }),
      ),
    );
    setSources((old) =>
      Array.from(
        new Map(
          [...old, ...entries.flatMap((e) => (e.source ? [e.source] : []))].map(
            (s) => [s.clip_id, s],
          ),
        ).values(),
      ),
    );
    setName("Confirmed selects");
    setCoverageMode(true);
    setOmissions(coverage.omissions);
    setDirty(asDraft);
    command.current = null;
    setMessage(
      `Confirmed portions across ${coverage.scene_count} scenes. Scene → shot → selected-range order. This is coverage, not an automatically edited film. Save a sequence to keep your own order.`,
    );
  }
  function download() {
    const blob = new Blob(
      [
        JSON.stringify(
          {
            project_id: projectId,
            name,
            revision: saved?.rev,
            draft: dirty,
            ranges: rows,
          },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob),
      anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `trimbin-${projectId}-film.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }
  return (
    <main className="film-page">
      <header className="film-heading">
        <div>
          <Link href={paths.project(projectId)}>← Project</Link>
          <h1>Film Preview</h1>
          <p>
            Watch confirmed portions across the project, or arrange a saved
            sequence. Original footage and shot selections stay unchanged.
          </p>
        </div>
        <div>
          <button className="ghost" onClick={download} disabled={!rows.length}>
            Export list
          </button>
          {canEdit && !editing && (
            <button
              className="primary"
              disabled={busy || !saved}
              onClick={() => {
                setEditing(true);
                if (!catalog.length) void loadSources(0);
              }}
            >
              Arrange sequence
            </button>
          )}
          {canEdit && editing && (
            <button
              className="primary"
              disabled={busy || (!dirty && !coverageMode) || !!invalid}
              onClick={() => void save()}
            >
              {busy ? "Working…" : "Save sequence"}
            </button>
          )}
        </div>
      </header>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <p role="status" className="hint">
        {message ||
          (dirty
            ? "Unsaved changes — save before leaving this page."
            : saved
              ? `Saved revision ${saved.rev}${saved.updated_by ? ` · ${saved.updated_by.split("@")[0]}` : " · Start with an empty sequence or copy coverage once."}`
              : "Loading sequence…")}
      </p>
      <div className="film-view-modes" aria-label="Preview source">
        <button
          className="ghost small"
          disabled={busy || !saved}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              const [latest, coverage] = await Promise.all([
                api.film(projectId),
                api.filmCoverage(projectId),
              ]);
              const signature = (
                items: { clip_id: string; start_s: number; end_s: number }[],
              ) =>
                JSON.stringify(
                  items.map(({ clip_id, start_s, end_s }) => [
                    clip_id,
                    start_s,
                    end_s,
                  ]),
                );
              const matches =
                signature(rows) === signature(coverage.preview.entries ?? []);
              setMessage(
                `${latest.rev !== saved?.rev ? `Another editor saved revision ${latest.rev}. ` : "Saved revision is current. "}${matches ? "This order matches current shot selects." : "This order differs from current shot selects; that may be intentional."} ${coverage.omissions.length} shots lack confirmed portions. Your draft and saved sequence are unchanged.`,
              );
            } catch (e) {
              setError(
                e instanceof Error
                  ? e.message
                  : "Could not check current decisions.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          Check latest decisions
        </button>
        <button
          className={coverageMode ? "primary small" : "ghost small"}
          disabled={busy}
          onClick={() => void importCoverage()}
        >
          Current confirmed selects
        </button>
        <button
          className={!coverageMode ? "primary small" : "ghost small"}
          disabled={busy || !saved?.rev}
          onClick={() => {
            if (
              !dirty ||
              window.confirm(
                "Discard draft changes and show the saved sequence?",
              )
            )
              void api
                .film(projectId)
                .then(adopt)
                .catch((e) => setError(e.message));
          }}
        >
          Saved sequence
        </button>
        <span className="hint">
          {coverageMode
            ? "Refresh selects to include new shot decisions."
            : "A saved order, independent of scene coverage."}
        </span>
      </div>
      {coverageMode && omissions.length > 0 && (
        <details className="film-omissions">
          <summary>
            {omissions.length} shots have no confirmed playable range — not
            included in this preview
          </summary>
          {omissions.map((gap) => (
            <Link
              key={`${gap.scene}/${gap.shot}`}
              href={paths.shot(projectId, gap.scene, gap.shot)}
            >
              Scene {gap.scene_code} / Shot {gap.shot_code} · {gap.reason}
            </Link>
          ))}
        </details>
      )}
      {localDraft && canEdit && (
        <div className="hint">
          <span>
            An unsaved draft from revision {localDraft.rev} is stored in this
            browser.{" "}
          </span>
          <button
            className="ghost small"
            disabled={busy || !saved || localDraft.rev !== saved.rev}
            onClick={() => void restoreDraft()}
          >
            Restore draft
          </button>
          <button
            className="ghost small"
            onClick={() => {
              try {
                localStorage.removeItem(draftKey());
              } catch {
                /* Storage can be disabled. */
              }
              setLocalDraft(null);
            }}
          >
            Discard local draft
          </button>
          {saved && localDraft.rev !== saved.rev && (
            <span>
              {" "}
              The shared sequence has changed; this draft cannot overwrite it.
            </span>
          )}
        </div>
      )}
      <div className={editing ? "film-grid" : "film-grid preview-only"}>
        <section>
          <div className="film-player">
            <Player
              ref={player}
              src={source?.proxy_uri ?? ""}
              controls={false}
              className="player"
              onReady={() => {
                if (active) player.current?.seek(active.start_s, playing);
              }}
              onTimeUpdate={setPosition}
              onEnded={advance}
              emptyLabel={
                active
                  ? "Source unavailable. Replace or remove this row; it will not be silently skipped."
                  : "No confirmed portions yet. Open a shot to choose ranges, or arrange a sequence from available takes."
              }
            />
          </div>
          <div className="film-transport">
            <button
              className="ghost"
              disabled={!rows.length || !!invalid}
              onClick={() => {
                player.current?.element()?.pause();
                setPlaying(false);
                advancing.current = false;
                setIndex(0);
                setPosition(rows[0].start_s);
                player.current?.seek(rows[0].start_s, false);
              }}
            >
              Back to start
            </button>
            <button
              className="primary"
              disabled={!rows.length || !!invalid}
              onClick={() => {
                if (playing) {
                  player.current?.element()?.pause();
                  setPlaying(false);
                } else {
                  advancing.current = false;
                  setPlaying(true);
                  if (position >= (active?.end_s ?? 0))
                    player.current?.seek(active.start_s, true);
                  else
                    player.current?.seek(
                      Math.max(active.start_s, position),
                      true,
                    );
                }
              }}
            >
              {playing ? "Pause" : "Play sequence"}
            </button>
            <span>
              {clock(
                recordStart +
                  Math.max(
                    0,
                    Math.min(
                      position - (active?.start_s ?? 0),
                      (active?.end_s ?? 0) - (active?.start_s ?? 0),
                    ),
                  ),
              )}{" "}
              / {clock(total)}
            </span>
            <span>
              Row {rows.length ? index + 1 : 0} / {rows.length}
            </span>
          </div>
          <input
            className="film-scrub"
            type="range"
            aria-label="Seek in current source range"
            min={active?.start_s ?? 0}
            max={active?.end_s ?? 1}
            step={0.01}
            value={Math.max(
              active?.start_s ?? 0,
              Math.min(position, active?.end_s ?? 1),
            )}
            disabled={!active}
            onChange={(e) => {
              const time = Number(e.target.value);
              setPosition(time);
              player.current?.seek(time, playing);
            }}
          />
          <p className="hint">
            {source ? label(source) : "No source selected"} · Browser preview,
            not a rendered master. Only listed ranges play.
          </p>
        </section>
        <aside className="film-tools" hidden={!editing}>
          <button
            className="ghost small"
            disabled={dirty}
            title={
              dirty
                ? "Save or reload before closing arrangement"
                : "Return to preview"
            }
            onClick={() => setEditing(false)}
          >
            Close arrangement
          </button>
          <label>
            Sequence name
            <input
              value={name}
              maxLength={100}
              disabled={!canEdit || busy}
              onChange={(e) => {
                setName(e.target.value);
                setDirty(true);
                command.current = null;
              }}
            />
          </label>
          {canEdit && (
            <>
              <h2>Add footage</h2>
              <p>
                Any placed take is available, including alternatives not
                selected for coverage.
              </p>
              <select
                aria-label="Source take"
                value={sourceId}
                onChange={(e) => setSourceId(e.target.value)}
              >
                <option value="">Choose scene / shot / take</option>
                {catalog.map((s) => (
                  <option key={s.clip_id} value={s.clip_id}>
                    {label(s)} · {clock(s.duration_s)}
                  </option>
                ))}
              </select>
              <div className="film-source-pages">
                <button
                  className="ghost small"
                  disabled={!offset || busy}
                  onClick={() => void loadSources(Math.max(0, offset - 100))}
                >
                  Previous
                </button>
                <span>
                  Sources {offset + 1}–{offset + catalog.length}
                </span>
                <button
                  className="ghost small"
                  disabled={!more || busy}
                  onClick={() => void loadSources(offset + 100)}
                >
                  Next
                </button>
              </div>
              <button
                className="ghost"
                disabled={!sourceId || busy || rows.length >= 1000}
                onClick={() => {
                  const s = sources.find((v) => v.clip_id === sourceId);
                  if (s)
                    edit([
                      ...rows,
                      {
                        id: crypto.randomUUID(),
                        clip_id: s.clip_id,
                        attempt_revision: 0,
                        start_s: 0,
                        end_s: s.duration_s,
                        note: "",
                      },
                    ]);
                }}
              >
                Add range
              </button>
              {!rows.length && (
                <button
                  className="ghost"
                  disabled={busy}
                  onClick={() => void importCoverage()}
                >
                  Load current confirmed selects
                </button>
              )}
              <button
                className="ghost"
                disabled={busy}
                onClick={() => {
                  if (
                    !dirty ||
                    window.confirm(
                      "Discard unsaved sequence edits and load the latest saved version?",
                    )
                  )
                    void api
                      .film(projectId)
                      .then(adopt)
                      .catch((e) => setError(e.message));
                }}
              >
                Reload saved sequence
              </button>
            </>
          )}
          {canEdit && versions.length > 0 && (
            <label>
              Saved history
              <select
                aria-label="Restore a saved film revision"
                value=""
                disabled={busy}
                onChange={(e) => {
                  const revision = Number(e.target.value);
                  if (!revision) return;
                  void api
                    .filmVersion(projectId, revision)
                    .then((v) => {
                      setSources((old) =>
                        Array.from(
                          new Map(
                            [
                              ...old,
                              ...(v.entries ?? []).flatMap((r) =>
                                r.source ? [r.source] : [],
                              ),
                            ].map((s) => [s.clip_id, s]),
                          ).values(),
                        ),
                      );
                      setName(v.name);
                      edit(
                        (v.entries ?? []).map(
                          ({
                            id,
                            clip_id,
                            start_s,
                            end_s,
                            note,
                            attempt_id,
                            attempt_revision,
                          }) => ({
                            id,
                            clip_id,
                            attempt_id,
                            attempt_revision,
                            start_s,
                            end_s,
                            note,
                          }),
                        ),
                      );
                      setMessage(
                        `Revision ${revision} loaded as a draft. Save to create a new revision; history stays intact.`,
                      );
                    })
                    .catch((e) => setError(e.message));
                }}
              >
                <option value="">Load an earlier revision…</option>
                {versions.map((v) => (
                  <option key={v.rev} value={v.rev}>
                    Revision {v.rev} · {v.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {!canEdit && <p>Sign in to arrange and save a sequence.</p>}
        </aside>
      </div>
      {!editing && rows.length > 0 && (
        <section className="film-chapters">
          <h2>Playback order</h2>
          <p className="hint">
            Click any portion to preview it. Switch to Arrange sequence to
            change the order.
          </p>
          <div>
            {rows.map((row, i) => {
              const media = sources.find((s) => s.clip_id === row.clip_id);
              return (
                <button
                  key={row.id}
                  className={i === index ? "on" : ""}
                  aria-label={`Preview portion ${i + 1}`}
                  onClick={() => {
                    player.current?.element()?.pause();
                    setPlaying(false);
                    setIndex(i);
                    setPosition(row.start_s);
                    player.current?.seek(row.start_s, false);
                  }}
                >
                  <small>
                    {String(i + 1).padStart(2, "0")} ·{" "}
                    {clock(row.end_s - row.start_s)}
                  </small>
                  <b>
                    {media
                      ? `Scene ${media.scene_code} / ${media.shot_code} · T${media.take_no}`
                      : "Source unavailable"}
                  </b>
                  <span>
                    {clock(row.start_s)} → {clock(row.end_s)}
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      )}
      <section className="film-list" hidden={!editing}>
        <header>
          <h2>Playback order</h2>
          <p>
            In / Out are source seconds. A scene can appear in several rows
            without replaying all its coverage.
          </p>
        </header>
        {invalid && (
          <p className="error">
            A row has an invalid range or missing source. Correct it before
            saving or playing.
          </p>
        )}
        <div className="film-table-scroll">
          <table>
            <thead>
              <tr>
                <th>Order</th>
                <th>Source</th>
                <th>In (s)</th>
                <th>Out (s)</th>
                <th>Duration</th>
                <th>Editorial note</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const s = sources.find((v) => v.clip_id === r.clip_id);
                return (
                  <tr key={r.id} className={i === index ? "active" : ""}>
                    <td>
                      <button
                        className="ghost small"
                        aria-label={`Preview row ${i + 1}`}
                        onClick={() => {
                          setPlaying(false);
                          player.current?.element()?.pause();
                          setIndex(i);
                          setPosition(r.start_s);
                          player.current?.seek(r.start_s);
                        }}
                      >
                        {i + 1} ▷
                      </button>
                    </td>
                    <td>
                      {s ? (
                        <Link
                          href={`${paths.shot(projectId, s.scene, s.shot)}?clip=${r.clip_id}&at=${r.start_s}`}
                        >
                          {label(s)}
                        </Link>
                      ) : (
                        `Unavailable · ${r.clip_id.slice(0, 8)}`
                      )}
                    </td>
                    {(["start_s", "end_s"] as const).map((key) => (
                      <td key={key}>
                        <input
                          type="number"
                          aria-label={`Row ${i + 1} ${key === "start_s" ? "In" : "Out"} seconds`}
                          value={r[key]}
                          step="0.01"
                          min="0"
                          max={s?.duration_s}
                          disabled={!canEdit || busy}
                          onChange={(e) =>
                            edit(
                              rows.map((v) =>
                                v.id === r.id
                                  ? { ...v, [key]: Number(e.target.value) }
                                  : v,
                              ),
                            )
                          }
                        />
                      </td>
                    ))}
                    <td>{clock(Math.max(0, r.end_s - r.start_s))}</td>
                    <td>
                      <input
                        aria-label={`Row ${i + 1} editorial note`}
                        value={r.note ?? ""}
                        maxLength={300}
                        disabled={!canEdit || busy}
                        onChange={(e) =>
                          edit(
                            rows.map((v) =>
                              v.id === r.id
                                ? { ...v, note: e.target.value }
                                : v,
                            ),
                          )
                        }
                      />
                    </td>
                    <td>
                      {canEdit && (
                        <div className="film-row-actions">
                          {[-1, 1].map((direction) => (
                            <button
                              key={direction}
                              className="ghost small"
                              aria-label={`Move row ${i + 1} ${direction < 0 ? "up" : "down"}`}
                              disabled={
                                busy ||
                                i + direction < 0 ||
                                i + direction >= rows.length
                              }
                              onClick={() => {
                                const next = [...rows];
                                [next[i], next[i + direction]] = [
                                  next[i + direction],
                                  next[i],
                                ];
                                edit(next);
                              }}
                            >
                              {direction < 0 ? "↑" : "↓"}
                            </button>
                          ))}
                          <button
                            className="ghost small"
                            disabled={busy || rows.length >= 1000}
                            onClick={() =>
                              edit([
                                ...rows.slice(0, i + 1),
                                { ...r, id: crypto.randomUUID() },
                                ...rows.slice(i + 1),
                              ])
                            }
                          >
                            Duplicate
                          </button>
                          <button
                            className="ghost small"
                            disabled={busy}
                            onClick={() =>
                              edit(rows.filter((v) => v.id !== r.id))
                            }
                          >
                            Remove
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!rows.length && (
          <p className="empty">
            No film sequence yet. Add a take, trim its range, and arrange the
            next shot.
          </p>
        )}
      </section>
    </main>
  );
}
