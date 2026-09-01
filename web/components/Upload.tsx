"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { JobStatus, PlannedScene } from "@/lib/api";
import { ApiError, api } from "@/lib/api";
import { type Progress, type Ticket, uploadAll } from "@/lib/upload";

type Stage = "add" | "read" | "verify" | "ingest";
type Resolution = { action: "move" | "keep" | "unassign" | "create"; scene?: number; shot?: number };
type SavedGrant = { job_id: string; tickets: Ticket[]; filenames: string[] };

const STAGES: { key: Stage; label: string }[] = [
  { key: "add", label: "Add files" },
  { key: "read", label: "Read slates" },
  { key: "verify", label: "Verify matches" },
  { key: "ingest", label: "Ingest" },
];

function bytes(value: number) {
  return value > 1024 ** 3 ? `${(value / 1024 ** 3).toFixed(2)} GB` : `${(value / 1024 ** 2).toFixed(0)} MB`;
}

export default function Upload({ projectId, plan, canResolve = true, onFinished }: { projectId: number; plan: PlannedScene[]; canResolve?: boolean; onFinished?: () => void }) {
  const fileInput = useRef<HTMLInputElement>(null);
  const storageKey = `trimbin.ingest.${projectId}`;
  const [stage, setStage] = useState<Stage>("add");
  const [mode, setMode] = useState<"slate" | "manual">("slate");
  const [files, setFiles] = useState<File[]>([]);
  const [rows, setRows] = useState<Progress[]>([]);
  const [jobId, setJobId] = useState("");
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [decisions, setDecisions] = useState<Record<string, Resolution>>({});
  const [targetScene, setTargetScene] = useState(0);
  const [targetShot, setTargetShot] = useState(0);
  const [createNew, setCreateNew] = useState(false);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);

  const shots = plan.find((item) => item.scene === targetScene)?.shots ?? [];
  const items = status?.items ?? [];
  const selected = items.find((item) => item.clip_id === selectedId) ?? items[0];
  const uploaded = rows.reduce((total, row) => total + row.sent, 0);
  const total = rows.reduce((sum, row) => sum + row.total, 0);
  const activeIndex = STAGES.findIndex((item) => item.key === stage);

  useEffect(() => {
    const saved = window.localStorage.getItem(storageKey);
    if (!saved) return;
    try {
      const grant = JSON.parse(saved) as SavedGrant;
      setJobId(grant.job_id);
      void api.jobStatus(grant.job_id).then((found) => {
        setStatus(found);
        if (found.state === "committed") setStage("ingest");
        else if (found.done) setStage("verify");
        else if (found.state === "processing") setStage("read");
      }).catch(() => window.localStorage.removeItem(storageKey));
    } catch { window.localStorage.removeItem(storageKey); }
  }, [storageKey]);

  useEffect(() => {
    if (!items.length) return;
    setSelectedId((current) => current || items[0].clip_id);
    setDecisions((current) => {
      const next = { ...current };
      for (const item of items) {
        const draft = item.draft as Resolution | null | undefined;
        if (!next[item.clip_id] && draft?.action) next[item.clip_id] = draft;
        else if (!next[item.clip_id] && item.status === "Matched") next[item.clip_id] = { action: "keep", scene: item.scene, shot: item.shot };
      }
      return next;
    });
  }, [items]);

  useEffect(() => {
    if (!selected) return;
    const draft = decisions[selected.clip_id];
    setTargetScene(draft?.scene ?? selected.scene);
    setTargetShot(draft?.shot ?? selected.shot);
    setCreateNew(draft?.action === "create");
  }, [selected?.clip_id]);

  useEffect(() => {
    if (stage !== "read" || !jobId) return;
    let alive = true;
    const poll = async () => {
      try {
        const found = await api.jobStatus(jobId);
        if (!alive) return;
        setStatus(found);
        if (found.done) { setStage(found.state === "committed" ? "ingest" : "verify"); return; }
      } catch { /* one poll can fail while the archive wakes */ }
      if (alive) window.setTimeout(() => void poll(), 2500);
    };
    void poll();
    return () => { alive = false; };
  }, [jobId, stage]);

  const start = useCallback(async () => {
    if (!files.length) return;
    setError("");
    setStage("read");
    try {
      const saved = window.localStorage.getItem(storageKey);
      const prior = saved ? JSON.parse(saved) as SavedGrant : null;
      const sameFiles = prior && prior.filenames.length === files.length && prior.filenames.every((name) => files.some((file) => file.name === name));
      const grant = sameFiles ? prior : await api.grantUpload(projectId, files.map((file) => file.name), mode === "manual" ? { scene: targetScene, shot: targetShot } : undefined);
      if (!grant) throw new Error("Upload batch could not be restored.");
      window.localStorage.setItem(storageKey, JSON.stringify({ job_id: grant.job_id, tickets: grant.tickets, filenames: files.map((file) => file.name) }));
      setJobId(grant.job_id);
      const { arrived, names } = await uploadAll(grant.tickets, files, setRows);
      const result = await api.completeUpload(grant.job_id, arrived, names);
      if (Number(result.missing)) setError(`${result.missing} file(s) did not reach storage.`);
    } catch (cause) {
      setStage("add");
      setError(cause instanceof ApiError || cause instanceof Error ? cause.message : "Upload could not start.");
    }
  }, [files, mode, projectId, storageKey, targetScene, targetShot]);

  const choose = async (clipId: string, resolution: Resolution) => {
    setDecisions((current) => ({ ...current, [clipId]: resolution }));
    if (!jobId) return;
    try { await api.saveIngestDraft(jobId, { clip_id: clipId, ...resolution }); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save that verification choice."); }
  };
  const unresolved = items.filter((item) => !item.verified && !decisions[item.clip_id]);

  const commit = async () => {
    if (!jobId || unresolved.length) return;
    try {
      const pending = items.filter((item) => !item.verified).map((item) => ({ clip_id: item.clip_id, ...decisions[item.clip_id] }));
      await api.commitIngest(jobId, pending);
      const found = await api.jobStatus(jobId);
      setStatus(found);
      setStage("ingest");
      window.localStorage.removeItem(storageKey);
      onFinished?.();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not commit ingest."); }
  };

  const reset = () => {
    setStage("add"); setFiles([]); setRows([]); setJobId(""); setStatus(null); setDecisions({}); setSelectedId(""); setError("");
    window.localStorage.removeItem(storageKey);
    if (fileInput.current) fileInput.current.value = "";
  };

  return <section className="ingest-wizard">
    <header className="ingest-head"><div><p className="eyebrow">FOOTAGE INGEST</p><h1>Add a shoot day</h1><p>AI proposes. You verify. Only then does footage enter the project.</p></div><span className="safety-lock">◈ Nothing moves or deletes without confirmation</span></header>
    <ol className="ingest-stepper">{STAGES.map((item, index) => <li key={item.key} className={index === activeIndex ? "active" : index < activeIndex ? "done" : ""}><span>{index < activeIndex ? "✓" : index + 1}</span><b>{item.label}</b></li>)}</ol>

    {stage === "add" && <div className="ingest-add">
      <div className="source-tiles"><button className="source-tile on"><span>▣</span><b>Computer</b><small>Camera cards or a shoot folder</small></button></div>
      <div className="ingest-mode"><button className={mode === "slate" ? "on" : ""} onClick={() => setMode("slate")}><b>AI reads the slate</b><small>Scene, shot, take and camera from the board</small></button><button className={mode === "manual" ? "on" : ""} onClick={() => setMode("manual")}><b>I know scene / shot / take</b><small>Declare a destination; mismatches are still flagged</small></button></div>
      {mode === "manual" && <div className="manual-target"><label>Scene<select value={targetScene} onChange={(event) => { setTargetScene(Number(event.target.value)); setTargetShot(0); }}><option value={0}>Choose scene</option>{plan.map((item) => <option key={item.scene} value={item.scene}>{item.scene} · {item.heading}</option>)}</select></label><label>Shot<select value={targetShot} onChange={(event) => setTargetShot(Number(event.target.value))}><option value={0}>Slate decides shot</option>{shots.map((item) => <option key={item.shot} value={item.shot}>{item.slug || `Shot ${item.shot}`}</option>)}</select></label></div>}
      <div className={dragging ? "ingest-drop over" : "ingest-drop"} role="button" tabIndex={0} onClick={() => fileInput.current?.click()} onKeyDown={(event) => { if (event.key === "Enter") fileInput.current?.click(); }} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); setFiles(Array.from(event.dataTransfer.files)); }}><span>＋</span><h2>Drop camera files or a shoot folder</h2><p>MOV, MP4, MXF, BRAW and R3D · files upload directly to storage</p><input ref={fileInput} hidden type="file" multiple accept=".mov,.mp4,.mxf,.m4v,.avi,.mkv,.braw,.r3d" onChange={(event) => setFiles(Array.from(event.target.files ?? []))} /></div>
      {files.length > 0 && <div className="ingest-file-summary"><span><b>{files.length}</b> clips · {bytes(files.reduce((sum, file) => sum + file.size, 0))}</span><button className="primary" disabled={mode === "manual" && !targetScene} onClick={() => void start()}>Upload &amp; read slates</button></div>}
    </div>}

    {stage === "read" && <div className="ingest-reading"><div className="reading-orbit">✦</div><h2>{rows.length && uploaded < total ? "Uploading camera originals" : "Reading slates and building proxies"}</h2><p>{status ? `${status.completed + status.failed} of ${status.total} processed` : rows.length ? `${bytes(uploaded)} of ${bytes(total)}` : "Restoring this batch…"}</p><div className="ingest-progress"><i style={{ width: `${status?.total ? ((status.completed + status.failed) / status.total) * 100 : total ? uploaded / total * 100 : 2}%` }} /></div><p className="hint">This batch is persisted. After a refresh, choose the same local files to continue any interrupted upload.</p></div>}

    {(stage === "verify" || stage === "ingest") && <div className="ingest-verify">
      <section className="ingest-table-panel"><header><div><h2>{items.length} clips</h2><p>{items.filter((item) => item.status === "Matched").length} matched · {items.filter((item) => item.status === "Needs review").length} need review · {items.filter((item) => item.status === "Duplicate").length} duplicate</p></div><div className="status-filter">Verify every row before commit</div></header><div className="ingest-table-wrap"><table className="ingest-table"><thead><tr><th>Clip</th><th>Duration</th><th>Camera</th><th>Detected assignment</th><th>Confidence</th><th>Status</th></tr></thead><tbody>{items.map((item) => <tr key={item.clip_id} className={selected?.clip_id === item.clip_id ? "selected" : ""} onClick={() => setSelectedId(item.clip_id)}><td><div className="clip-cell">{item.slate_uri ? <img src={item.slate_uri} alt="Slate frame" /> : <span className="clip-thumb">▶</span>}<span><b>{item.filename || item.clip_id.slice(0, 8)}</b><small>Take {item.take_no || "—"}</small></span></div></td><td>{item.duration_s.toFixed(1)}s</td><td>{item.camera || "—"}</td><td>{item.scene ? `Scene ${item.scene} / Shot ${item.shot || "—"}` : "Unassigned"}</td><td><span className="confidence-meter"><i style={{ width: `${item.confidence * 100}%` }} /></span>{Math.round(item.confidence * 100)}%</td><td><span className={`ingest-status ${item.status.toLowerCase().replace(" ", "-")}`}>{item.status}</span></td></tr>)}</tbody></table></div></section>
      <aside className="ingest-inspector">{selected ? <><p className="eyebrow">SLATE EVIDENCE</p>{selected.slate_uri ? <img className="inspector-slate" src={selected.slate_uri} alt="Actual slate frame" /> : <div className="inspector-slate missing">No readable board frame</div>}<h2>{selected.filename}</h2><div className="slate-read"><span>Scene <b>{selected.scene || "—"}</b></span><span>Shot <b>{selected.shot || "—"}</b></span><span>Take <b>{selected.take_no || "—"}</b></span><span>Camera <b>{selected.camera || "—"}</b></span></div><p className="raw-read">{selected.slate_raw || "No slate text was confidently read."}</p>{selected.mismatch && <div className="mismatch-callout"><b>Assignment mismatch</b><p>{selected.mismatch}</p></div>}{selected.duplicate_of && <div className="mismatch-callout"><b>Duplicate evidence</b><p>Same bytes as clip {selected.duplicate_of.slice(0, 8)}. Kept; never auto-deleted.</p></div>}<div className="evidence-chips"><span>Slate frame</span>{selected.slate_raw && <span>Slate read</span>}<span>Folder target</span></div>
        {stage === "verify" && canResolve && <><div className="resolve-target"><label>Scene<select value={targetScene || selected.scene} onChange={(event) => { setTargetScene(Number(event.target.value)); setTargetShot(0); }}><option value={0}>Unassigned</option>{plan.map((item) => <option key={item.scene} value={item.scene}>{item.scene} · {item.heading}</option>)}</select></label><label>Shot<select value={targetShot || selected.shot} onChange={(event) => setTargetShot(Number(event.target.value))}><option value={0}>Choose shot</option>{(plan.find((item) => item.scene === (targetScene || selected.scene))?.shots ?? []).map((item) => <option key={item.shot} value={item.shot}>{item.slug || item.shot}</option>)}</select></label></div><label className="create-shot-toggle"><input type="checkbox" checked={createNew} onChange={(event) => setCreateNew(event.target.checked)} /> Create this shot if it is not in the plan</label><div className="resolve-buttons"><button className="primary" onClick={() => choose(selected.clip_id, createNew ? { action: "create", scene: targetScene || selected.scene, shot: targetShot || selected.shot } : { action: "move", scene: targetScene || selected.scene, shot: targetShot || selected.shot })}>Move / choose manually</button><button className="ghost" onClick={() => choose(selected.clip_id, { action: "keep", scene: selected.scene, shot: selected.shot })}>Keep proposed match</button><button className="ghost" onClick={() => choose(selected.clip_id, { action: "unassign" })}>Leave unassigned</button></div>{decisions[selected.clip_id] && <p className="decision-ready">✓ Decision ready: {decisions[selected.clip_id].action}</p>}</>}
      </> : <p>Choose a clip.</p>}</aside>
    </div>}

    {stage === "verify" && <footer className="ingest-footer"><div><b>Nothing moves or deletes without confirmation.</b><span>{unresolved.length ? `${unresolved.length} clip${unresolved.length === 1 ? "" : "s"} still need a decision.` : "All assignments are ready."}</span></div><button className="primary" disabled={Boolean(unresolved.length) || !items.length} onClick={() => void commit()}>Commit {items.filter((item) => !item.verified).length} clips to project</button></footer>}
    {stage === "ingest" && <div className="ingest-complete"><span>✓</span><div><h2>Ingest committed</h2><p>{status?.items.filter((item) => item.verified).length ?? 0} clips are organized. Full-take analysis is queued.</p></div><button className="ghost" onClick={reset}>Add another batch</button></div>}
    {error && <p className="error ingest-error">{error}</p>}
  </section>;
}
