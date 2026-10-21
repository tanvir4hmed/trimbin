"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { projectIdFromSlug } from "@/lib/slug";
import { mediaRequest, type MediaSource } from "@/lib/media";
import { evidenceRequest, type EvidenceItem, type Workspace } from "@/lib/evidence";

export default function EvidencePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const project = projectIdFromSlug(slug);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [sources, setSources] = useState<MediaSource[]>([]);
  const [source, setSource] = useState("");
  const [sourcePage, setSourcePage] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState({ text: "", kind: "moment", start: "0", end: "1" });
  const [editing, setEditing] = useState<string | null>(null);
  const [draftRevision, setDraftRevision] = useState<number | null>(null);
  const [brief, setBrief] = useState("");
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState("text");
  const [filterSource, setFilterSource] = useState(false);
  const [filterKind, setFilterKind] = useState("");
  const [results, setResults] = useState<EvidenceItem[] | null>(null);
  const [report, setReport] = useState("");
  const [playback, setPlayback] = useState("");
  const [sample, setSample] = useState(2);
  const [labels, setLabels] = useState({ scene: "", shot: "", take: "" });

  const refresh = useCallback(async () => {
    const data = await evidenceRequest<Workspace>(`/${project}`);
    setWorkspace(data);
  }, [project]);
  useEffect(() => { setResults(null); }, [workspace?.revision]);
  useEffect(() => {
    void refresh().catch(e => setError(e.message));
    const timer = setInterval(() => void refresh().catch(e => setError(e.message)), 5000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    void mediaRequest<MediaSource[]>(`/${project}/sources?offset=${sourcePage * 50}`)
      .then(setSources).catch(e => setError(e.message));
  }, [project, sourcePage]);

  async function action(work: () => Promise<void>) {
    setBusy(true); setError("");
    try { await work(); await refresh(); setResults(null); }
    catch (e) { setError(e instanceof Error ? e.message : "Operation unavailable"); }
    finally { setBusy(false); }
  }
  async function command(body: Record<string, unknown>, expected = workspace?.revision) {
    await evidenceRequest(`/${project}/commands`, {
      command_id: crypto.randomUUID(), expected_revision: expected, ...body,
    });
  }
  function updateDraft(values: Partial<typeof draft>) {
    if (draftRevision === null) setDraftRevision(workspace?.revision ?? 0);
    setDraft(previous => ({ ...previous, ...values }));
  }
  async function saveNote() {
    const start = Number(draft.start), end = Number(draft.end);
    if (!source || !draft.text.trim() || !Number.isFinite(start) || !Number.isFinite(end) || end <= start || start < 0)
      throw new Error("Choose a source, enter valid source seconds and describe the evidence.");
    await command({ operation: editing ? "correct" : "note", item_id: editing,
      note: { source_id: source, start_us: Math.round(start * 1e6), end_us: Math.round(end * 1e6), kind: draft.kind, text: draft.text },
      decision: "accepted" }, draftRevision ?? workspace?.revision);
    setEditing(null); setDraftRevision(null); setDraft({ text: "", kind: "moment", start: "0", end: "1" });
  }
  async function analyze(task: "visual" | "slate") {
    await evidenceRequest(`/${project}/analyze`, { command_id: crypto.randomUUID(),
      expected_revision: workspace?.revision, source_id: source, task, mode: workspace?.analysis_mode,
      window_seconds: 30, overlap_seconds: 2, sample_every_seconds: sample,
      allowed_labels: Object.fromEntries(Object.entries(labels).map(([key, value]) => [key, value ? [value] : []])),
    });
  }

  return <main className="shell" style={{ maxWidth: 1150, padding: "2rem" }}>
    <Link href={`/projects/${slug}/media`}>Media library</Link>
    <Link href={`/projects/${slug}/timeline`}>Scene / film timeline</Link>
    <h1>Evidence workspace</h1>
    <p>Review source evidence, preserve corrections and select ranges for your edit.</p>
    {error && <p role="alert">{error}</p>}
    {!workspace ? <p>Loading authorized workspace…</p> : <>
      <p>Revision {workspace.revision} · {workspace.analysis_mode === "fixture" ? "Development fixtures: no AI findings are generated." : "Configured inference: live quality is not yet verified."}</p>
      <button disabled={busy} onClick={() => void action(refresh)}>Refresh</button>
      <section style={{ marginBlock: "2rem" }}>
        <h2>Source and analysis</h2>
        <select aria-label="Source" value={source} disabled={busy || !!editing} onChange={e => setSource(e.target.value)}>
          <option value="">Choose indexed source</option>
          {source && !sources.some(s => s.id === source) && <option value={source}>{source}</option>}
          {sources.filter(s => s.state === "succeeded").map(s => <option key={s.id} value={s.id}>{s.filename}</option>)}
        </select>{" "}
        <button disabled={sourcePage === 0 || busy} onClick={() => setSourcePage(p => p - 1)}>Previous sources</button>
        <button disabled={sources.length < 50 || busy} onClick={() => setSourcePage(p => p + 1)}>Next sources</button>
        <p>Original-detail PNG frames are sampled in overlapping windows. Sampling does not prove every action was observed.</p>
        <label>Sample interval (seconds) <input type="number" min={1} max={30} value={sample} onChange={e => setSample(Number(e.target.value))} /></label>{" "}
        <button disabled={busy || !source} onClick={() => void action(() => analyze("visual"))}>Analyze observations</button>
        <p>Scene, shot and take values are editor placement labels and the allowed vocabulary for slate analysis.</p>
        {(["scene", "shot", "take"] as const).map(key => <label key={key}>{key} <input value={labels[key]} onChange={e => setLabels({ ...labels, [key]: e.target.value })} /></label>)}
        <button disabled={busy || !source} onClick={() => void action(async () => { await command({ operation: "place", source_id: source, ...labels }); })}>Save placement</button>
        <button disabled={busy || !source} onClick={() => void action(() => analyze("slate"))}>Read slate</button>
        {source && workspace.placements[source] && <p>Saved: {[workspace.placements[source].scene, workspace.placements[source].shot, workspace.placements[source].take].join(" / ")}</p>}
      </section>
      <section>
        <h2>{editing ? "Correct evidence" : "Add editor evidence"}</h2>
        <select aria-label="Evidence kind" value={draft.kind} onChange={e => updateDraft({ kind: e.target.value })}>
          {["moment", "attempt", "observation", "slate", "continuity", "speech"].map(k => <option key={k}>{k}</option>)}
        </select>
        <label>From seconds <input value={draft.start} onChange={e => updateDraft({ start: e.target.value })} /></label>
        <label>To seconds <input value={draft.end} onChange={e => updateDraft({ end: e.target.value })} /></label>
        <textarea aria-label="Evidence text" value={draft.text} onChange={e => updateDraft({ text: e.target.value })} style={{ display: "block", width: "100%" }} />
        <button disabled={busy || !source} onClick={() => void action(saveNote)}>Save evidence</button>
        {draftRevision !== null && draftRevision !== workspace.revision && <>
          <p>The workspace changed while this draft was open. Review the current evidence before applying it.</p>
          <button disabled={busy} onClick={() => setDraftRevision(workspace.revision)}>Apply draft to current revision</button>
        </>}
        {editing && <button onClick={() => { setEditing(null); setDraftRevision(null); }}>Cancel correction</button>}
      </section>
      {playback && <video key={playback} src={playback} controls style={{ width: "100%", maxHeight: 450 }} />}
      <section style={{ marginBlock: "2rem" }}>
        <h2>Find evidence</h2>
        <input aria-label="Search text" value={query} onChange={e => setQuery(e.target.value)} />
        <select aria-label="Search mode" value={searchMode} onChange={e => setSearchMode(e.target.value)}><option value="text">Text</option><option value="semantic">Semantic (live query)</option></select>
        <label><input type="checkbox" checked={filterSource} onChange={e => setFilterSource(e.target.checked)} /> Selected source only</label>
        <select aria-label="Search evidence kind" value={filterKind} onChange={e => setFilterKind(e.target.value)}><option value="">All kinds</option>{["moment", "attempt", "observation", "slate", "continuity", "speech"].map(k => <option key={k}>{k}</option>)}</select>
        <button disabled={busy || !query.trim() || (filterSource && !source)} onClick={() => { setBusy(true); setError(""); void evidenceRequest<{ items: EvidenceItem[] }>(`/${project}/search`, { query, mode: searchMode, source_id: filterSource ? source : null, kind: filterKind || null }).then(r => setResults(r.items)).catch(e => { setResults(null); setError(e.message); }).finally(() => setBusy(false)); }}>Search</button>
        <button onClick={() => setResults(null)}>Show workspace</button>
        {results?.length === 0 && <p>No matching current evidence.</p>}
      </section>
      {(results ?? workspace.items).map(item => <article key={item.id} style={{ borderTop: "1px solid #888", paddingBlock: "1rem" }}>
        <strong>{item.kind} · {(item.start_us / 1e6).toFixed(3)}–{(item.end_us / 1e6).toFixed(3)}s</strong>
        <p>{item.text}</p><small>{item.origin} · {item.decision}{item.corrected ? " · corrected" : ""}{!item.current ? " · retained from previous analysis" : ""}</small><br />
        <button disabled={busy} onClick={() => void action(async () => { const ticket = await mediaRequest<{ url: string }>(`/${project}/sources/${item.source_id}/access/proxy`, { method: "POST" }); setPlayback(`/api${ticket.url}#t=${item.start_us / 1e6},${item.end_us / 1e6}`); })}>Preview</button>
        <button disabled={busy} onClick={() => { setSource(item.source_id); setEditing(item.id); setDraftRevision(workspace.revision); setDraft({ kind: item.kind, text: item.text, start: String(item.start_us / 1e6), end: String(item.end_us / 1e6) }); }}>Correct</button>
        <button disabled={busy} onClick={() => void action(async () => { await command({ operation: "correct", item_id: item.id, decision: "accepted" }); })}>Accept</button>
        <button disabled={busy} onClick={() => void action(async () => { await command({ operation: "correct", item_id: item.id, decision: "retracted" }); })}>Retract</button>
        <button disabled={busy || item.decision === "retracted"} onClick={() => void action(async () => { await command({ operation: "select", item_id: item.id }); })}>Select range</button>
      </article>)}
      <h2>Selected range snapshots ({workspace.selections.length})</h2>
      <p>Selections preserve the evidence as it was selected. Later corrections do not silently change these saved ranges.</p>
      {workspace.selections.map((item, i) => <p key={item.selection_id}>{i + 1}. {item.text} <button disabled={busy} onClick={() => void action(async () => { await command({ operation: "unselect", item_id: item.selection_id }); })}>Remove</button></p>)}
      <textarea aria-label="Comparison brief" placeholder="What matters in this edit?" value={brief} onChange={e => setBrief(e.target.value)} />
      {(["comparison", "continuity"] as const).map(task => <button key={task} disabled={busy || !brief.trim() || !workspace.selections.length} onClick={() => void action(async () => { await evidenceRequest(`/${project}/compare`, { command_id: crypto.randomUUID(), expected_revision: workspace.revision, mode: workspace.analysis_mode, task, brief }); })}>{task === "comparison" ? "Compare selections" : "Review continuity"}</button>)}
      <h2>Analysis runs</h2>
      {workspace.runs.map(run => <p key={run.id}>{run.task} · {run.mode} · {run.state}{run.error_code && ` · ${run.error_code.replaceAll("_", " ")}`}
        <button onClick={() => void action(async () => { const data = await evidenceRequest<{ result: unknown }>(`/${project}/runs/${run.id}`); setReport(JSON.stringify(data.result, null, 2)); })}>View result</button>
        {["queued", "running"].includes(run.state) && <button disabled={busy} onClick={() => void action(async () => { await evidenceRequest(`/${project}/runs/${run.id}/cancel`, {}); })}>Cancel</button>}
      </p>)}
      {report && <details open><summary>Run provenance and proposed results</summary><pre style={{ whiteSpace: "pre-wrap", maxHeight: 500, overflow: "auto" }}>{report}</pre></details>}
    </>}
  </main>;
}
