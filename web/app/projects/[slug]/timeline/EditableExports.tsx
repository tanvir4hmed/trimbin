"use client";
import { useEffect, useRef, useState } from "react";
import { currentToken } from "@/lib/auth";

type Job = { id: string; state: string; error_code: string | null; payload: { revision: number; format: string }; result: { sha256: string; bytes: number } | null };
async function call(path: string, body?: unknown) {
  const token = currentToken();
  const response = await fetch(`/api/editable-exports${path}`, { method: body === undefined ? "GET" : "POST", headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(typeof error.detail === "string" ? error.detail.replaceAll("_", " ") : "Export unavailable"); }
  return response;
}
export default function EditableExports({ project, sequence, revision, dirty }: { project: number; sequence: string; revision: number; dirty: boolean }) {
  const [jobs, setJobs] = useState<Job[]>([]), [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef<{ command_id: string; revision: number; format: string; key: string } | null>(null);
  const endpoint = `/${project}/sequences/${sequence}`;
  async function refresh() { const result = await (await call(endpoint)).json(); setJobs(result.jobs); }
  useEffect(() => {
    let stopped = false;
    setJobs([]); setError(""); pending.current = null;
    async function poll() { try { const data = await (await call(endpoint)).json(); if (!stopped) setJobs(data.jobs); } catch (e) { if (!stopped) setError(e instanceof Error ? e.message : "Export unavailable"); } }
    void poll(); const timer = setInterval(() => void poll(), 5000);
    return () => { stopped = true; clearInterval(timer); };
  }, [endpoint]);
  async function action(work: () => Promise<void>) { setBusy(true); setError(""); try { await work(); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : "Export unavailable"); } finally { setBusy(false); } }
  async function create(format: string) {
    if (!pending.current || pending.current.format !== format || pending.current.revision !== revision || pending.current.key !== endpoint) pending.current = { command_id: crypto.randomUUID(), revision, format, key: endpoint };
    const { key: _key, ...body } = pending.current;
    await call(endpoint, body); pending.current = null;
  }
  async function download(job: Job) {
    const blob = await (await call(`/${project}/jobs/${job.id}/download`)).blob();
    const url = URL.createObjectURL(blob), anchor = document.createElement("a");
    anchor.href = url; anchor.download = `${sequence}-r${job.payload.revision}-${job.payload.format}.zip`; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <section><h2>Editable timeline export</h2>
    <p>Export saved revision {revision}. Originals are referenced, never copied or re-encoded. This is an editable handoff, not a rendered movie.</p>
    {dirty && <p>Save or discard draft changes before exporting.</p>}
    <button disabled={busy || dirty || revision < 1} onClick={() => void action(() => create("native"))}>Native timeline bundle</button>
    <button disabled={busy || dirty || revision < 1} onClick={() => void action(() => create("fcp7"))}>FCP7 XML bundle</button>
    <p>Premiere import/relink verification is pending. XML currently requires equal source/sequence rates and dimensions, mono/stereo audio with zero offset. Other cases remain available in the native manifest.</p>
    {error && <p role="alert">{error}</p>}
    {jobs.map(job => <p key={job.id}>Revision {job.payload.revision} · {job.payload.format} · {job.state}{job.error_code ? ` · ${job.error_code.replaceAll("_", " ")}` : ""}
      {job.state === "succeeded" && <button disabled={busy} onClick={() => void action(() => download(job))}>Download ZIP</button>}
      {["queued", "running"].includes(job.state) && <button disabled={busy} onClick={() => void action(async () => { await call(`/${project}/jobs/${job.id}/cancel`, {}); })}>Cancel</button>}
      {job.result && <small> · {job.result.bytes} bytes · SHA-256 {job.result.sha256}</small>}
    </p>)}
    <p>Extract the bundle, map media root aliases to your local original folders, and run the included relink.py for XML. It checks original hashes before creating a relinked XML file.</p>
  </section>;
}
