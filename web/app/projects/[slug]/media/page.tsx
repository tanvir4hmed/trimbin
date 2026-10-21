"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { projectIdFromSlug } from "@/lib/slug";
import { mediaRequest, uploadIdentity, verifyUploadPrefix, type MediaSource, type MediaUpload } from "@/lib/media";

export default function MediaPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const project = projectIdFromSlug(slug);
  const [sources, setSources] = useState<MediaSource[]>([]);
  const [roots, setRoots] = useState<string[]>([]);
  const [alias, setAlias] = useState("");
  const [relative, setRelative] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [playback, setPlayback] = useState("");
  const [page, setPage] = useState(0);
  const [relinkId, setRelinkId] = useState<string | null>(null);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [pendingUploads, setPendingUploads] = useState<MediaUpload[]>([]);
  const [resumeId, setResumeId] = useState("");

  const refresh = useCallback(async () => {
    const data = await mediaRequest<MediaSource[]>(`/${project}/sources?offset=${page * 50}`);
    setSources(data);
    setPendingUploads(await mediaRequest<MediaUpload[]>(`/${project}/uploads`).catch(() => []));
  }, [project, page]);

  useEffect(() => {
    let active = true;
    mediaRequest<{ enabled: boolean }>("/status").then((status) => {
      if (active) setEnabled(status.enabled);
    }).catch((e) => { if (active) setError(String(e.message)); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!enabled) return;
    void refresh().catch((e) => setError(e.message));
    void mediaRequest<string[]>(`/${project}/roots`).then((data) => {
      setRoots(data); setAlias(data[0] ?? "");
    }).catch(() => setRoots([]));
    const timer = setInterval(() => void refresh().catch((e) => setError(e.message)), 5000);
    return () => clearInterval(timer);
  }, [enabled, project, refresh]);

  async function action(work: () => Promise<void>) {
    setBusy(true); setError("");
    try { await work(); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not complete the operation."); }
    finally { setBusy(false); }
  }

  async function upload() {
    if (!file) return;
    const key = uploadIdentity(project, file);
    const saved = resumeId || localStorage.getItem(key);
    let session = saved
      ? await mediaRequest<MediaUpload>(`/${project}/uploads/${saved}`)
      : await mediaRequest<MediaUpload>(`/${project}/uploads`, {
          method: "POST", body: JSON.stringify({ filename: file.name, expected_bytes: file.size }),
        });
    localStorage.setItem(key, session.id);
    setMessage("Checking previously uploaded bytes…");
    await verifyUploadPrefix(file, session);
    const chunkSize = session.chunk_bytes ?? 8 * 1024 * 1024;
    while (session.received_bytes < file.size) {
      const offset = session.received_bytes;
      setMessage(`Uploading ${Math.round(offset / file.size * 100)}%`);
      session = await mediaRequest<MediaUpload>(`/${project}/uploads/${session.id}?offset=${offset}`, {
        method: "PUT", body: file.slice(offset, Math.min(offset + chunkSize, file.size)),
        headers: { "Content-Type": "application/octet-stream" },
      });
    }
    await mediaRequest(`/${project}/uploads/${session.id}/complete`, { method: "POST" });
    localStorage.removeItem(key);
    setResumeId("");
    setMessage("Upload saved. Indexing and proxy processing are queued.");
  }

  async function discard() {
    const key = file ? uploadIdentity(project, file) : null;
    const saved = resumeId || (key ? localStorage.getItem(key) : null);
    if (!saved) return;
    await mediaRequest(`/${project}/uploads/${saved}`, { method: "DELETE" });
    if (key) localStorage.removeItem(key);
    setResumeId(""); setMessage("Pending upload discarded.");
  }

  return <main className="shell" style={{ maxWidth: 1100, padding: "2rem" }}>
    <Link href={`/projects/${slug}/ingest`}>Back to ingest</Link>
    <h1>Media library</h1>
    <p>Upload footage or index files already mounted on this deployment. Originals remain unchanged.</p>
    {enabled === null && <p>Checking media storage…</p>}
    {enabled === false && <p>Media storage is not configured on this deployment yet.</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {enabled && <>
      <section style={{ marginBlock: "2rem" }}>
        <h2>Upload footage</h2>
        <p>If interrupted, reselect the same file and choose Upload / resume. Previously received bytes are verified before continuing.</p>
        <input type="file" aria-label="Footage file" disabled={busy} accept=".mov,.mp4,.m4v,.mkv,.avi,.mxf"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        {pendingUploads.length > 0 && <label>Pending upload <select disabled={busy} value={resumeId} onChange={(e) => setResumeId(e.target.value)}>
          <option value="">Match this file automatically</option>
          {pendingUploads.map((item) => <option key={item.id} value={item.id}>{item.filename} — {Math.round(item.received_bytes / item.expected_bytes * 100)}%</option>)}
        </select></label>}
        <button disabled={busy || !file} onClick={() => void action(upload)}>Upload / resume</button>{" "}
        <button disabled={busy || (!file && !resumeId)} onClick={() => void action(discard)}>Discard pending upload</button>
        <p role="status">{message}</p>
      </section>
      {roots.length > 0 && <section style={{ marginBlock: "2rem" }}>
        <h2>{relinkId ? "Relink original" : "Mounted footage"}</h2>
        <p>Select a configured server folder and enter the file path inside it. Relinking requires identical file content and project-owner access.</p>
        <label>Media root <select value={alias} onChange={(e) => setAlias(e.target.value)}>
          {roots.map((root) => <option key={root}>{root}</option>)}
        </select></label>{" "}
        <label>Relative file path <input value={relative} onChange={(e) => setRelative(e.target.value)} placeholder="day-1/camera-a/take.mov" /></label>{" "}
        <button disabled={busy || !relative || !alias} onClick={() => void action(async () => {
          await mediaRequest(`/${project}/sources${relinkId ? `/${relinkId}/location` : ""}`, {
            method: relinkId ? "PUT" : "POST", body: JSON.stringify({ root_alias: alias, relative_path: relative }),
          }); setRelative(""); setRelinkId(null);
        })}>{relinkId ? "Verify and relink" : "Index file"}</button>
        {relinkId && <button onClick={() => setRelinkId(null)}>Cancel relink</button>}
      </section>}
      {playback && <video key={playback} src={playback} controls style={{ width: "100%", maxHeight: 500 }}
        onError={() => setError("Playback link may have expired or media is unavailable. Choose Preview again.")} />}
      <h2>Sources</h2>
      <p>Preview indexed footage and check its processing status here.</p>
      <table style={{ width: "100%", textAlign: "left" }}><thead><tr><th>File</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody>{sources.map((item) => <tr key={item.id}>
          <td><strong>{item.filename}</strong><br /><small>{item.root_alias}/{item.relative_path}</small>
            {item.duplicate_of && <p>Duplicate content: {item.duplicate_of}</p>}</td>
          <td>{item.state} · {item.stage}{!item.available && <p>Original missing or unavailable</p>}
            {item.error_code && <p>{item.error_code.replaceAll("_", " ")}</p>}</td>
          <td>
            {item.available_files.includes("proxy") && <button disabled={busy} onClick={() => void action(async () => {
              const ticket = await mediaRequest<{ url: string }>(`/${project}/sources/${item.id}/access/proxy`, { method: "POST" });
              setPlayback(`/api${ticket.url}`);
            })}>Preview</button>}{" "}
            {roots.length > 0 && <button disabled={busy} onClick={() => setRelinkId(item.id)}>Relink</button>}{" "}
            {["failed", "cancelled"].includes(item.state) && <button disabled={busy} onClick={() => void action(async () => {
              await mediaRequest(`/${project}/sources/${item.id}/retry`, { method: "POST" });
            })}>Retry</button>}
            {["queued", "running"].includes(item.state) && <button disabled={busy} onClick={() => void action(async () => {
              await mediaRequest(`/${project}/sources/${item.id}/cancel`, { method: "POST" });
            })}>Cancel processing</button>}
          </td>
        </tr>)}</tbody>
      </table>
      {sources.length === 0 && <p>No sources on this page.</p>}
      <button disabled={page === 0 || busy} onClick={() => setPage(page - 1)}>Previous</button>{" "}
      <button disabled={sources.length < 50 || busy} onClick={() => setPage(page + 1)}>Next</button>
    </>}
  </main>;
}
