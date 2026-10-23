"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { currentToken, signInWithPass } from "@/lib/auth";

type Project = { id: number; name: string; role: string };
type Summary = { sources: number; timelines: { document_id: string; revision: number }[]; jobs: { kind: string; state: string; count: number }[]; inference_mode: string };
async function read(path: string) {
  const response = await fetch(`/api/workflow${path}`, { headers: { Authorization: `Bearer ${currentToken() ?? ""}` }, cache: "no-store" });
  if (!response.ok) throw new Error(response.status === 401 ? "Sign in to see your projects." : "Project information is unavailable. Check access and service configuration.");
  return response.json();
}

export default function Studio() {
  const [projects, setProjects] = useState<Project[]>([]), [error, setError] = useState("");
  const [username, setUsername] = useState(""), [password, setPassword] = useState("");
  const [authRevision, setAuthRevision] = useState(0);
  const [signed, setSigned] = useState(false), [busy, setBusy] = useState(false), [page, setPage] = useState(0);
  const [selected, setSelected] = useState<number | null>(null), [summary, setSummary] = useState<Summary | null>(null);
  useEffect(() => {
    const refresh = () => { setSigned(Boolean(currentToken())); setAuthRevision(v => v + 1); setError(""); setProjects([]); setSelected(null); setSummary(null); };
    refresh(); window.addEventListener("trimbin:auth", refresh); window.addEventListener("storage", refresh);
    return () => { window.removeEventListener("trimbin:auth", refresh); window.removeEventListener("storage", refresh); };
  }, []);
  useEffect(() => {
    let active = true; setProjects([]); setSelected(null); setSummary(null);
    if (signed) read(`/projects?offset=${page * 50}`).then(data => { if (active) setProjects(data.projects); }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [signed, page, authRevision]);
  useEffect(() => {
    let active = true; setSummary(null);
    if (selected !== null) read(`/${selected}/summary`).then(data => { if (active) setSummary(data); }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [selected]);
  return <main className="shell" style={{ maxWidth: 1000, padding: "2rem" }}>
    <h1>Editorial workspace</h1>
    <p>Keep originals, review source-grounded evidence, approve a timeline, then export an editable handoff or movie.</p>
    {!signed && <form onSubmit={async e => { e.preventDefault(); setBusy(true); setError(""); try { await signInWithPass(username, password); setPassword(""); setSigned(true); } catch (e) { setError(e instanceof Error ? e.message : "Sign-in failed"); } finally { setBusy(false); } }}>
      <label>Account <input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required /></label>
      <label>Password <input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
      <button disabled={busy}>Sign in</button>
      <p>Use the account provided by your deployment operator. Project membership is required.</p>
    </form>}
    {error && <p role="alert">{error}</p>}
    {signed && <><h2>Your projects</h2>
      {projects.length === 0 && <p>No projects on this page. Ask the operator to grant your account project access.</p>}
      {projects.map(p => <section key={p.id} style={{ marginBlock: "1rem" }}><h3>{p.name}</h3><p>{p.role}</p>
        <Link href={`/projects/${p.id}/media`}>Open media</Link>{" · "}<Link href={`/projects/${p.id}/evidence`}>Review evidence</Link>{" · "}<Link href={`/projects/${p.id}/timeline`}>Timeline & exports</Link>{" "}
        <button onClick={() => setSelected(p.id)}>Show saved-work status</button>
        {selected === p.id && summary && <div><p>{summary.sources} registered originals · inference: {summary.inference_mode}</p>
          {summary.timelines.map(t => <p key={t.document_id}>{t.document_id}: saved revision {t.revision}</p>)}
          {summary.jobs.map(j => <p key={`${j.kind}-${j.state}`}>{j.kind.replaceAll("_", " ")}: {j.count} {j.state}</p>)}
          <p>Job completion does not establish AI accuracy or export fidelity. Quality acceptance remains pending.</p>
        </div>}
      </section>)}
      <button disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>{" "}<button disabled={projects.length < 50} onClick={() => setPage(page + 1)}>Next</button>
    </>}
    <p>Media is uploaded or staged on this deployment. Live model inputs are sent to the configured external inference service. Offline studio operation and terabyte throughput are future validation.</p>
  </main>;
}
