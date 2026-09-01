"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Comments from "@/components/Comments";
import Player, { type PlayerHandle } from "@/components/Player";
import type { FindingEvent, Take, TakeAnalysis } from "@/lib/api";
import {
  conflictMessage,
  useChooseTake,
  useFindingAction,
  useJudge,
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
  const takes = verdicts?.takes ?? [];
  const recommended = takes.find((take) => take.clip_id === verdicts?.recommended) ?? takes[0];
  const [aId, setAId] = useState("");
  const [bId, setBId] = useState("");
  const [activeSide, setActiveSide] = useState<"a" | "b">("a");
  const [focus, setFocus] = useState<Focus | null>(null);
  const [range, setRange] = useState<Range>({ from: 0, to: 0 });
  const [reason, setReason] = useState<string>("better performance");
  const [notice, setNotice] = useState("");
  const [adjusting, setAdjusting] = useState(false);
  const [commentAt, setCommentAt] = useState<{ clipId: string; at: number } | null>(null);
  const [playheads, setPlayheads] = useState<Record<string, number>>({});
  const playerA = useRef<PlayerHandle>(null);
  const playerB = useRef<PlayerHandle>(null);

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
  const choose = useChooseTake(projectId, scene, shot, verdicts?.rev ?? 0);
  const findingAction = useFindingAction(projectId, scene, shot);
  const judge = useJudge(projectId, scene, shot);
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

  const selectTake = async () => {
    if (!selected) return;
    try {
      await choose.mutateAsync({
        clip_id: selected.clip_id,
        reason: selected.clip_id === verdicts?.recommended ? "confirmed the technical recommendation" : reason,
        in_point_s: range.from,
        out_point_s: range.to,
      });
      setNotice(`Take ${selected.take_no} now stands for this shot.`);
    } catch (error) {
      setNotice(conflictMessage(error) ?? (error instanceof Error ? error.message : "Could not select that take."));
    }
  };

  if (screen.isPending) return <div className="cockpit-state">Loading shot intelligence…</div>;
  if (screen.isError) return <div className="cockpit-state error">Could not load this shot. <button onClick={() => void screen.refetch()}>Retry</button></div>;
  if (!verdicts || !takes.length) return <div className="cockpit-state"><div><p>No takes have been compared for this shot yet.</p>{canCurate && <button className="primary" disabled={judge.isPending} onClick={() => void judge.mutateAsync()}>{judge.isPending ? "Comparing full takes…" : "Analyse & compare takes"}</button>}</div></div>;

  const humanChoiceRecorded = verdicts.rev > 0 || takes.some(
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

        <div className="compare-toolbar" aria-label="A B comparison">
          <label>A<select value={a?.clip_id} onChange={(event) => { setAId(event.target.value); setActiveSide("a"); }}>
            {takes.map((take) => <option key={take.clip_id} value={take.clip_id}>Take {take.take_no}</option>)}
          </select></label>
          <button className={activeSide === "a" ? "compare-side on" : "compare-side"} onClick={() => setActiveSide("a")}>Listen to A</button>
          <span className="compare-vs">A / B</span>
          <button className={activeSide === "b" ? "compare-side on" : "compare-side"} onClick={() => setActiveSide("b")}>Listen to B</button>
          <label>B<select value={b?.clip_id} onChange={(event) => { setBId(event.target.value); setActiveSide("b"); }}>
            {takes.map((take) => <option key={take.clip_id} value={take.clip_id}>Take {take.take_no}</option>)}
          </select></label>
        </div>

        <div className="compare-players">
          {[{ side: "a" as const, take: a, ref: playerA }, { side: "b" as const, take: b, ref: playerB }].map(({ side, take, ref }) => take && (
            <div key={side} className={activeSide === side ? "compare-player active" : "compare-player"} onClick={() => setActiveSide(side)}>
              <span className="player-badge">{side.toUpperCase()} · TAKE {take.take_no}</span>
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
              <span className="take-score">{Math.round(take.score * 100)} <small>technical</small></span>
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
            <p className="eyebrow">AI RECOMMENDATION</p>
            <div className="recommendation">
              <span className="recommend-icon">✦</span>
              <div><h2>Take {recommended?.take_no} suggested</h2><p>{recommended?.reason || "Best observable technical coverage."}</p></div>
              <b>{recommended ? Math.round(recommended.score * 100) : 0}%</b>
            </div>
            <p className="policy-note">Technical, continuity and completion evidence only. Performance remains your decision.</p>
            {selected && <div className="selection-card">
              <h3>Your choice</h3>
              <div className="selection-take">Take {selected.take_no}<span>{selected.clip_id === recommended?.clip_id ? "AI suggestion" : "Alternative"}</span></div>
              <label>Use range<div className="range-inputs"><input type="number" step="0.01" min="0" max={selected.duration_s} value={range.from} onChange={(event) => setRange({ ...range, from: Number(event.target.value) })} /><span>→</span><input type="number" step="0.01" min="0" max={selected.duration_s} value={range.to} onChange={(event) => setRange({ ...range, to: Number(event.target.value) })} /></div></label>
              {selected.clip_id !== recommended?.clip_id && <div className="reason-chips">{HUMAN_REASONS.map((item) => <button key={item} className={reason === item ? "chip on" : "chip"} onClick={() => setReason(item)}>{item}</button>)}</div>}
              <button className="primary cockpit-confirm" disabled={!canComment || choose.isPending || !(range.to > range.from)} onClick={() => void selectTake()}>{canComment ? (selected.clip_id === recommended?.clip_id ? `Confirm Take ${selected.take_no}` : "Modify & Select") : "Sign in to select a take"}</button>
            </div>}
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
