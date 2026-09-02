"use client";

import { useSyncExternalStore } from "react";
import { cancelUpload, dismissUpload, pauseUpload, resumeUpload, subscribeUploads, uploadSnapshots } from "@/lib/upload";
import { api } from "@/lib/api";

const empty: ReturnType<typeof uploadSnapshots> = [];

export default function UploadTray() {
  const batches = useSyncExternalStore(subscribeUploads, uploadSnapshots, () => empty);
  if (!batches.length) return null;
  return <aside className="global-upload-tray" aria-label="Upload progress">{batches.map((batch) => {
    const total = batch.rows.reduce((sum, row) => sum + row.total, 0);
    const sent = batch.rows.reduce((sum, row) => sum + row.sent, 0);
    const pct = total ? Math.round(sent / total * 100) : 0;
    const finished = batch.state === "done" || batch.state === "cancelled" || batch.state === "failed";
    const cancel = () => { cancelUpload(batch.id); void api.cancelUpload(batch.id).catch(() => undefined); };
    return <section key={batch.id}><header><span><b>{batch.state === "done" ? "Upload complete" : batch.state === "paused" ? "Upload paused" : batch.state === "cancelled" ? "Upload cancelled" : "Uploading footage"}</b><small>{batch.rows.filter((row) => row.state === "done").length}/{batch.rows.length} files · {pct}%</small></span><div>{batch.state === "uploading" && <button onClick={() => pauseUpload(batch.id)}>Pause</button>}{batch.state === "paused" && <button onClick={() => resumeUpload(batch.id)}>Resume</button>}{!finished && <button onClick={cancel}>Cancel</button>}{finished && <button onClick={() => dismissUpload(batch.id)}>Dismiss</button>}</div></header><div className="upload-tray-bar"><i style={{ width: `${pct}%` }} /></div></section>;
  })}</aside>;
}
