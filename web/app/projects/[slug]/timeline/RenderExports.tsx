"use client";
import { useEffect, useRef, useState } from "react";
import { currentToken } from "@/lib/auth";

type Job = { id: string; state: string; error_code: string | null; payload: { revision: number; format: string }; result: { sha256?: string; bytes?: number; stage?: string; completed?: number; total?: number } | null };
async function call(path: string, body?: unknown) {
  const token = currentToken();
  const response = await fetch(`/api/renders${path}`, { method: body === undefined ? "GET" : "POST", headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(typeof error.detail === "string" ? error.detail.replaceAll("_", " ") : "Export unavailable"); }
  return response;
}
export default function RenderExports({ project, sequence, revision, dirty }: { project: number; sequence: string; revision: number; dirty: boolean }) {
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
    const data = await (await call(`/${project}/jobs/${job.id}/access`, {})).json();
    const anchor = document.createElement("a"); anchor.href = `/api${data.url}`; anchor.rel = "noreferrer"; anchor.click();
  }
  return <section><h2>Original-footage video export</h2>
    <p>Render saved revision {revision} from verified originals. H.264 CRF 18 / slow, AAC 320 kbps stereo. This is a lossy delivery preset; source files remain unchanged. Fidelity acceptance is pending.</p>
    <p>Requires matching source/sequence resolution and FPS, progressive square-pixel Rec.709 limited-range 8-bit 4:2:0 footage. Unsupported formats fail explicitly. Raw scratch capacity is checked before encoding.</p>
    {dirty && <p>Save or discard draft changes before rendering.</p>}
    <button disabled={busy || dirty || revision < 1} onClick={() => void action(() => create("h264-sdr-v1"))}>Render MP4</button>
    {error && <p role="alert">{error}</p>}
    {jobs.map(job => <p key={job.id}>Revision {job.payload.revision} · {job.state}{job.error_code ? ` · ${job.error_code.replaceAll("_", " ")}` : ""}
      {job.result?.stage && <span> · {job.result.stage.replaceAll("_", " ")} · {job.result.completed}/{job.result.total} cuts</span>}
      {job.state === "succeeded" && <button disabled={busy} onClick={() => void action(() => download(job))}>Download MP4</button>}
      {["queued", "running"].includes(job.state) && <button disabled={busy} onClick={() => void action(async () => { await call(`/${project}/jobs/${job.id}/cancel`, {}); })}>Cancel</button>}
      {job.result?.sha256 && <small> · {job.result.bytes} bytes · SHA-256 {job.result.sha256}</small>}
    </p>)}
  </section>;
}
