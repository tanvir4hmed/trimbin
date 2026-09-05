"use client";

import { useEffect, useSyncExternalStore } from "react";
import {
  cancelUpload,
  dismissUpload,
  pauseUpload,
  restoreUploadSnapshots,
  resumeUpload,
  subscribeUploads,
  uploadSnapshots,
} from "@/lib/upload";
import { api } from "@/lib/api";

const empty: ReturnType<typeof uploadSnapshots> = [];

export default function UploadTray() {
  useEffect(() => restoreUploadSnapshots(), []);
  const batches = useSyncExternalStore(
    subscribeUploads,
    uploadSnapshots,
    () => empty,
  );
  if (!batches.length) return null;
  return (
    <aside className="global-upload-tray" aria-label="Upload progress">
      {batches.map((batch) => {
        const total = batch.rows.reduce((sum, row) => sum + row.total, 0);
        const sent = batch.rows.reduce((sum, row) => sum + row.sent, 0);
        const pct = total ? Math.round((sent / total) * 100) : 0;
        const finished =
          batch.state === "done" ||
          batch.state === "cancelled" ||
          batch.state === "failed";
        const cancel = () => {
          cancelUpload(batch.id);
          void api.cancelUpload(batch.id).catch(() => undefined);
        };
        const failed = batch.rows.filter((row) => row.state === "failed");
        return (
          <section key={batch.id}>
            <header>
              <span>
                <b>
                  {batch.state === "done"
                    ? "Upload complete"
                    : batch.state === "failed"
                      ? "Upload needs attention"
                      : batch.state === "interrupted"
                        ? "Upload interrupted"
                        : batch.state === "paused"
                          ? "Upload paused"
                          : batch.state === "cancelled"
                            ? "Upload cancelled"
                            : "Uploading footage"}
                </b>
                <small>
                  {batch.state === "interrupted"
                    ? "Return to this project's ingest page and reselect the same files to resume"
                    : batch.state === "failed"
                      ? `${failed.length} failed after automatic retries · ${batch.rows.filter((row) => row.state === "done").length} uploaded`
                      : `${batch.rows.filter((row) => row.state === "done").length}/${batch.rows.length} files · ${pct}%`}
                </small>
              </span>
              <div>
                {batch.state === "uploading" && (
                  <button onClick={() => pauseUpload(batch.id)}>Pause</button>
                )}
                {batch.state === "paused" && (
                  <button onClick={() => resumeUpload(batch.id)}>Resume</button>
                )}
                {!finished && batch.state !== "interrupted" && (
                  <button onClick={cancel}>Cancel</button>
                )}
                {finished && (
                  <button onClick={() => dismissUpload(batch.id)}>
                    Dismiss
                  </button>
                )}
              </div>
            </header>
            <div className="upload-tray-bar">
              <i style={{ width: `${pct}%` }} />
            </div>
            {failed.length > 0 && (
              <details>
                <summary>Show failed files</summary>
                {failed.map((row) => (
                  <p key={row.clipId}>
                    {row.filename}: {row.error || "upload failed"}
                  </p>
                ))}
              </details>
            )}
          </section>
        );
      })}
    </aside>
  );
}
