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

/** What the pipeline is doing, in words a person can act on. */
function stageLabel(stage: string) {
  if (stage === "processing") return "analysing…";
  if (stage === "pending") return "queued for analysis";
  if (stage === "failed") return "analysis failed";
  if (stage === "completed") return "analysed";
  return "not analysed yet";
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
  focusTake = 0,
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
  /** A take chosen in the rail. Opens it on the A side. */
  focusTake?: number;
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
    // Open on the recommended take when there is one, otherwise the last take
    // shot — which is the one an editor is usually coming to look at.
    setAId((current) => current || recommended?.clip_id || takes[takes.length - 1].clip_id);
  }, [takes, recommended]);

  useEffect(() => {
    if (!initialClipId || !takes.some((take) => take.clip_id === initialClipId)) return;
    setAId(initialClipId);
    const timer = window.setTimeout(() => playerA.current?.seek(initialAt, true), 350);
    return () => window.clearTimeout(timer);
  }, [initialAt, initialClipId, takes]);

  // One number decides the stage. `chosen` is the take being reviewed and
  // `previous` is the one before it, which is what it gets compared against.
  const chosenTakeNo = takes.find((take) => take.clip_id === aId)?.take_no ?? takes[0]?.take_no ?? 0;
  const chosen = takes.find((take) => take.take_no === chosenTakeNo) ?? takes[0];
  const chosenIndex = takes.findIndex((take) => take.take_no === chosenTakeNo);
  const previous = chosenIndex > 0 ? takes[chosenIndex - 1] : undefined;
  const chooseTake = (takeNo: number) => {
    const wanted = takes.find((take) => take.take_no === takeNo);
    if (wanted) setAId(wanted.clip_id);
  };
  const a = previous ?? chosen;
  const b = chosen;
  const selected = chosen;
  const selectedAnalysis = selected ? analysisFor(analyses, selected.clip_id) : undefined;
  // The brief's revision, which is the shot document's revision — the same one
  // `commit_coverage` checks. `verdicts.rev` is a copy of it and is null when
  // nothing has been compared, so on a one-take shot this sent 0 forever: the
  // first save succeeded, bumped the shot to rev 1, and every save after it
  // was refused as a stale write.
  const saveCoverage = useSaveCoverage(projectId, scene, shot, screen.data?.brief.rev ?? 0);
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
    // From the shot, not from a comparison it may never have had. Reading this
    // off `verdicts` meant every saved range vanished on refresh for any shot
    // with fewer than two takes — saved correctly, then never asked for.
    setSelects((screen.data?.coverage_segments ?? []).map((item, position) => ({ ...item, position })));
  }, [screen.data?.coverage_segments]);

  // Every open finding across every take, flattened once so the count in the
  // header and the rows beneath it cannot disagree.
  const openFindings = useMemo(
    () => analyses.flatMap((analysis) => analysis.findings.map((finding) => ({ analysis, finding }))),
    [analyses],
  );

  // Escape closes the finding. It was the first thing tried and did nothing.
  useEffect(() => {
    if (!focus) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setFocus(null); setAdjusting(false); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focus]);

  // Whether the tray differs from what is stored. The Save button stayed lit
  // after a successful save, so the only way to know whether a change had been
  // written was to reload and look.
  const savedSelects = screen.data?.coverage_segments ?? [];
  const dirty = useMemo(() => {
    const shape = (rows: CoverageSegment[]) =>
      rows.map((r) => `${r.clip_id}:${r.source_in_s}:${r.source_out_s}`).join("|");
    return shape(selects) !== shape(savedSelects as CoverageSegment[]);
  }, [selects, savedSelects]);

  // Two ranges from the same take share a proxy URL, so the player's own
  // load effect does not fire between them. Seek on the segment changing
  // rather than on the source changing, or the second range plays from
  // wherever the first one ended.
  useEffect(() => {
    if (selectPreviewIndex === null) return;
    const segment = selects[selectPreviewIndex];
    if (!segment) return;
    selectPlayer.current?.seek(segment.source_in_s, true);
  }, [selectPreviewIndex, selects]);

  const [issueTab, setIssueTab] = useState(0);
  useEffect(() => {
    if (chosenTakeNo) setIssueTab(chosenTakeNo);
  }, [chosenTakeNo]);

  const stageOf = (clipId: string) => screen.data?.analysis_state?.[clipId] ?? "";

  // A take picked in the rail opens on the A side, swapping B out of the way
  // if it was already showing it.
  useEffect(() => {
    if (!focusTake) return;
    const wanted = takes.find((take) => take.take_no === focusTake);
    if (wanted) setAId(wanted.clip_id);
  }, [focusTake, takes]);

  const activePlayer = (clipId: string) => (clipId === a?.clip_id ? playerA.current : playerB.current);
  const inspect = (clipId: string, finding: FindingEvent) => {
    // A second click on the finding already open closes it — the same gesture
    // that opened it, which is what a person reaches for before they look for
    // a button.
    if (focus && String(focus.finding.finding_id) === String(finding.finding_id)) {
      setFocus(null);
      setAdjusting(false);
      return;
    }
    setFocus({ clipId, finding });
    // Opening a finding brings its take to the front of the stage.
    const owner = takes.find((take) => take.clip_id === clipId);
    if (owner) setAId(owner.clip_id);
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

  // The shot's standing decision, in one phrase.
  //
  // A shot used to have one winning take, so "Take 4" said everything. Ranges
  // from several takes have no single winner, and calling that "Take 4"
  // because take 4 happened to be first would be a lie about what plays.
  const standing = useMemo(() => {
    if (!selects.length) return "";
    const used = Array.from(new Set(selects.map((item) => item.take_no))).sort((x, y) => x - y);
    const ranges = `${selects.length} range${selects.length === 1 ? "" : "s"}`;
    if (used.length === 1) return `Take ${used[0]} · ${ranges}`;
    return `Custom · ${ranges} from take${used.length === 1 ? "" : "s"} ${used.join(", ")}`;
  }, [selects]);

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
            <span className={humanChoiceRecorded ? "live-dot complete" : "live-dot"} title={standing || undefined}>{standing || "No take chosen yet"}</span>
          </div>
        </header>

        {/* A comparison needs two takes. With one, the A/B chooser offered the
            same clip on both sides and the stage drew it twice — two identical
            videos side by side, each half the width it deserved. */}
        {takes.length > 1 && <div className="compare-toolbar" aria-label="Which take">
          {/* One choice, not two. Two independent A/B pickers meant the pair
              could hold the same take, or a pair nobody meant to compare; and
              which box below was "selected" answered neither. Choosing take N
              shows take N with the take before it, which is the comparison an
              editor actually makes. */}
          <span className="compare-vs">Comparing</span>
          {takes.map((take) => (
            <button
              key={take.clip_id}
              className={take.take_no === chosenTakeNo ? "compare-side on" : "compare-side"}
              aria-current={take.take_no === chosenTakeNo ? "true" : undefined}
              onClick={() => chooseTake(take.take_no)}
            >
              Take {take.take_no}
            </button>
          ))}
          {previous && <span className="compare-hint">with take {previous.take_no}</span>}
        </div>}

        <div className={previous ? "compare-players" : "compare-players single"}>
          {/* Take 1 stands alone — there is nothing before it to compare
              against. Every later take sits on the right with its predecessor
              on the left, which is the direction a shoot runs in. */}
          {(previous
            ? [{ side: "a" as const, take: previous, ref: playerA }, { side: "b" as const, take: chosen, ref: playerB }]
            : [{ side: "a" as const, take: chosen, ref: playerA }]
          ).map(({ side, take, ref }) => take && (
            <div key={side} className={take.take_no === chosenTakeNo ? "compare-player active" : "compare-player"} onClick={() => chooseTake(take.take_no)}>
              <span className="player-badge">TAKE {take.take_no}{take.take_no === chosenTakeNo && previous ? " · chosen" : ""}</span>
              <Player ref={ref} className="player" src={take.proxy_uri} poster={take.sprite_uri} onTimeUpdate={(at) => {
                setPlayheads((current) => ({ ...current, [take.clip_id]: at }));
                if (take.take_no === chosenTakeNo) setCommentAt((old) => old && old.clipId === take.clip_id ? { ...old, at } : old);
              }} />
            </div>
          ))}
        </div>

        <div className="take-card-strip">
          {takes.map((take) => {
            const analysis = analysisFor(analyses, take.clip_id);
            const issueCount = analysis?.findings.length ?? take.findings.length;
            const stage = stageOf(take.clip_id);
            return <button key={take.clip_id} className={take.take_no === chosenTakeNo ? "take-card selected" : "take-card"} onClick={() => chooseTake(take.take_no)}>
              <span className="take-card-no">Take {take.take_no}</span>
              <span className="take-badges"><b>PROXY</b><b>{take.fps ? `${Math.round(take.fps)} FPS` : "FPS UNMEASURED"}</b></span>
              <span className="take-score">{compared ? <>{Math.round(take.score * 100)} <small>technical</small></> : <small>not compared</small>}</span>
              {/* "Clean" and "not looked at yet" drew identically. */}
              <span className={issueCount ? "issue-count" : stage === "completed" ? "issue-count clean" : "issue-count pending"}>{issueCount ? `${issueCount} issue${issueCount === 1 ? "" : "s"}` : stage === "completed" ? "clean" : stageLabel(stage)}</span>
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
              <button className="lane-label" onClick={() => chooseTake(take.take_no)}>T{take.take_no}<small>{tc(take.duration_s)}</small></button>
              <div className="lane-track">
                <span className="lane-empty" style={{ width: pct(take.duration_s) }} />
                {safe.map((item, index) => <button key={`safe-${index}`} className="lane-safe" style={{ left: pct(item.start_s), width: pct(item.end_s - item.start_s) }} onClick={() => activePlayer(take.clip_id)?.seek(item.start_s, true)} title={`Clean ${tc(item.start_s)}–${tc(item.end_s)}`} />)}
                {findings.map((finding) => <button key={String(finding.finding_id)} className={`lane-finding severity-${finding.severity}${focus && String(focus.finding.finding_id) === String(finding.finding_id) ? " open" : ""}`} style={{ left: pct(finding.start_s), width: pct(Math.max(.4, finding.end_s - finding.start_s)) }} onClick={() => inspect(take.clip_id, finding)} title={`${label(finding.code)} ${tc(finding.start_s)}–${tc(finding.end_s)}`}><span>{label(finding.code)}</span></button>)}
              </div>
            </div>;
          })}
        </section>

        {/* Beneath the clock it belongs to. This sat in the right-hand column,
            so the bar showing where the issues are and the list naming them
            were on opposite sides of the screen and only one of them could be
            read at a time. */}
        <section className="finding-list-panel">
          <header><p className="eyebrow">ISSUES ON THIS SHOT</p><span>{openFindings.length} to verify</span></header>
            <div className="finding-list">
            {/* Tabs per take rather than every take's issues stacked. Two takes
                already filled the panel; six would have been a page of its own. */}
            <div className="finding-tabs" role="tablist">
              {takes.map((take) => {
                const count = openFindings.filter(({ analysis }) => String(analysis.clip_id) === take.clip_id).length;
                return <button
                  key={take.clip_id}
                  role="tab"
                  aria-selected={take.take_no === issueTab}
                  className={take.take_no === issueTab ? "finding-tab on" : "finding-tab"}
                  onClick={() => setIssueTab(take.take_no)}
                >Take {take.take_no}<span>{count}</span></button>;
              })}
            </div>
            {(() => {
              const rows = openFindings.filter(({ analysis }) => {
                const take = takes.find((t) => t.clip_id === String(analysis.clip_id));
                return take?.take_no === issueTab;
              });
              if (!rows.length) return <p className="empty-panel">No issues on take {issueTab}.</p>;
              return rows.map(({ analysis, finding }) => <button key={String(finding.finding_id)} className={focus && String(focus.finding.finding_id) === String(finding.finding_id) ? "open" : ""} onClick={() => inspect(String(analysis.clip_id), finding)}><span className={`finding-dot severity-${finding.severity}`} /><span><b>{tc(finding.start_s)}–{tc(finding.end_s)} {label(finding.code)}</b><small>{finding.detail}</small></span><i>›</i></button>);
            })()}
          </div>
        </section>
      </section>

      <aside className="cockpit-inspector">
        {/* Shown *above* the shot's own controls, never instead of them. It
            used to replace the entire column, so opening an issue took away
            Add range, Shot selects and every way back — and nothing closed it:
            not the shot, not Escape, not clicking the issue again. */}
        {focus && (
          <FindingInspector focus={focus} onClose={() => { setFocus(null); setAdjusting(false); }} take={takes.find((take) => take.clip_id === focus.clipId)} adjusting={adjusting} setAdjusting={setAdjusting} onChange={(start, end) => setFocus({ ...focus, finding: { ...focus.finding, start_s: start, end_s: end } })} onConfirm={() => void act("confirm")} onDismiss={() => void act("dismiss")} onCorrect={(detail, severity) => void act("correct", { detail, severity })} onAdjust={() => void act("adjust_range")} pending={findingAction.isPending} canAct={canComment} />
        )}
        <>
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
                <div><h2>{takes.length === 1 ? "One take — nothing to compare" : `${takes.length} takes, not compared`}</h2><p>{takes.length === 1 ? "Cut the ranges you want." : "Compare them, or cut ranges yourself."}</p></div>
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
              {/* Reusing a clip from another shot is parked, not removed: a
                  shot's ranges should come from that shot, and this invited
                  the opposite. The commands behind it (`addSource`,
                  `findSources`, /review/{p}/sources) are untouched and the
                  markup is preserved verbatim, so restoring it is deleting
                  this comment.

                  <details className="source-library"><summary>Reuse footage from another shot or scene</summary><p className="policy-note">Adds a source range here without changing where its slate placed the clip.</p><div className="source-search"><input value={sourceQuery} onChange={(event) => setSourceQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void findSources(); }} placeholder="Scene, shot, description or clip ID"/><button className="ghost" disabled={sourceBusy} onClick={() => void findSources()}>{sourceBusy ? "Finding…" : "Find"}</button></div>{sourcePreview?.proxy_uri && <Player className="source-preview" src={sourcePreview.proxy_uri} poster={sourcePreview.sprite_uri} />}{sourceRows.map((source) => <div className="source-row" key={source.clip_id}><button className="source-ident" onClick={() => setSourcePreview(source)}><b>Scene {source.scene_code || source.scene} · Shot {source.shot_code || source.shot} · Take {source.take_no}</b><small>{tc(source.duration_s)}{source.description ? ` · ${source.description}` : ""}</small></button><button className="ghost" disabled={!canComment} onClick={() => addSource(source)}>Add range</button></div>)}</details>
              */}
              {previewSegment && previewSource?.proxy_uri && <div className="shot-select-preview"><Player ref={selectPlayer} src={previewSource.proxy_uri} poster={previewSource.sprite_uri} onReady={() => selectPlayer.current?.seek(previewSegment.source_in_s, true)} onTimeUpdate={(at) => { if (at >= previewSegment.source_out_s - .05) setSelectPreviewIndex((index) => index !== null && index + 1 < selects.length ? index + 1 : null); }} /><small>Playing select {(selectPreviewIndex ?? 0) + 1} of {selects.length} · Take {previewSegment.take_no} · {tc(previewSegment.source_in_s)}–{tc(previewSegment.source_out_s)}</small></div>}
              <button className="ghost cockpit-confirm" disabled={!selects.length} onClick={() => setSelectPreviewIndex(0)}>▶ Play this shot</button>
              <button className="primary cockpit-confirm" disabled={!canComment || saveCoverage.isPending || !dirty} onClick={() => void saveSelects()}>{saveCoverage.isPending ? "Saving…" : !dirty ? (selects.length ? `✓ ${selects.length} range${selects.length === 1 ? "" : "s"} saved` : "Nothing to save") : `Save ${selects.length} shot select${selects.length === 1 ? "" : "s"}`}</button>
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
          </>
        </>
        {notice && <p className="cockpit-notice">{notice}</p>}
        {canComment && selected && <button className="ghost note-at-playhead" onClick={() => setCommentAt({ clipId: selected.clip_id, at: selectedAt })}>＋ Add note at {tc(selectedAt)}</button>}
        <Comments hideOwnTrigger projectId={projectId} scene={scene} shot={shot} canComment={canComment} comments={screen.data?.comments ?? []} takes={takes.map((take) => ({ clip_id: take.clip_id, take_no: take.take_no }))} pending={commentAt} onConsumedPending={() => setCommentAt(null)} />
      </aside>
    </div>
  );
}

function FindingInspector({ focus, take, adjusting, setAdjusting, onChange, onConfirm, onDismiss, onCorrect, onAdjust, pending, canAct, onClose }: { focus: Focus; onClose: () => void; take?: Take; adjusting: boolean; setAdjusting: (value: boolean) => void; onChange: (start: number, end: number) => void; onConfirm: () => void; onDismiss: () => void; onCorrect: (detail: string, severity: "note" | "attention" | "blocking") => void; onAdjust: () => void; pending: boolean; canAct: boolean }) {
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
    <header className="finding-inspector-head">
      <p className="eyebrow">FINDING · TAKE {take?.take_no ?? "—"}</p>
      <button type="button" className="finding-close" onClick={onClose} aria-label="Close this finding">
        ✕ Close
      </button>
    </header>
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
    {/* Two controls with nearly the same name do two unrelated things, and the
        only way to tell was to press one. */}
    <p className="policy-note">
      This corrects <b>where the problem is</b> — it moves the issue&rsquo;s own
      timecodes, and changes no footage. Choosing which parts of a take you
      actually use is <b>Add range</b>, under Shot selects.
    </p>
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
      <p className="policy-note">Claiming hides it from everyone else&apos;s queue. Approved closes it.</p>
    </div>
  );
}
