"use client";

import { use, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import Player, { type PlayerHandle } from "@/components/Player";
import type { Stringout, StringoutEntry } from "@/lib/api";
import { ApiError, api } from "@/lib/api";

function clock(value: number) {
  const minutes = Math.floor(value / 60);
  return `${String(minutes).padStart(2, "0")}:${String(Math.floor(value % 60)).padStart(2, "0")}`;
}

export default function SceneCoveragePage({ params }: { params: Promise<{ id: string; scene: string }> }) {
  const { id, scene } = use(params);
  const projectId = Number(id);
  const sceneId = Number(scene);
  const player = useRef<PlayerHandle>(null);
  const [data, setData] = useState<Stringout | null>(null);
  const [error, setError] = useState("");
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [tab, setTab] = useState<"review" | "notes" | "activity">("review");

  useEffect(() => {
    void api.stringout(projectId, sceneId).then(setData).catch((cause) => setError(cause instanceof ApiError && cause.waking ? "The archive is waking up." : cause instanceof Error ? cause.message : "Could not load this scene."));
  }, [projectId, sceneId]);

  const entries = useMemo(() => data?.timeline.flatMap((item) => item.entries?.length ? item.entries : item.entry ? [item.entry] : []) ?? [], [data]);
  const active = entries[index];

  const seekStart = () => { if (active) player.current?.seek(active.start_s, playing); };
  useEffect(seekStart, [active?.clip_id, active?.start_s]);

  const advance = () => {
    if (index < entries.length - 1) setIndex((current) => current + 1);
    else { player.current?.element()?.pause(); setPlaying(false); }
  };
  const toggle = () => {
    const video = player.current?.element();
    if (!video || !active) return;
    if (playing) { video.pause(); setPlaying(false); }
    else { setPlaying(true); void video.play().catch(() => setPlaying(false)); }
  };
  const openEntry = (entry: StringoutEntry, at?: number) => {
    const found = entries.findIndex((candidate) => candidate.segment_id
      ? candidate.segment_id === entry.segment_id
      : candidate.clip_id === entry.clip_id && candidate.start_s === entry.start_s);
    if (found >= 0) setIndex(found);
    window.setTimeout(() => player.current?.seek(at ?? entry.start_s, true), found === index ? 0 : 120);
    setPlaying(true);
  };

  if (error) return <main className="scene-state"><p className="error">{error}</p><Link href={`/project/${projectId}`}>Back to project</Link></main>;
  if (!data) return <main className="scene-state">Loading coverage…</main>;

  return <main className="coverage-shell">
    <header className="coverage-head"><div className="crumbs"><Link href={`/project/${projectId}`}>Project</Link><span>›</span><b>Scene {sceneId}</b><span className="coverage-mode">Coverage Reel</span></div><div className="coverage-stats"><span>{data.entries.length}/{data.shots} shots confirmed</span><span>{clock(data.duration_s)}</span><a className="ghost small" href={api.edlUrl(projectId, sceneId, data.export_fps || 24)}>EDL</a><a className="ghost small" href={api.markersUrl(projectId, sceneId, data.export_fps || 24)}>Markers</a></div></header>
    <div className="coverage-grid">
      <section className="coverage-main">
        <div className="coverage-player"><Player ref={player} className="player" src={active?.proxy_uri ?? ""} poster={active?.sprite_uri} emptyLabel="No source ranges have been chosen for this scene yet. Open a shot and pick the parts of each take you want." onReady={seekStart} onTimeUpdate={(time) => { if (active && time >= active.end_s - .04) advance(); }} onEnded={advance} /><div className="coverage-now"><span>{active?.slug ?? "No confirmed take"}</span>{active && <span>Take {active.take_no} · {clock(active.start_s)}–{clock(active.end_s)}</span>}</div></div>
        <div className="coverage-transport"><button className="ghost" onClick={() => setIndex(Math.max(0, index - 1))} disabled={!index}>← Previous shot</button><button className="primary" onClick={toggle} disabled={!active}>{playing ? "Pause reel" : "Play coverage reel"}</button><button className="ghost" onClick={() => setIndex(Math.min(entries.length - 1, index + 1))} disabled={index >= entries.length - 1}>Next shot →</button></div>
        <div className="coverage-takes">{data.timeline.map((item) => item.entry ? <button key={item.shot} className={(item.entries ?? [item.entry]).some((entry) => entry.segment_id === active?.segment_id) ? "coverage-take on" : "coverage-take"} onClick={() => openEntry((item.entries?.[0] ?? item.entry)!)}><img src={item.entry.sprite_uri} alt=""/><span><b>{item.slug}</b><small>{item.entries?.length || 1} range{(item.entries?.length || 1) === 1 ? "" : "s"} · {Array.from(new Set((item.entries ?? [item.entry]).map((entry) => `T${entry.take_no}`))).join(" + ")}</small></span></button> : <Link key={item.shot} className="coverage-take gap" href={`/project/${projectId}?scene=${sceneId}&shot=${item.shot}`}><span className="gap-icon">＋</span><span><b>{item.slug}</b><small>Choose source ranges</small></span></Link>)}</div>

        <section className="nle-context"><header><div><p className="eyebrow">READ-ONLY COVERAGE TIMELINE</p><h2>Scene {sceneId} coverage</h2></div><span>V1 / A1 · selected source ranges, not an edit</span></header><div className="nle-ruler"><span>00:00</span><span>{clock(data.duration_s * .25)}</span><span>{clock(data.duration_s * .5)}</span><span>{clock(data.duration_s * .75)}</span><span>{clock(data.duration_s)}</span></div>{(["V1","A1"] as const).map((track) => <div className="nle-track" key={track}><b>{track}</b><div>{data.timeline.flatMap((item) => item.entry ? (item.entries?.length ? item.entries : [item.entry]).map((entry, segmentIndex) => <button key={`${track}-${item.shot}-${entry.segment_id || segmentIndex}`} className={`nle-block shot-${item.shot % 5}`} style={{ flexGrow: Math.max(2, entry.duration_s) }} onClick={() => openEntry(entry)}><span>{item.slug} / T{entry.take_no} · part {segmentIndex + 1}</span>{track === "A1" && <i className="waveform"/>}</button>) : [<Link key={`${track}-${item.shot}`} href={`/project/${projectId}?scene=${sceneId}&shot=${item.shot}`} className="nle-gap"><span>GAP</span><small>No confirmed ranges</small></Link>])}</div></div>)}</section>
      </section>

      <aside className="coverage-inspector"><nav><button className={tab === "review" ? "on" : ""} onClick={() => setTab("review")}>AI Review</button><button className={tab === "notes" ? "on" : ""} onClick={() => setTab("notes")}>Notes <span>{data.notes.length}</span></button><button className={tab === "activity" ? "on" : ""} onClick={() => setTab("activity")}>Activity</button></nav>
        {tab === "review" && <div className="coverage-panel"><p className="eyebrow">COVERAGE STATUS</p><h2>{data.unresolved ? `${data.unresolved} shot${data.unresolved === 1 ? " needs" : "s need"} a decision` : "Scene coverage is confirmed"}</h2><p>Only human-confirmed take ranges enter this reel. AI recommendations remain in the shot cockpit until someone confirms them.</p><div className="coverage-findings"><h3>Issues found</h3>{data.findings.length ? data.findings.map((finding, findingIndex) => { const entry = data.entries.find((candidate) => candidate.clip_id === finding.clip_id); return <button key={`${finding.clip_id}-${findingIndex}`} onClick={() => entry ? openEntry(entry, finding.start_s) : undefined}><span className={`issue-severity ${finding.severity}`}/><span><b>{finding.code.replaceAll(".", " ")}</b><small>Shot {finding.shot} · Take {finding.take_no} · {clock(finding.start_s)}</small></span><i>›</i></button>; }) : <p className="empty-panel">No open findings on this scene.</p>}</div></div>}
        {tab === "notes" && <div className="coverage-panel"><h2>Scene notes</h2>{data.notes.length ? data.notes.map((note, noteIndex) => { const entry = data.entries.find((candidate) => candidate.clip_id === note.clip_id); return <button className="coverage-note" key={`${note.clip_id}-${noteIndex}`} onClick={() => entry ? openEntry(entry, note.at_s) : undefined}><span className="avatar">{note.author.slice(0,1).toUpperCase()}</span><span><b>{note.author.split("@")[0]}</b><p>{note.body}</p><small>{clock(note.at_s)}</small></span></button>; }) : <p className="empty-panel">No open notes.</p>}</div>}
        {tab === "activity" && <div className="coverage-panel"><h2>Scene activity</h2>{data.activity.map((row, rowIndex) => <div className="activity-row" key={`${row.at}-${rowIndex}`}><span className="avatar">{row.actor.slice(0,1).toUpperCase()}</span><span><b>{row.actor.split("@")[0] || "System"}</b><p>{row.verb.replaceAll("_", " ")} · {row.detail}</p><small>{row.at ? new Date(row.at).toLocaleString() : ""}</small></span></div>)}</div>}
      </aside>
    </div>
  </main>;
}
