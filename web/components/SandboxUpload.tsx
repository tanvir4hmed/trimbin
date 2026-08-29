"use client";

/**
 * Upload, for someone with no account.
 *
 * The strongest thing this project can show a stranger in three minutes is
 * their own footage going through it. Everything else on the site is a claim
 * about what happens to video; this is the video.
 *
 * The limits are stated before anything is chosen rather than enforced after.
 * A visitor who picks four clips and is told at the end that three is the
 * maximum has been wasted; one who reads "up to three, thirty seconds each"
 * first has been told the shape of the thing.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";

interface Limits {
  clips: number;
  seconds: number;
}

interface Ticket {
  clip_id: string;
  filename: string;
  upload_url: string;
}

type Stage = "idle" | "granting" | "uploading" | "queued" | "processing" | "done" | "failed";

interface JobStatus {
  state: string;
  total: number;
  completed: number;
  failed: number;
  failures: { clip_id: string; reason: string }[];
}

/** Reasons the pipeline gives, said the way a person would say them. */
const REJECTIONS: Record<string, string> = {
  "sandbox.too_long": "longer than the sandbox allows",
  "clip.too_short": "too short to be a take",
  "clip.black": "black from start to finish",
  "clip.frozen": "a frozen frame throughout",
  "clip.no_video": "no video track we could read",
  "not found in storage": "did not finish uploading",
};

