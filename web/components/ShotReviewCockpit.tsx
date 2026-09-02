"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Comments from "@/components/Comments";
import Player, { type PlayerHandle } from "@/components/Player";
import ShotBrief from "@/components/ShotBrief";
import { api, type CoverageSegment, type FindingEvent, type SourceClip, type Take, type TakeAnalysis } from "@/lib/api";
import {
  conflictMessage,
  useSaveCoverage,
  useFindingAction,
  useJudge,
  useShotEdits,
  useShotScreen,
} from "@/lib/queries";

type Range = { from: number; to: number };
type Focus = { clipId: string; finding: FindingEvent };

const HUMAN_REASONS = [
  "better performance",
  "director's preference",
  "cuts better with the next shot",
  "stronger emotional read",
  "matches the scene's rhythm",
] as const;

function tc(value: number) {
  const minutes = Math.floor(value / 60);
  const seconds = Math.max(0, value - minutes * 60);
  return `${String(minutes).padStart(2, "0")}:${seconds.toFixed(2).padStart(5, "0")}`;
}

function label(code: string) {
  return code.replaceAll(".", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function persistedSegmentId(value: string): string | undefined {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
    ? value
    : undefined;
}

function findingSeverity(value: string): "note" | "attention" | "blocking" {
  return value === "note" || value === "blocking" ? value : "attention";
}

function analysisFor(analyses: TakeAnalysis[], clipId: string) {
  return analyses.find((row) => String(row.clip_id) === clipId);
}

export default function ShotReviewCockpit({
  projectId,
  scene,
  shot,
  canComment,
  canCurate,
  you,
  teamEmails,
  initialClipId = "",
  initialAt = 0,
}: {
  projectId: number;
  scene: number;
  shot: number;
  canComment: boolean;
  canCurate: boolean;
  you: string;
  teamEmails: string[];
  initialClipId?: string;
  initialAt?: number;
}) {
  const screen = useShotScreen(projectId, scene, shot);
  const verdicts = screen.data?.verdicts;
  const analyses = screen.data?.analyses ?? [];
  // The shot's footage, which exists whether or not a comparison does. Reading
  // takes out of the verdicts meant a shot holding one clip drew nothing at
  // all — no player, no lanes, no way to cut a range — while its proxy sat
  // built and reachable.
  const takes = screen.data?.takes ?? [];
  const compared = Boolean(verdicts && verdicts.takes.length);
  const recommended = compared
    ? takes.find((take) => take.clip_id === verdicts?.recommended) ?? takes[0]
    : undefined;
  const [aId, setAId] = useState("");
  const [bId, setBId] = useState("");
  const [activeSide, setActiveSide] = useState<"a" | "b">("a");
  const [focus, setFocus] = useState<Focus | null>(null);
  const [range, setRange] = useState<Range>({ from: 0, to: 0 });
  const [reason, setReason] = useState<string>("better performance");
  const [notice, setNotice] = useState("");
  const [adjusting, setAdjusting] = useState(false);
  const [sourceQuery, setSourceQuery] = useState("");
  const [sourceRows, setSourceRows] = useState<SourceClip[]>([]);
  const [sourcePreview, setSourcePreview] = useState<SourceClip | null>(null);
  const [sourceBusy, setSourceBusy] = useState(false);
  const [commentAt, setCommentAt] = useState<{ clipId: string; at: number } | null>(null);
  const [playheads, setPlayheads] = useState<Record<string, number>>({});
  const playerA = useRef<PlayerHandle>(null);
  const playerB = useRef<PlayerHandle>(null);
  const selectPlayer = useRef<PlayerHandle>(null);

  useEffect(() => {
    if (!takes.length) return;
    setAId((current) => current || recommended?.clip_id || takes[0].clip_id);
    setBId((current) => current || takes.find((take) => take.clip_id !== recommended?.clip_id)?.clip_id || takes[0].clip_id);
  }, [takes, recommended]);

  useEffect(() => {
    if (!initialClipId || !takes.some((take) => take.clip_id === initialClipId)) return;
    setAId(initialClipId);
    setActiveSide("a");
    const timer = window.setTimeout(() => playerA.current?.seek(initialAt, true), 350);
    return () => window.clearTimeout(timer);
  }, [initialAt, initialClipId, takes]);

  const a = takes.find((take) => take.clip_id === aId) ?? takes[0];
  const b = takes.find((take) => take.clip_id === bId) ?? takes[1] ?? takes[0];
  const selected = activeSide === "a" ? a : b;
  const selectedAnalysis = selected ? analysisFor(analyses, selected.clip_id) : undefined;
  const saveCoverage = useSaveCoverage(projectId, scene, shot, verdicts?.rev ?? 0);
  const [selects, setSelects] = useState<CoverageSegment[]>([]);
  const [selectPreviewIndex, setSelectPreviewIndex] = useState<number | null>(null);
  const findingAction = useFindingAction(projectId, scene, shot);
  const judge = useJudge(projectId, scene, shot);
  const edits = useShotEdits(projectId, scene, shot, screen.data?.brief);
  const duration = Math.max(1, ...takes.map((take) => take.duration_s || 0));
  const pct = (value: number) => `${Math.min(100, Math.max(0, (value / duration) * 100))}%`;

  useEffect(() => {
    if (!selected) return;
    const analysis = analysisFor(analyses, selected.clip_id);
    const primary = analysis?.primary_usable_range;
    setRange({
      from: primary?.start_s ?? selected.usable_from_s ?? 0,
      to: primary?.end_s ?? selected.usable_to_s ?? selected.duration_s,
    });
  }, [selected, analyses]);

  useEffect(() => {
    setSelects((verdicts?.coverage_segments ?? []).map((item, position) => ({ ...item, position })));
  }, [verdicts?.coverage_segments]);

  const activePlayer = (clipId: string) => (clipId === a?.clip_id ? playerA.current : playerB.current);
  const inspect = (clipId: string, finding: FindingEvent) => {
    setFocus({ clipId, finding });
    if (clipId === a?.clip_id) setActiveSide("a");
    else if (clipId === b?.clip_id) setActiveSide("b");
    activePlayer(clipId)?.seek(finding.start_s, true);
  };

  const act = async (
    action: "confirm" | "dismiss" | "correct" | "adjust_range",
    changes: { detail?: string; severity?: "note" | "attention" | "blocking" } = {},
  ) => {
    if (!focus) return;
    try {
      await findingAction.mutateAsync({
        clipId: focus.clipId,
        findingId: String(focus.finding.finding_id),
        body: {
          rev: focus.finding.revision,
          action,
          ...(action === "adjust_range"
            ? { start_s: focus.finding.start_s, end_s: focus.finding.end_s }
            : action === "correct" ? changes : {}),
        },
      });
      setNotice(action === "dismiss" ? "Finding dismissed. Its history is preserved." : "Finding review recorded.");
      setFocus(null);
      setAdjusting(false);
    } catch (error) {
      setNotice(conflictMessage(error) ?? (error instanceof Error ? error.message : "Could not record that review."));
    }
  };

  const addRange = () => {
    if (!selected) return;
    if (!(range.to > range.from)) return;
    setSelects((current) => [...current, {
      segment_id: crypto.randomUUID(), clip_id: selected.clip_id,
      take_no: selected.take_no, source_in_s: range.from, source_out_s: range.to,
      position: current.length, reason, created_by: you,
    }]);
    setNotice(`Take ${selected.take_no} ${tc(range.from)}–${tc(range.to)} added. Save the shot selects when ready.`);
  };

  const saveSelects = async () => {
    try {
      await saveCoverage.mutateAsync({
        reason: reason || "human coverage selection",
        segments: selects.map((item) => ({
          segment_id: persistedSegmentId(item.segment_id), clip_id: item.clip_id,
          source_in_s: item.source_in_s, source_out_s: item.source_out_s,
        })),
      });
      setNotice(`${selects.length} source range${selects.length === 1 ? "" : "s"} now stand for this shot.`);
    } catch (error) {
      setNotice(conflictMessage(error) ?? (error instanceof Error ? error.message : "Could not save shot selects."));
    }
  };

  const previewSegment = selectPreviewIndex === null ? null : selects[selectPreviewIndex];
  const previewSource = previewSegment
    ? takes.find((take) => take.clip_id === previewSegment.clip_id)
      ?? sourceRows.find((source) => source.clip_id === previewSegment.clip_id)
    : null;

  const findSources = async () => {
    setSourceBusy(true);
    try {
      setSourceRows(await api.projectSources(projectId, sourceQuery));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not search project footage.");
    } finally {
      setSourceBusy(false);
    }
  };

  const addSource = (source: SourceClip) => {
    setSelects((current) => [...current, {
      segment_id: crypto.randomUUID(), clip_id: source.clip_id, take_no: source.take_no,
      source_in_s: 0, source_out_s: source.duration_s, position: current.length,
      reason: "reused project source", created_by: you,
    }]);
    setNotice(`Scene ${source.scene} / Shot ${source.shot} / Take ${source.take_no} added as a reusable source. Its slate placement did not move.`);
  };

  if (screen.isPending) return <div className="cockpit-state">Loading shot intelligence…</div>;
  if (screen.isError) return <div className="cockpit-state error">Could not load this shot. <button onClick={() => void screen.refetch()}>Retry</button></div>;
  // Only a shot with no footage at all is empty. One take is a shot you can
  // watch, analyse and cut a range from; it is merely a shot nothing can be
  // compared against.
  if (!takes.length) return <div className="cockpit-state"><div><p>No footage has been placed in this shot yet.</p><p className="policy-note">Upload takes, or move a clip here from the placement inbox.</p></div></div>;

  const humanChoiceRecorded = (verdicts?.rev ?? 0) > 0 || selects.length > 0 || takes.some(
    (take) => take.outcome === "selected" && take.decided_by === "human",
  );
  const selectedAt = selected ? playheads[selected.clip_id] ?? 0 : 0;

  return (
    <div className="shot-cockpit">
      <section className="cockpit-main">
        <header className="cockpit-titlebar">
          <div>
            <p className="eyebrow">SHOT REVIEW</p>
            <h1>Scene {screen.data?.brief.heading || scene} / {screen.data?.brief.slug || `Shot ${shot}`}</h1>
          </div>
          <div className="cockpit-summary">
            <span>{takes.length} takes</span>
            <span>{analyses.filter((item) => item.coverage_complete).length}/{takes.length} fully analysed</span>
            <span className={humanChoiceRecorded ? "live-dot complete" : "live-dot"}>{humanChoiceRecorded ? "Human choice recorded" : "Human decision required"}</span>
          </div>
        </header>

        {/* A comparison needs two takes. With one, the A/B chooser offered the
            same clip on both sides and the stage drew it twice — two identical
            videos side by side, each half the width it deserved. */}
        {takes.length > 1 && <div className="compare-toolbar" aria-label="A B comparison">
          <label>A<select value={a?.clip_id} onChange={(event) => { setAId(event.target.value); setActiveSide("a"); }}>
            {takes.map((take) => <option key={take.clip_id} value={take.clip_id}>Take {take.take_no}</option>)}
          </select></label>
          <button className={activeSide === "a" ? "compare-side on" : "compare-side"} onClick={() => setActiveSide("a")}>Listen to A</button>
          <span className="compare-vs">A / B</span>
          <button className={activeSide === "b" ? "compare-side on" : "compare-side"} onClick={() => setActiveSide("b")}>Listen to B</button>
          <label>B<select value={b?.clip_id} onChange={(event) => { setBId(event.target.value); setActiveSide("b"); }}>
            {takes.map((take) => <option key={take.clip_id} value={take.clip_id}>Take {take.take_no}</option>)}
          </select></label>
        </div>}

        <div className={takes.length > 1 ? "compare-players" : "compare-players single"}>
          {(takes.length > 1
            ? [{ side: "a" as const, take: a, ref: playerA }, { side: "b" as const, take: b, ref: playerB }]
            : [{ side: "a" as const, take: a, ref: playerA }]
          ).map(({ side, take, ref }) => take && (
            <div key={side} className={activeSide === side ? "compare-player active" : "compare-player"} onClick={() => setActiveSide(side)}>
              <span className="player-badge">{takes.length > 1 ? `${side.toUpperCase()} · ` : ""}TAKE {take.take_no}</span>
              <Player ref={ref} className="player" src={take.proxy_uri} poster={take.sprite_uri} onTimeUpdate={(at) => {
                setPlayheads((current) => ({ ...current, [take.clip_id]: at }));
                if (activeSide === side) setCommentAt((old) => old && old.clipId === take.clip_id ? { ...old, at } : old);
              }} />
            </div>
          ))}
        </div>

        <div className="take-card-strip">
          {takes.map((take) => {
            const analysis = analysisFor(analyses, take.clip_id);
            const issueCount = analysis?.findings.length ?? take.findings.length;
            return <button key={take.clip_id} className={selected?.clip_id === take.clip_id ? "take-card selected" : "take-card"} onClick={() => { if (take.clip_id === a?.clip_id) setActiveSide("a"); else if (take.clip_id === b?.clip_id) setActiveSide("b"); else { setBId(take.clip_id); setActiveSide("b"); } }}>
              <span className="take-card-no">Take {take.take_no}</span>
              <span className="take-badges"><b>PROXY</b><b>{take.fps ? `${Math.round(take.fps)} FPS` : "FPS UNMEASURED"}</b></span>
              <span className="take-score">{compared ? <>{Math.round(take.score * 100)} <small>technical</small></> : <small>not compared</small>}</span>
              <span className={issueCount ? "issue-count" : "issue-count clean"}>{issueCount ? `${issueCount} issue${issueCount === 1 ? "" : "s"}` : "clean"}</span>
            </button>;
          })}
        </div>

        <section className="issue-lanes">
          <header><div><p className="eyebrow">TAKE ANALYSIS · USABLE RANGES &amp; ISSUES</p><h2>Every take on one clock</h2></div><div className="lane-legend"><span className="clean-key">Clean</span><span className="warn-key">Issue</span><span className="slate-key">Slate / exit</span></div></header>
          <div className="time-ruler"><span>00:00</span><span>{tc(duration * .25)}</span><span>{tc(duration * .5)}</span><span>{tc(duration * .75)}</span><span>{tc(duration)}</span></div>
          {takes.map((take) => {
            const analysis = analysisFor(analyses, take.clip_id);
            const findings = analysis?.findings ?? [];
            const safe = analysis?.safe_ranges ?? take.safe_ranges;
            return <div className={selected?.clip_id === take.clip_id ? "issue-lane selected" : "issue-lane"} key={take.clip_id}>
              <button className="lane-label" onClick={() => { setBId(take.clip_id); setActiveSide("b"); }}>T{take.take_no}<small>{tc(take.duration_s)}</small></button>
              <div className="lane-track">
                <span className="lane-empty" style={{ width: pct(take.duration_s) }} />
                {safe.map((item, index) => <button key={`safe-${index}`} className="lane-safe" style={{ left: pct(item.start_s), width: pct(item.end_s - item.start_s) }} onClick={() => activePlayer(take.clip_id)?.seek(item.start_s, true)} title={`Clean ${tc(item.start_s)}–${tc(item.end_s)}`} />)}
                {findings.map((finding) => <button key={String(finding.finding_id)} className={`lane-finding severity-${finding.severity}`} style={{ left: pct(finding.start_s), width: pct(Math.max(.4, finding.end_s - finding.start_s)) }} onClick={() => inspect(take.clip_id, finding)} title={`${label(finding.code)} ${tc(finding.start_s)}–${tc(finding.end_s)}`}><span>{label(finding.code)}</span></button>)}
              </div>
            </div>;
          })}
        </section>
      </section>

      <aside className="cockpit-inspector">
        {focus ? (
          <FindingInspector focus={focus} take={takes.find((take) => take.clip_id === focus.clipId)} adjusting={adjusting} setAdjusting={setAdjusting} onChange={(start, end) => setFocus({ ...focus, finding: { ...focus.finding, start_s: start, end_s: end } })} onConfirm={() => void act("confirm")} onDismiss={() => void act("dismiss")} onCorrect={(detail, severity) => void act("correct", { detail, severity })} onAdjust={() => void act("adjust_range")} pending={findingAction.isPending} canAct={canComment} />
        ) : (
          <>
            <p className="eyebrow">{compared ? "AI RECOMMENDATION" : "NOT COMPARED"}</p>
            {/* A field of one has no winner, and a score of 0% beside the only
                take reads as a verdict against it. Say what is true instead. */}
            {compared && recommended ? <>
              <div className="recommendation">
                <span className="recommend-icon">✦</span>
                <div><h2>Take {recommended.take_no} suggested</h2><p>{recommended.reason || "Best observable technical coverage."}</p></div>
                <b>{Math.round(recommended.score * 100)}%</b>
              </div>
              <p className="policy-note">Technical, continuity and completion evidence only. Performance remains your decision.</p>
            </> : <>
              <div className="recommendation not-compared">
                <span className="recommend-icon">◇</span>
                <div><h2>{takes.length === 1 ? "One take in this shot" : `${takes.length} takes, not yet compared`}</h2><p>{takes.length === 1 ? "There is nothing to compare it against. Watch it, review its findings and cut the ranges you want." : "Run the comparison to get a suggestion, or select ranges yourself."}</p></div>
              </div>
              {canCurate && takes.length > 1 && <button className="primary" disabled={judge.isPending} onClick={() => void judge.mutateAsync()}>{judge.isPending ? "Comparing full takes…" : "Analyse & compare takes"}</button>}
            </>}
            {selected && <div className="selection-card">
              <h3>Add source range</h3>
              <div className="selection-take">Take {selected.take_no}<span>{!compared ? "Only take" : selected.clip_id === recommended?.clip_id ? "AI suggestion" : "Alternative"}</span></div>
              <label>Use range<div className="range-inputs"><input type="number" step="0.01" min="0" max={selected.duration_s} value={range.from} onChange={(event) => setRange({ ...range, from: Number(event.target.value) })} /><span>→</span><input type="number" step="0.01" min="0" max={selected.duration_s} value={range.to} onChange={(event) => setRange({ ...range, to: Number(event.target.value) })} /></div></label>
              {selected.clip_id !== recommended?.clip_id && <div className="reason-chips">{HUMAN_REASONS.map((item) => <button key={item} className={reason === item ? "chip on" : "chip"} onClick={() => setReason(item)}>{item}</button>)}</div>}
              <button className="ghost cockpit-confirm" disabled={!canComment || !(range.to > range.from)} onClick={addRange}>{canComment ? `Add Take ${selected.take_no} range` : "Sign in to select ranges"}</button>
              <div className="shot-selects"><div className="shot-selects-head"><b>Shot selects</b><span>{selects.length} range{selects.length === 1 ? "" : "s"}</span></div>{selects.map((item, index) => <div className="shot-select-row" key={item.segment_id}><span><b>{index + 1}. Take {item.take_no}</b><span className="select-range-inputs"><input aria-label={`Select ${index + 1} in`} type="number" min="0" step="0.01" value={item.source_in_s} onChange={(event) => setSelects((rows) => rows.map((row, at) => at === index ? { ...row, source_in_s: Number(event.target.value) } : row))} /><i>→</i><input aria-label={`Select ${index + 1} out`} type="number" min="0" step="0.01" value={item.source_out_s} onChange={(event) => setSelects((rows) => rows.map((row, at) => at === index ? { ...row, source_out_s: Number(event.target.value) } : row))} /></span></span><span className="select-order"><button disabled={!index} onClick={() => setSelects((rows) => { const next = [...rows]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; return next; })}>↑</button><button disabled={index === selects.length - 1} onClick={() => setSelects((rows) => { const next = [...rows]; [next[index + 1], next[index]] = [next[index], next[index + 1]]; return next; })}>↓</button><button onClick={() => setSelects((rows) => rows.filter((_, at) => at !== index))}>Remove</button></span></div>)}</div>
              <details className="source-library"><summary>Reuse footage from another shot or scene</summary><p className="policy-note">Adds a source range here without changing where its slate placed the clip.</p><div className="source-search"><input value={sourceQuery} onChange={(event) => setSourceQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void findSources(); }} placeholder="Scene, shot, description or clip ID"/><button className="ghost" disabled={sourceBusy} onClick={() => void findSources()}>{sourceBusy ? "Finding…" : "Find"}</button></div>{sourcePreview?.proxy_uri && <Player className="source-preview" src={sourcePreview.proxy_uri} poster={sourcePreview.sprite_uri} />}{sourceRows.map((source) => <div className="source-row" key={source.clip_id}><button className="source-ident" onClick={() => setSourcePreview(source)}><b>Scene {source.scene_code || source.scene} · Shot {source.shot_code || source.shot} · Take {source.take_no}</b><small>{tc(source.duration_s)}{source.description ? ` · ${source.description}` : ""}</small></button><button className="ghost" disabled={!canComment} onClick={() => addSource(source)}>Add range</button></div>)}</details>
              {previewSegment && previewSource?.proxy_uri && <div className="shot-select-preview"><Player key={previewSegment.segment_id} ref={selectPlayer} src={previewSource.proxy_uri} poster={previewSource.sprite_uri} onReady={() => selectPlayer.current?.seek(previewSegment.source_in_s, true)} onTimeUpdate={(at) => { if (at >= previewSegment.source_out_s - .05) setSelectPreviewIndex((index) => index !== null && index + 1 < selects.length ? index + 1 : null); }} /><small>Playing select {(selectPreviewIndex ?? 0) + 1} of {selects.length} · Take {previewSegment.take_no} · {tc(previewSegment.source_in_s)}–{tc(previewSegment.source_out_s)}</small></div>}
              <button className="ghost cockpit-confirm" disabled={!selects.length} onClick={() => setSelectPreviewIndex(0)}>▶ Play this shot</button>
              <button className="primary cockpit-confirm" disabled={!canComment || saveCoverage.isPending} onClick={() => void saveSelects()}>{saveCoverage.isPending ? "Saving…" : `Save ${selects.length} shot select${selects.length === 1 ? "" : "s"}`}</button>
            </div>}
            <WhoIsOnIt
              assignee={screen.data?.brief.assignee ?? ""}
              state={screen.data?.brief.state ?? ""}
              you={you}
              team={teamEmails}
              canAct={canComment}
              pending={edits.assign.isPending || edits.setState.isPending}
              onAssign={async (who) => {
                try {
                  await edits.assign.mutateAsync(who);
                  setNotice(who ? `Assigned to ${who.split("@")[0]}.` : "Left unclaimed.");
                } catch (error) {
                  setNotice(conflictMessage(error) ?? "Could not change who is on this shot.");
                }
              }}
              onState={async (next) => {
                try {
                  await edits.setState.mutateAsync(next);
                  setNotice(next ? `Marked ${next.replaceAll("_", " ")}.` : "Status cleared.");
                } catch (error) {
                  setNotice(conflictMessage(error) ?? "Could not change the status.");
                }
              }}
            />
            {screen.data?.brief && (
              // Built and wired to both agents from the start — the analyst's
              // briefing already renders these five fields into the model's
              // context, with its own rule stated beside them: "It tells you
              // where to look; the footage tells you what is there, and where
              // they disagree the footage is right." Nobody could ever reach
              // the editor for it, so no shot has ever been analysed against
              // a script line.
              <ShotBrief
                projectId={projectId}
                scene={scene}
                shot={shot}
                brief={screen.data.brief}
                canEdit={canCurate}
                onSave={(fields) => edits.saveBrief.mutateAsync(fields)}
              />
            )}
            <div className="finding-list"><h3>Findings to verify</h3>{analyses.flatMap((analysis) => analysis.findings.map((finding) => ({ analysis, finding }))).slice(0, 8).map(({ analysis, finding }) => <button key={String(finding.finding_id)} onClick={() => inspect(String(analysis.clip_id), finding)}><span className={`finding-dot severity-${finding.severity}`} /><span><b>{tc(finding.start_s)}–{tc(finding.end_s)} {label(finding.code)}</b><small>Take {analysis.clip.take_no} · {finding.detail}</small></span><i>›</i></button>)}</div>
          </>
        )}
        {notice && <p className="cockpit-notice">{notice}</p>}
        {canComment && selected && <button className="ghost note-at-playhead" onClick={() => setCommentAt({ clipId: selected.clip_id, at: selectedAt })}>＋ Add note at {tc(selectedAt)}</button>}
        <Comments projectId={projectId} scene={scene} shot={shot} canComment={canComment} comments={screen.data?.comments ?? []} takes={takes.map((take) => ({ clip_id: take.clip_id, take_no: take.take_no }))} pending={commentAt} onConsumedPending={() => setCommentAt(null)} />
      </aside>
    </div>
  );
}

function FindingInspector({ focus, take, adjusting, setAdjusting, onChange, onConfirm, onDismiss, onCorrect, onAdjust, pending, canAct }: { focus: Focus; take?: Take; adjusting: boolean; setAdjusting: (value: boolean) => void; onChange: (start: number, end: number) => void; onConfirm: () => void; onDismiss: () => void; onCorrect: (detail: string, severity: "note" | "attention" | "blocking") => void; onAdjust: () => void; pending: boolean; canAct: boolean }) {
  const finding = focus.finding;
  const evidence = useRef<PlayerHandle>(null);
  const [correcting, setCorrecting] = useState(false);
  const [detail, setDetail] = useState(finding.detail);
  const [severity, setSeverity] = useState<"note" | "attention" | "blocking">(findingSeverity(finding.severity));
  useEffect(() => {
    setCorrecting(false);
    setDetail(finding.detail);
    setSeverity(findingSeverity(finding.severity));
  }, [finding.finding_id, finding.detail, finding.severity]);
  return <div className="finding-inspector">
    <p className="eyebrow">FINDING · TAKE {take?.take_no ?? "—"}</p>
    <h2>{tc(finding.start_s)}–{tc(finding.end_s)} {label(finding.code)}</h2>
    {take?.proxy_uri ? <Player ref={evidence} className="evidence-player" src={take.proxy_uri} poster={take.sprite_uri} onReady={() => evidence.current?.seek(finding.start_s)} /> : <div className="evidence-placeholder">Evidence frame unavailable</div>}
    <div className="frame-meta">
      <span>{take?.fps ? `${Math.max(1, Math.round((finding.end_s - finding.start_s) * take.fps))} frames` : `${tc(finding.end_s - finding.start_s)} duration`}</span>
      <span>{finding.severity}</span><span>{finding.sources.join(" + ") || "AI observation"}</span>
    </div>
    <section><p className="eyebrow">AI TECHNICAL NOTE</p><p>{finding.detail || "The model detected a visible technical inconsistency in this range."}</p></section>
    {adjusting && <div className="range-inputs"><input aria-label="Finding start" type="number" step="0.01" value={finding.start_s} onChange={(event) => onChange(Number(event.target.value), finding.end_s)} /><span>→</span><input aria-label="Finding end" type="number" step="0.01" value={finding.end_s} onChange={(event) => onChange(finding.start_s, Number(event.target.value))} /></div>}
    {correcting && <div className="finding-correction"><label>Correct technical note<textarea value={detail} maxLength={500} onChange={(event) => setDetail(event.target.value)} /></label><label>Severity<select value={severity} onChange={(event) => setSeverity(event.target.value as typeof severity)}><option value="note">Note</option><option value="attention">Attention</option><option value="blocking">Blocking</option></select></label><button className="primary" disabled={pending || !detail.trim()} onClick={() => onCorrect(detail.trim(), severity)}>Save correction</button></div>}
    <div className="finding-actions"><button className="primary" disabled={!canAct || pending} onClick={onConfirm}>Issue is correct</button><button className="ghost" disabled={!canAct || pending} onClick={onDismiss}>Dismiss issue</button><button className="ghost" disabled={!canAct || pending} onClick={() => setCorrecting((value) => !value)}>{correcting ? "Cancel correction" : "Correct finding"}</button>{adjusting ? <button className="ghost" disabled={!canAct || pending} onClick={onAdjust}>Save adjusted range</button> : <button className="ghost" disabled={!canAct} onClick={() => setAdjusting(true)}>Adjust range</button>}</div>
    {!canAct && <p className="policy-note">Sign in to confirm, correct, dismiss, or adjust this finding.</p>}
  </div>;
}

/**
 * Who has this shot, and whether it is still moving.
 *
 * Assignment was filterable on the project page and settable nowhere: the only
 * control lived in the component the cockpit replaced, so the workspace offered
 * a filter for a state no one could enter. That is why nobody could tell what
 * it was for.
 *
 * It is worth one line of explanation because the benefit is not obvious from a
 * dropdown. Three editors share one queue; claiming a shot is how the other two
 * stop seeing it as unclaimed work and reviewing the same takes twice.
 */
function WhoIsOnIt({
  assignee,
  state,
  you,
  team,
  canAct,
  pending,
  onAssign,
  onState,
}: {
  assignee: string;
  state: string;
  you: string;
  team: string[];
  canAct: boolean;
  pending: boolean;
  onAssign: (who: string) => void;
  onState: (next: "" | "in_progress" | "approved") => void;
}) {
  const people = useMemo(() => {
    const set = new Set(team.filter(Boolean));
    if (you) set.add(you);
    if (assignee) set.add(assignee);
    return Array.from(set).sort();
  }, [team, you, assignee]);

  const mine = Boolean(you) && assignee === you;

  return (
    <div className="who-card">
      <p className="eyebrow">WHO IS ON THIS</p>
      <div className="who-row">
        <select
          aria-label="Assigned to"
          value={assignee}
          disabled={!canAct || pending}
          onChange={(event) => onAssign(event.target.value)}
        >
          <option value="">Unclaimed</option>
          {people.map((person) => (
            <option key={person} value={person}>
              {person === you ? `${person.split("@")[0]} (you)` : person.split("@")[0]}
            </option>
          ))}
        </select>
        {canAct && you && !mine && (
          <button className="ghost small" disabled={pending} onClick={() => onAssign(you)}>
            Claim
          </button>
        )}
        {canAct && mine && (
          <button className="ghost small" disabled={pending} onClick={() => onAssign("")}>
            Release
          </button>
        )}
      </div>
      <div className="who-row">
        <select
          aria-label="Shot status"
          value={state}
          disabled={!canAct || pending}
          onChange={(event) => onState(event.target.value as "" | "in_progress" | "approved")}
        >
          <option value="">No status</option>
          <option value="in_progress">In progress</option>
          <option value="approved">Approved</option>
        </select>
      </div>
      <p className="policy-note">
        Claiming takes this shot out of everyone else&apos;s unclaimed queue, so
        two people do not review the same takes. Approved removes it from the
        queue entirely.
      </p>
    </div>
  );
}
