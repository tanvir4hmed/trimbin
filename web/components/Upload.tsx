"use client";

/**
 * Add files → read slates → verify matches → ingest.
 *
 * Four steps because that is what actually happens, and because the third one
 * needs a person. The system reads every board it can, and a clip whose board
 * disagrees with the folder it came from is exactly the file somebody dragged
 * from the wrong place — worth catching now rather than in the cut.
 *
 * Nothing moves or deletes without confirmation, which is why the verify step is
 * a step rather than a toast.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import PlacementInbox from "@/components/PlacementInbox";
import type { JobStatus, PlannedScene } from "@/lib/api";
import { ApiError, api } from "@/lib/api";
import { type Progress, uploadAll } from "@/lib/upload";

type Step = "files" | "sending" | "reading" | "done";

const STEPS: { key: Step; n: number; label: string }[] = [
  { key: "files", n: 1, label: "Add files" },
  { key: "sending", n: 2, label: "Send" },
  { key: "reading", n: 3, label: "Read slates" },
  { key: "done", n: 4, label: "Verify & ingest" },
];

export default function Upload({
  projectId,
  plan,
  canResolve = true,
  onFinished,
}: {
  projectId: number;
  plan: PlannedScene[];
  canResolve?: boolean;
  onFinished?: () => void;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [scene, setScene] = useState(0);
  const [shot, setShot] = useState(0);
  const [step, setStep] = useState<Step>("files");
  const [rows, setRows] = useState<Progress[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const shots = plan.find((s) => s.scene === scene)?.shots ?? [];

  const start = useCallback(async () => {
    if (files.length === 0) return;
    setStep("sending");
    setError(null);

    try {
      const grant = await api.grantUpload(
        projectId,
        files.map((f) => f.name),
        scene && shot ? { scene, shot } : scene ? { scene, shot: 0 } : undefined,
      );

      const { arrived, names } = await uploadAll(grant.tickets, files, setRows);
      const result = await api.completeUpload(grant.job_id, arrived, names);

      setJobId(grant.job_id);
      setStep("reading");
      if (Number(result.missing) > 0) {
        setError(`${result.missing} file(s) did not reach storage.`);
      }
    } catch (e) {
      setStep("files");
      setError(e instanceof ApiError ? e.message : "Upload could not start.");
    }
  }, [files, projectId, scene, shot]);

  // Poll while the workers run. An editor who walked away comes back to this
  // screen; it has to say where things are without being reloaded.
  useEffect(() => {
    if (step !== "reading" || !jobId) return;
    let live = true;

    const tick = async () => {
      try {
        const found = await api.jobStatus(jobId);
        if (!live) return;
        setStatus(found);
        if (found.done) {
          setStep("done");
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
  }, [step, jobId, onFinished]);

  const reset = () => {
    setStep("files");
    setFiles([]);
    setRows([]);
    setStatus(null);
    setJobId(null);
    setError(null);
    if (input.current) input.current.value = "";
  };

  const sent = rows.filter((r) => r.state === "done").length;
  const bytesSent = rows.reduce((n, r) => n + r.sent, 0);
  const bytesTotal = rows.reduce((n, r) => n + r.total, 0);
  const activeStep = STEPS.findIndex((s) => s.key === step);

  return (
    <section className="upload">
      <ol className="stepper">
        {STEPS.map((s, i) => (
          <li
            key={s.key}
            className={i === activeStep ? "on" : i < activeStep ? "past" : ""}
          >
            <span className="sn">{i < activeStep ? "✓" : s.n}</span>
            {s.label}
          </li>
        ))}
      </ol>

      {step === "files" && (
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
                ? "Clips whose slate says otherwise are flagged, not moved."
                : scene
                  ? "This scene; the slates sort the shots inside it."
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
              setFiles(Array.from(e.dataTransfer.files));
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
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
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

      {step === "sending" && (
        <>
          <div className="ustat">
            <span>
              <b>{sent}</b> of {rows.length} sent
            </span>
            <div className="pbar">
              <i style={{ width: `${bytesTotal ? (bytesSent / bytesTotal) * 100 : 0}%` }} />
            </div>
            <span className="mono small">
              {(bytesSent / 1024 ** 3).toFixed(2)} / {(bytesTotal / 1024 ** 3).toFixed(2)} GB
            </span>
          </div>

          {/* Per file, because "sending" over forty files says nothing about
              which one is stuck. */}
          <ul className="file-rows">
            {rows.map((r) => (
              <li key={r.clipId} className={r.state}>
                <span className="fr-name mono">{r.filename}</span>
                <span className="pbar thin">
                  <i style={{ width: `${r.total ? (r.sent / r.total) * 100 : 0}%` }} />
                </span>
                <span className="fr-state">
                  {r.state === "failed" ? (r.error ?? "failed") : r.state}
                </span>
              </li>
            ))}
          </ul>

          <p className="hint small">
            Interrupted uploads resume. Closing this tab does not lose what has
            already been sent.
          </p>
        </>
      )}

      {(step === "reading" || step === "done") && (
        <>
          <div className="ustat">
            <span>
              <b>
                {(status?.completed ?? 0) + (status?.failed ?? 0)} of {status?.total ?? 0}
              </b>{" "}
              {step === "done"
                ? "processed"
                : "· measuring, reading slates, building proxies"}
            </span>
            <div className="pbar">
              <i
                style={{
                  width: `${
                    status?.total
                      ? ((status.completed + status.failed) / status.total) * 100
                      : 0
                  }%`,
                }}
              />
            </div>
            <span className="mono small">{step === "done" ? "done" : "working"}</span>
          </div>

          {status && status.groups.length > 0 && (
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
                  <div className="gicon">{g.status === "clean" ? "✓" : "!"}</div>
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
                  </div>
                  <span className="scount">{g.takes}</span>
                </div>
              ))}
            </>
          )}

          {status && status.failures.length > 0 && (
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

          {/* The verify step. Rows appear as the workers land clips, so this is
              here during processing too rather than only at the end. */}
          <PlacementInbox projectId={projectId} plan={plan} canResolve={canResolve} />

          {step === "done" && (
            <div className="actions">
              <button type="button" className="primary" onClick={reset}>
                Upload more
              </button>
            </div>
          )}
          {step === "reading" && (
            <p className="hint small">
              You can close this. Work carries on and the project updates when it
              lands.
            </p>
          )}
        </>
      )}

      {error && <p className="error small">{error}</p>}
    </section>
  );
}
