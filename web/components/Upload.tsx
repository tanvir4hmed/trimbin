"use client";

/**
 * Dropping a shoot day in.
 *
 * The browser talks to Cloud Storage directly. Video never passes through the
 * API — proxying gigabytes through Cloud Run would cost twice, in ingress and
 * again in egress, and would make the service scale with footage volume rather
 * than with request count.
 *
 * The interaction is deliberately shallow. Drop a folder and leave; there is no
 * form to fill, no per-file naming, and nothing to come back to except the
 * result. The job exists before a single byte moves, because the editor is going
 * to close the tab.
 *
 * This replaced the sandbox uploader, which lived on its own page with its own
 * rules. One uploader now, in the project it uploads into: a guest working in a
 * project they made uses exactly this, under the limits stated on the New
 * Project form.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";

type Phase = "idle" | "granting" | "uploading" | "processing" | "done" | "failed";

interface Failure {
  clip_id: string;
  reason: string;
}

export default function Upload({
  projectId,
  onFinished,
}: {
  projectId: number;
  onFinished?: () => void;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [sent, setSent] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ done: number; failed: number; total: number } | null>(null);
  const [failures, setFailures] = useState<Failure[]>([]);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const start = useCallback(async () => {
    if (files.length === 0) return;
    setPhase("granting");
    setError(null);
    setFailures([]);

    try {
      const grant = await api.grantUpload(
        projectId,
        files.map((f) => f.name),
      );

      setPhase("uploading");
      const arrived: string[] = [];

      // Sequential rather than parallel. A shoot day is large files on an
      // office connection, and six at once makes all six slow and the progress
      // bar meaningless. One at a time is honest about what is happening.
      for (const ticket of grant.tickets) {
        const file = files.find((f) => f.name === ticket.filename);
        if (!file) continue;
        try {
          const response = await fetch(ticket.upload_url, {
            method: "PUT",
            headers: ticket.headers,
            body: file,
          });
          if (response.ok) arrived.push(ticket.clip_id);
        } catch {
          // Left out of `arrived`, so the API is never told a file is there
          // when it is not. A queued job for a missing object fails five times
          // and lands in the dead letter queue for no reason.
        }
        setSent((n) => n + 1);
      }

      const result = await api.completeUpload(grant.job_id, arrived);
      setJobId(grant.job_id);
      setPhase("processing");

      if (Number(result.missing) > 0) {
        setError(
          `${result.missing} file${Number(result.missing) === 1 ? "" : "s"} did not arrive and will not be processed.`,
        );
      }
    } catch (e) {
      setPhase("failed");
      setError(
        e instanceof ApiError ? e.message : "Could not start the upload.",
      );
    }
  }, [files, projectId]);

  // Poll while the worker runs. The editor walked away; the job is what they
  // come back to, and a page that stopped watching would show "uploading"
  // forever for work that finished.
  useEffect(() => {
    if (phase !== "processing" || !jobId) return;
    let live = true;

    const tick = async () => {
      try {
        const status = await api.jobStatus(jobId);
        if (!live) return;
        setProgress({
          done: status.completed,
          failed: status.failed,
          total: status.total,
        });
        setFailures(status.failures ?? []);
        if (status.state === "finished" || status.state === "abandoned") {
          setPhase("done");
          onFinished?.();
          return;
        }
      } catch {
        // A failed poll is not a failed job. Keep watching.
      }
      if (live) window.setTimeout(() => void tick(), 4000);
    };

    void tick();
    return () => {
      live = false;
    };
  }, [phase, jobId, onFinished]);

  const busy = phase === "granting" || phase === "uploading" || phase === "processing";

  return (
    <section className="upload">
      {phase === "idle" && (
        <>
          <input
            ref={input}
            type="file"
            multiple
            accept=".mov,.mp4,.mxf,.m4v,.avi,.mkv,.braw,.r3d"
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            aria-label="Choose takes"
          />
          {files.length > 0 && (
            <>
              <ul className="chosen">
                {files.slice(0, 8).map((f) => (
                  <li key={f.name}>
                    {f.name}{" "}
                    <span className="dim small">
                      {(f.size / 1024 ** 2).toFixed(0)} MB
                    </span>
                  </li>
                ))}
                {files.length > 8 && (
                  <li className="dim">and {files.length - 8} more</li>
                )}
              </ul>
              <button type="button" className="primary" onClick={() => void start()}>
                Upload {files.length} take{files.length === 1 ? "" : "s"}
              </button>
            </>
          )}
        </>
      )}

      {phase === "granting" && <p className="waiting">Getting ready…</p>}

      {phase === "uploading" && (
        <div className="upload-progress">
          <p>
            Uploading {sent} of {files.length}
          </p>
          <div className="bar">
            <div style={{ width: `${(sent / files.length) * 100}%` }} />
          </div>
        </div>
      )}

      {phase === "processing" && (
        <div className="upload-progress">
          <p className="waiting">
            Measuring, reading the slates and building proxies.
            {progress && ` ${progress.done + progress.failed} of ${progress.total}.`}
          </p>
          <p className="hint small">
            You can close this. The work carries on and the project updates when
            it lands.
          </p>
        </div>
      )}

      {phase === "done" && progress && (
        <div className="upload-done">
          <p>
            {progress.done} clip{progress.done === 1 ? "" : "s"} in
            {progress.failed > 0 && `, ${progress.failed} could not be used`}.
          </p>
          <button
            type="button"
            className="ghost"
            onClick={() => {
              setPhase("idle");
              setFiles([]);
              setSent(0);
              setProgress(null);
              if (input.current) input.current.value = "";
            }}
          >
            Upload more
          </button>
        </div>
      )}

      {/* Never a silent gap. Somebody who dropped in eight takes and sees six
          needs to know which two and why — the alternative is discovering it
          weeks later in the edit, which is the worst possible time. */}
      {failures.length > 0 && (
        <ul className="rejections">
          {failures.map((f) => (
            <li key={f.clip_id}>
              <span className="mono small">{f.clip_id.slice(0, 8)}</span>{" "}
              {f.reason}
            </li>
          ))}
        </ul>
      )}

      {error && <p className="error small">{error}</p>}
      {busy && phase === "uploading" && (
        <p className="hint small">Keep this tab open until the files are sent.</p>
      )}
    </section>
  );
}
