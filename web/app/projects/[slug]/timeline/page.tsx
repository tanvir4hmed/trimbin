"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import EditableExports from "./EditableExports";
import { currentToken } from "@/lib/auth";
import { mediaRequest } from "@/lib/media";
import { projectIdFromSlug } from "@/lib/slug";

type Rate = { numerator: number; denominator: number };
type Sequence = { name: string; fps: Rate; width: number; height: number; color: "rec709-sdr"; audio_rate: 48000; conform: "preserve-speed-drop-duplicate-v1" };
type Clip = { id: string; source_id: string; selection_id: string; in_frame: number; out_frame: number; muted: boolean; gain_db: number; note: string };
type Entry = Clip & { start_frame: number; duration_frames: number; source: { filename: string; fps: Rate; frame_count: number; audio: unknown }; quantization_seconds: Rate };
type Snapshot = { revision: number; body: { sequence: Sequence; clips: Entry[]; duration_frames: number } | null; source_errors: Record<string, string | null> };
const initial: Sequence = { name: "Film", fps: { numerator: 24, denominator: 1 }, width: 1920, height: 1080, color: "rec709-sdr", audio_rate: 48000, conform: "preserve-speed-drop-duplicate-v1" };
function plain(c: Clip): Clip { return { id: c.id, source_id: c.source_id, selection_id: c.selection_id, in_frame: c.in_frame, out_frame: c.out_frame, muted: c.muted, gain_db: c.gain_db, note: c.note }; }
async function request<T>(path: string, body?: unknown): Promise<T> {
  const token = currentToken();
  const response = await fetch(`/api/timelines${path}`, { method: body === undefined ? "GET" : "POST", headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(response.status === 409 ? "Timeline changed. Your draft is retained; reload explicitly before reconciling." : typeof error.detail === "string" ? error.detail.replaceAll("_", " ") : "Timeline request failed"); }
  return response.json();
}

export default function TimelinePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params), project = projectIdFromSlug(slug);
  const [key, setKey] = useState("film"), [keyInput, setKeyInput] = useState("film");
  const [saved, setSaved] = useState<Snapshot | null>(null);
  const [draft, setDraft] = useState<{ sequence: Sequence; clips: Clip[] }>({ sequence: initial, clips: [] });
  const [undo, setUndo] = useState<typeof draft[]>([]), [redo, setRedo] = useState<typeof draft[]>([]);
  const [dirty, setDirty] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [versions, setVersions] = useState<{ revision: number; actor: string }[]>([]);
  const pending = useRef<unknown>(null);
  const loadSerial = useRef(0);
  const [frame, setFrame] = useState(0), [playing, setPlaying] = useState(false), [url, setUrl] = useState("");
  const player = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);
  const endpoint = `/${project}/${key}`;
  const entry = saved?.body?.clips.find(c => c.start_frame <= frame && frame < c.start_frame + c.duration_frames);
  const fps = saved?.body?.sequence.fps ?? initial.fps;
  const target = entry ? entry.in_frame + Number(BigInt(frame - entry.start_frame) * BigInt(entry.source.fps.numerator) * BigInt(fps.denominator) / (BigInt(entry.source.fps.denominator) * BigInt(fps.numerator))) : 0;
  const sourceSeconds = entry ? Math.min(entry.out_frame - 1, target) * entry.source.fps.denominator / entry.source.fps.numerator : 0;

  async function load(path = endpoint) {
    const serial = ++loadSerial.current;
    const [value, history] = await Promise.all([request<Snapshot>(path), request<{ versions: typeof versions }>(`${path}/history`)]);
    if (serial !== loadSerial.current) return;
    setSaved(value); setDraft({ sequence: value.body?.sequence ?? initial, clips: value.body?.clips.map(plain) ?? [] });
    setDirty(false); setUndo([]); setRedo([]); pending.current = null; setPlaying(false); setFrame(0);
    setVersions(history.versions);
  }
  useEffect(() => { void load().catch(e => setError(e.message)); }, [project, key]); // Explicit load, never overwrite drafts by polling.
  useEffect(() => {
    function leaving(event: BeforeUnloadEvent) { if (dirty) { event.preventDefault(); event.returnValue = ""; } }
    window.addEventListener("beforeunload", leaving); return () => window.removeEventListener("beforeunload", leaving);
  }, [dirty]);
  async function action(work: () => Promise<void>) { setBusy(true); setError(""); try { await work(); } catch (e) { setError(e instanceof Error ? e.message : "Operation unavailable"); } finally { setBusy(false); } }
  function edit(next: typeof draft) { setUndo(v => [...v.slice(-99), draft]); setRedo([]); setDraft(next); setDirty(true); pending.current = null; setPlaying(false); }
  function change(index: number, values: Partial<Clip>) { edit({ ...draft, clips: draft.clips.map((c, i) => i === index ? { ...c, ...values } : c) }); }
  async function addSelected() {
    let result = await request<{ clips: Clip[]; requires_timing: string[] }>(`${endpoint}/selections`);
    for (const source of result.requires_timing) await request(`/${project}/sources/${source}/timing`, {});
    if (result.requires_timing.length) result = await request(`${endpoint}/selections`);
    if (result.requires_timing.length) throw new Error("Source timing remains unavailable; no partial selection was appended.");
    if (!result.clips.length) throw new Error("Select ranges in Evidence workspace first.");
    edit({ ...draft, clips: [...draft.clips, ...result.clips] });
  }
  async function save() {
    if (!saved) return;
    pending.current ??= { ...draft, expected_revision: saved.revision, command_id: crypto.randomUUID() };
    await request(`${endpoint}/revisions`, pending.current);
    await load();
  }
  useEffect(() => {
    let cancelled = false; setUrl(""); setReady(false);
    if (entry && !saved?.source_errors[entry.source_id]) void mediaRequest<{ url: string }>(`/${project}/sources/${entry.source_id}/access/proxy`, { method: "POST" }).then(ticket => { if (!cancelled) setUrl(`/api${ticket.url}`); }).catch(e => { if (!cancelled) { setError(e.message); setPlaying(false); } });
    return () => { cancelled = true; };
  }, [entry?.source_id, project, saved?.revision]);
  function sync() {
    const video = player.current;
    if (!video || video.readyState < 1 || !entry) return;
    video.muted = entry.muted; video.volume = Math.pow(10, entry.gain_db / 20);
    if (!playing || Math.abs(video.currentTime - sourceSeconds) > 0.12) video.currentTime = sourceSeconds;
    if (playing && target < entry.out_frame - 1) void video.play().catch(() => { setPlaying(false); setError("Playback could not start. Use the frame slider or retry."); }); else video.pause();
  }
  useEffect(sync, [frame, playing, url]);
  useEffect(() => {
    if (!playing || !ready || !saved?.body) return;
    const start = performance.now(), first = frame, count = saved.body.duration_frames;
    let id: number;
    function tick(now: number) { const next = first + Math.floor((now - start) * fps.numerator / fps.denominator / 1000); if (next >= count) { setFrame(Math.max(0, count - 1)); setPlaying(false); return; } setFrame(next); id = requestAnimationFrame(tick); }
    id = requestAnimationFrame(tick); return () => cancelAnimationFrame(id);
  }, [playing, ready, saved?.revision, entry?.source_id]);

  return <main className="shell" style={{ maxWidth: 1150, padding: "2rem" }}>
    <Link href={`/projects/${slug}/evidence`}>Evidence workspace</Link><h1>Scene and film timeline</h1>
    <p>Arrange selected ranges, then save an approved revision. Preview uses that saved revision; unsaved edits do not alter it.</p>
    {error && <p role="alert">{error}</p>}
    <label>Timeline key <input value={keyInput} onChange={e => setKeyInput(e.target.value)} /></label>
    <button disabled={busy || !/^(film|scene-[A-Za-z0-9_-]{1,64})$/.test(keyInput)} onClick={() => { if (!dirty || confirm("Discard unsaved timeline edits?")) { if (key === keyInput) void action(() => load()); else { loadSerial.current++; setSaved(null); setPlaying(false); setKey(keyInput); } } }}>Open film or scene</button>
    <p>Use “film” or a scene key such as “scene-01”. Each has independent revisions. Append only the ranges intended for this sequence.</p>
    <button disabled={busy || !saved} onClick={() => void action(addSelected)}>Append selected ranges (verify timing)</button>
    <button disabled={busy || !dirty || !saved} onClick={() => void action(save)}>Save approved revision</button>
    <button disabled={busy} onClick={() => { if (!dirty || confirm("Discard unsaved timeline edits and reload?")) void action(() => load()); }}>Reload saved</button>
    <button disabled={busy || !undo.length} onClick={() => { setRedo(v => [...v, draft]); setDraft(undo[undo.length - 1]); setUndo(v => v.slice(0, -1)); setDirty(true); pending.current = null; }}>Undo</button>
    <button disabled={busy || !redo.length} onClick={() => { setUndo(v => [...v, draft]); setDraft(redo[redo.length - 1]); setRedo(v => v.slice(0, -1)); setDirty(true); pending.current = null; }}>Redo</button>
    <p>Saved revision {saved?.revision ?? "loading"}{dirty ? " · Unsaved draft" : ""}</p>
    <fieldset disabled={busy || !saved}><legend>Sequence settings</legend>
      <label>Name <input value={draft.sequence.name} onChange={e => edit({ ...draft, sequence: { ...draft.sequence, name: e.target.value } })} /></label>
      <label>FPS <select value={`${draft.sequence.fps.numerator}/${draft.sequence.fps.denominator}`} onChange={e => { const [numerator, denominator] = e.target.value.split("/").map(Number); edit({ ...draft, sequence: { ...draft.sequence, fps: { numerator, denominator } } }); }}>{["24/1", "24000/1001", "25/1", "30/1", "30000/1001", "50/1", "60/1", "60000/1001"].map(r => <option key={r}>{r}</option>)}</select></label>
      {(["width", "height"] as const).map(k => <label key={k}>{k} <input type="number" value={draft.sequence[k]} onChange={e => edit({ ...draft, sequence: { ...draft.sequence, [k]: Number(e.target.value) } })} /></label>)}
      <p>SDR Rec.709 · 48 kHz audio · preserve speed with frame drop/duplication. Export validation is pending.</p>
    </fieldset>
    {draft.clips.map((clip, index) => <fieldset key={clip.id} disabled={busy}><legend>{index + 1}. {saved?.body?.clips.find(c => c.source_id === clip.source_id)?.source.filename ?? clip.source_id}</legend>
      <label>In frame <input type="number" min={0} value={clip.in_frame} onChange={e => change(index, { in_frame: Number(e.target.value) })} /></label>
      <label>Out frame (exclusive) <input type="number" min={1} value={clip.out_frame} onChange={e => change(index, { out_frame: Number(e.target.value) })} /></label>
      <label>Note <input value={clip.note} onChange={e => change(index, { note: e.target.value })} /></label>
      <label><input type="checkbox" checked={clip.muted} onChange={e => change(index, { muted: e.target.checked })} /> Mute linked audio</label>
      <label>Gain dB <input type="number" min={-60} max={0} value={clip.gain_db} onChange={e => change(index, { gain_db: Number(e.target.value) })} /></label>
      {[-1, 1].map(step => <button key={step} disabled={index + step < 0 || index + step >= draft.clips.length} onClick={() => { const clips = [...draft.clips]; [clips[index], clips[index + step]] = [clips[index + step], clips[index]]; edit({ ...draft, clips }); }}>{step < 0 ? "Up" : "Down"}</button>)}
      <button onClick={() => { const clips = [...draft.clips]; clips.splice(index + 1, 0, { ...clip, id: crypto.randomUUID() }); edit({ ...draft, clips }); }}>Repeat</button>
      <button onClick={() => edit({ ...draft, clips: draft.clips.filter(c => c.id !== clip.id) })}>Remove</button>
    </fieldset>)}
    <h2>Saved timeline preview</h2>
    <p>Browser proxy playback is approximate, not a frame-accurate export verification. Source frame mapping and sequence durations are saved exactly.</p>
    {Object.entries(saved?.source_errors ?? {}).filter(([, problem]) => problem).map(([id, problem]) => <p role="alert" key={id}>{id}: {problem}</p>)}
    {url && <video key={url} ref={player} src={url} onLoadedMetadata={() => { sync(); setReady(true); }} onError={() => { setPlaying(false); setError("Preview unavailable; source or access ticket may need reloading."); }} style={{ width: "100%", maxHeight: 450 }} />}
    <button disabled={!saved?.body?.duration_frames || Object.values(saved?.source_errors ?? {}).some(Boolean)} onClick={() => setPlaying(p => !p)}>{playing ? "Pause" : "Play saved sequence"}</button>
    <input aria-label="Sequence frame" type="range" min={0} max={Math.max(0, (saved?.body?.duration_frames ?? 1) - 1)} value={frame} onChange={e => { setPlaying(false); setFrame(Number(e.target.value)); }} />
    <p>Sequence frame {frame} / {saved?.body?.duration_frames ?? 0}{entry ? ` · Source frame ${Math.min(entry.out_frame - 1, target)} · ${entry.source.filename}` : ""}</p>
    {entry && <p>Quantization delta: {entry.quantization_seconds.numerator}/{entry.quantization_seconds.denominator} seconds. Linked source audio metadata is pinned with this occurrence.</p>}
    <EditableExports key={endpoint} project={project} sequence={key} revision={saved?.revision ?? 0} dirty={dirty} />
    <h2>Saved revisions</h2>
    {versions.map(v => <button key={v.revision} disabled={busy} onClick={() => { if (!dirty || confirm("Replace the unsaved draft with this revision?")) void action(async () => { const old = await request<Snapshot>(`${endpoint}?revision=${v.revision}`); if (old.body) edit({ sequence: old.body.sequence, clips: old.body.clips.map(plain) }); }); }}>Use revision {v.revision} as draft</button>)}
    {versions.length > 0 && <button disabled={busy} onClick={() => void action(async () => { const more = await request<{ versions: typeof versions }>(`${endpoint}/history?before=${versions[versions.length - 1].revision}`); setVersions(v => [...v, ...more.versions]); })}>Older revisions</button>}
    <p>Using history creates a draft; saving creates a new revision without rewriting history. AI drafts remain disabled; editable export uses the saved revision above.</p>
  </main>;
}
