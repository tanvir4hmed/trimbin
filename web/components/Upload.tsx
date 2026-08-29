"use client";

/**
 * Drop a shoot folder, watch it land, confirm only what had to be guessed.
 *
 * Three things this has to get right, and the previous version got none of them:
 *
 * A **destination**. Footage goes into a scene and a shot, and an editor who
 * already has a shot list should be able to say which. Reading it off the slate
 * stays the default.
 *
 * A **cross-check**. A clip sent to 12C whose slate reads 15B is usually a file
 * from the wrong folder. It is kept where it was sent and flagged, because
 * moving somebody's footage on a slate reading is how a shoot day scatters.
 *
 * **Live progress**. The last version told you nothing until you reloaded, and
 * often not then.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { JobStatus, PlannedScene } from "@/lib/api";
import { ApiError, api } from "@/lib/api";

type Phase = "choosing" | "uploading" | "processing" | "done" | "failed";

export default function Upload({
  projectId,
  plan,
  onFinished,
}: {
  projectId: number;
  plan: PlannedScene[];
  onFinished?: () => void;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [scene, setScene] = useState(0);
  const [shot, setShot] = useState(0);
  const [phase, setPhase] = useState<Phase>("choosing");
  const [sent, setSent] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const shots = plan.find((s) => s.scene === scene)?.shots ?? [];

  const accept = (list: FileList | null) => {
    setFiles(Array.from(list ?? []));
    setError(null);
  };

  const start = useCallback(async () => {
    if (files.length === 0) return;
    setPhase("uploading");
    setError(null);

    try {
      const target = scene && shot ? { scene, shot } : undefined;
      const grant = await api.grantUpload(
        projectId,
        files.map((f) => f.name),
        target,
      );

      const arrived: string[] = [];
      const names: Record<string, string> = {};

      // One at a time. A shoot folder is large files on an office connection,
      // and six in parallel makes all six slow and the progress meaningless.
      for (const ticket of grant.tickets) {
        const file = files.find((f) => f.name === ticket.filename);
        if (!file) continue;
        try {
          const response = await fetch(ticket.upload_url, {
            method: "PUT",
            headers: ticket.headers,
            body: file,
          });
          if (response.ok) {
            arrived.push(ticket.clip_id);
            names[ticket.clip_id] = ticket.filename;
          }
        } catch {
          // Left out of `arrived`, so the API is never told a file is there
          // when it is not.
        }
        setSent((n) => n + 1);
      }

      const result = await api.completeUpload(grant.job_id, arrived, names);
      setJobId(grant.job_id);
      setPhase("processing");

      if (Number(result.missing) > 0) {
        setError(`${result.missing} file(s) did not reach storage.`);
      }
    } catch (e) {
      setPhase("failed");
      setError(e instanceof ApiError ? e.message : "Upload could not start.");
    }
  }, [files, projectId, scene, shot]);

  // Poll while the workers run. The editor closed the tab or did not; either
  // way the screen has to say where things are without being reloaded.
  useEffect(() => {
    if (phase !== "processing" || !jobId) return;
    let live = true;

    const tick = async () => {
      try {
        const found = await api.jobStatus(jobId);
        if (!live) return;
        setStatus(found);
        if (found.done) {
          setPhase("done");
          onFinished?.();
          return;
        }
      } catch {
        // A failed poll is not a failed job.
      }
      if (live) window.setTimeout(() => void tick(), 3000);
    };

    void tick();
    return () => {
      live = false;
    };
  }, [phase, jobId, onFinished]);

  const reset = () => {
    setPhase("choosing");
    setFiles([]);
    setSent(0);
    setStatus(null);
    setJobId(null);
    setError(null);
    if (input.current) input.current.value = "";
  };

  return (
    <section className="upload">
      {phase === "choosing" && (
        <>
          <div className="target">
            <label>
              Scene
              <select
                value={scene}
                onChange={(e) => {
                  setScene(Number(e.target.value));
                  setShot(0);
                }}
              >
                <option value={0}>Read from the slate</option>
                {plan.map((s) => (
                  <option key={s.scene} value={s.scene}>
                    {s.scene}
                    {s.heading ? ` · ${s.heading}` : ""}
                  </option>
                ))}
              </select>
            </label>

            {scene > 0 && (
              <label>
                Shot
                <select value={shot} onChange={(e) => setShot(Number(e.target.value))}>
                  <option value={0}>Read from the slate</option>
                  {shots.map((h) => (
                    <option key={h.shot} value={h.shot}>
                      {h.slug || `Shot ${h.shot}`}
                      {h.description ? ` · ${h.description}` : ""}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <span className="hint small">
              {scene && shot
                ? "Clips whose slate says otherwise will be flagged, not moved."
                : "Slates decide where each clip goes."}
            </span>
          </div>

          <div
            className={dragging ? "drop over" : "drop"}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              accept(e.dataTransfer.files);
            }}
            onClick={() => input.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") input.current?.click();
            }}
          >
            <div className="dt">Drop the shoot folder here</div>
            <div className="ds">No naming, no forms.</div>
            <input
              ref={input}
              type="file"
              multiple
              hidden
              accept=".mov,.mp4,.mxf,.m4v,.avi,.mkv,.braw,.r3d"
              onChange={(e) => accept(e.target.files)}
            />
          </div>

          {files.length > 0 && (
            <div className="actions">
              <button type="button" className="primary" onClick={() => void start()}>
                Upload {files.length} file{files.length === 1 ? "" : "s"}
              </button>
              <button type="button" className="ghost" onClick={reset}>
                Clear
              </button>
              <span className="note">
                {(files.reduce((n, f) => n + f.size, 0) / 1024 ** 3).toFixed(2)} GB
              </span>
            </div>
          )}
        </>
      )}

      {phase === "uploading" && (
        <div className="ustat">
          <span>
            <b>{sent}</b> of {files.length} uploaded
          </span>
          <div className="pbar">
            <i style={{ width: `${(sent / files.length) * 100}%` }} />
          </div>
          <span className="mono small">Keep this tab open.</span>
        </div>
      )}

      {(phase === "processing" || phase === "done") && status && (
        <>
          <div className="ustat">
            <span>
              <b>
                {status.completed + status.failed} of {status.total}
              </b>{" "}
              {status.done ? "processed" : "· measuring, reading slates, building proxies"}
            </span>
            <div className="pbar">
              <i
                style={{
                  width: `${
                    status.total
                      ? ((status.completed + status.failed) / status.total) * 100
                      : 0
                  }%`,
                }}
              />
            </div>
            <span className="mono small">
              {status.done ? "done" : `${Math.round(((status.completed + status.failed) / Math.max(status.total, 1)) * 100)}%`}
            </span>
          </div>

          {status.groups.length > 0 && (
            <>
              <div className="sect">
                {status.needs_a_look === 0
                  ? `${status.groups.length} shot${status.groups.length === 1 ? "" : "s"} · all slates read cleanly`
                  : `${status.needs_a_look} of ${status.groups.length} need a look`}
              </div>

              {status.groups.map((g) => (
                <div
                  key={`${g.scene}-${g.shot}`}
                  className={g.status === "clean" ? "grp" : "grp amber"}
                >
                  <div
                    className="gicon"
                    style={
                      g.status === "clean"
                        ? undefined
                        : { background: "var(--amber-soft)", color: "var(--amber)" }
                    }
                  >
                    {g.status === "clean" ? "✓" : "!"}
                  </div>
                  <div className="gmain">
                    <div className="gt">
                      Scene {g.scene} · Shot {g.shot} — {g.takes} take
                      {g.takes === 1 ? "" : "s"}
                    </div>
                    <div className="gs">
                      {g.status === "mismatch"
                        ? `${g.mismatches.length} clip(s) sent here but slated elsewhere`
                        : g.status === "unread"
                          ? `${g.unread_slates} slate(s) could not be read`
                          : "Slate read cleanly"}
                    </div>
                    {g.mismatches.map((m, i) => (
                      <div key={i} className="gmis">
                        <span className="mono">{m.filename || "clip"}</span> — {m.detail}
                      </div>
                    ))}
                  </div>
                  <span className="scount">{g.takes}</span>
                </div>
              ))}
            </>
          )}

          {status.failures.length > 0 && (
            <div className="fail">
              <span>
                <b>
                  {status.failed} of {status.total} could not be processed
                </b>
              </span>
              <ul className="rejections">
                {status.failures.map((f) => (
                  <li key={f.clip_id}>
                    <span className="mono small">{f.clip_id.slice(0, 8)}</span> {f.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {phase === "done" && (
            <div className="actions">
              <button type="button" className="primary" onClick={reset}>
                Upload more
              </button>
            </div>
          )}
          {phase === "processing" && (
            <p className="hint small">
              You can close this. Work continues and the project updates when it lands.
            </p>
          )}
        </>
      )}

      {phase === "processing" && !status && (
        <p className="waiting">Queued.</p>
      )}

      {error && <p className="error small">{error}</p>}
    </section>
  );
}