export default function SandboxUpload({
  projectId,
  limits,
  onFinished,
}: {
  projectId: number;
  limits: Limits;
  onFinished?: () => void;
}) {
  const [stage, setStage] = useState<Stage>("idle");
  const [chosen, setChosen] = useState<File[]>([]);
  const [progress, setProgress] = useState(0);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const busy = stage === "granting" || stage === "uploading" || stage === "processing";

  // Poll while the worker runs. Stopped the moment the job closes, because a
  // page left polling a finished job is a page quietly costing requests for
  // nothing.
  useEffect(() => {
    if (!jobId || (stage !== "queued" && stage !== "processing")) return;

    let cancelled = false;
    const tick = async () => {
      try {
        const status = (await api.jobStatus(jobId)) as JobStatus;
        if (cancelled) return;
        setJob(status);
        if (status.state === "done" || status.state === "failed") {
          setStage("done");
          onFinished?.();
        } else {
          setStage("processing");
        }
      } catch {
        // A failed poll is not a failed job. The worker is still going; the
        // next tick will find it.
      }
    };

    void tick();
    const timer = setInterval(tick, 4000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [jobId, stage, onFinished]);

  const choose = (files: FileList | null) => {
    setError(null);
    if (!files) return;
    const picked = Array.from(files).slice(0, limits.clips);
    if (files.length > limits.clips) {
      setError(
        `The sandbox takes ${limits.clips} clips at a time — using the first ${limits.clips}.`,
      );
    }
    setChosen(picked);
  };

  const send = useCallback(async () => {
    if (chosen.length === 0) return;
    setError(null);
    setStage("granting");
    setProgress(0);

    try {
      const grant = await api.grantUpload(
        projectId,
        chosen.map((f) => f.name),
      );

      setStage("uploading");
      const tickets: Ticket[] = grant.tickets;

      // Sequential, not parallel. Three clips is not worth the complexity of
      // concurrent progress, and a visitor on a phone connection is better
      // served by one upload having the whole pipe.
      const arrived: string[] = [];
      for (let i = 0; i < tickets.length; i++) {
        const file = chosen.find((f) => f.name === tickets[i].filename) ?? chosen[i];
        const ok = await put(tickets[i].upload_url, file, (fraction) =>
          setProgress((i + fraction) / tickets.length),
        );
        if (ok) arrived.push(tickets[i].clip_id);
      }

      if (arrived.length === 0) {
        throw new Error("Nothing finished uploading.");
      }

      await api.completeUpload(grant.job_id, arrived);
      setJobId(grant.job_id);
      setStage("queued");
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) {
        // The quota message from the server, which knows the numbers.
        setError(e.message);
      } else {
        setError(e instanceof Error ? e.message : "The upload did not go through.");
      }
      setStage("failed");
    }
  }, [chosen, projectId]);

  const reset = () => {
    setStage("idle");
    setChosen([]);
    setJob(null);
    setJobId(null);
    setProgress(0);
    setError(null);
    if (input.current) input.current.value = "";
  };

  return (
    <section className="sandbox">
      <h2>Try it on your own footage</h2>
      <p className="dim small">
        Up to {limits.clips} clips, {limits.seconds} seconds each, no account.
        Shoot the same thing {limits.clips} times so there is something to
        compare — the system only compares takes of one camera setup.
      </p>
      <p className="dim small">
        Everything you upload here is deleted within a day.
      </p>

      {stage === "idle" || stage === "failed" ? (
        <>
          <input
            ref={input}
            type="file"
            accept="video/*"
            multiple
            onChange={(e) => choose(e.target.files)}
            aria-label="Choose clips"
          />
          {chosen.length > 0 && (
            <ul className="chosen">
              {chosen.map((f) => (
                <li key={f.name}>
                  {f.name} <span className="dim">{(f.size / 1e6).toFixed(1)} MB</span>
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            className="primary"
            disabled={chosen.length === 0}
            onClick={() => void send()}
          >
            Upload {chosen.length || ""} clip{chosen.length === 1 ? "" : "s"}
          </button>
        </>
      ) : null}

      {stage === "granting" && <p className="waiting">Asking for somewhere to put them…</p>}

      {stage === "uploading" && (
        <div className="upload-progress">
          <div className="bar">
            <div style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
          <p className="dim small">
            Uploading — {Math.round(progress * 100)}%. This goes straight to
            storage, not through us.
          </p>
        </div>
      )}

      {(stage === "queued" || stage === "processing") && (
        <div className="waiting">
          <p>
            Measuring, reading the slate and encoding
            {job ? ` — ${job.completed + job.failed} of ${job.total}` : ""}.
          </p>
          <p className="dim small">
            A minute or two per clip. You can leave this page; the work carries
            on without it.
          </p>
        </div>
      )}

      {stage === "done" && job && (
        <div className="upload-done">
          <p>
            {job.completed} clip{job.completed === 1 ? "" : "s"} went through
            {job.failed > 0 && `, ${job.failed} could not`}.
          </p>

          {job.failures.length > 0 && (
            // Never a silent gap. Someone who uploaded three and sees two needs
            // to know which one and why.
            <ul className="rejections">
              {job.failures.map((f) => (
                <li key={f.clip_id}>
                  {REJECTIONS[f.reason] ?? f.reason}
                </li>
              ))}
            </ul>
          )}

          {job.completed >= 2 ? (
            <p>
              Two or more takes arrived, so there is something to compare. Open
              the setup below and press <strong>Compare the takes</strong>.
            </p>
          ) : (
            <p className="dim small">
              Comparison needs at least two takes of the same setup.
            </p>
          )}

          <button type="button" onClick={reset}>
            Upload more
          </button>
        </div>
      )}

      {error && <p className="error">{error}</p>}

      {busy && stage !== "uploading" && <span className="sr-only">Working</span>}
    </section>
  );
}

/**
 * PUT one file to its signed URL, reporting progress.
 *
 * XMLHttpRequest rather than fetch, only because fetch still cannot report
 * upload progress. On a phone connection a thirty-second clip is long enough
 * that a bar is the difference between waiting and giving up.
 */
function put(
  url: string,
  file: File,
  onProgress: (fraction: number) => void,
): Promise<boolean> {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => resolve(xhr.status >= 200 && xhr.status < 300);
    xhr.onerror = () => resolve(false);
    xhr.send(file);
  });
}
