"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Comments from "@/components/Comments";
import Player, { type PlayerHandle } from "@/components/Player";
import ShotBrief from "@/components/ShotBrief";
import ReviewedRanges from "@/components/ReviewedRanges";
import { draggedRange, rangeDragBounds, type TimelineDrag } from "@/lib/timeline-drag";
import { useQuery } from "@tanstack/react-query";
import {
  api,
  type CoverageSegment,
  type FindingEvent,
  type SourceClip,
  type Take,
  type TakeAnalysis,
} from "@/lib/api";
import {
  conflictMessage,
  useSaveCoverage,
  useFindingAction,
  useJudge,
  useShotEdits,
  useShotScreen,
} from "@/lib/queries";

type Range = { from: number; to: number };
type SegmentDrag = TimelineDrag & {
  id: string;
  clipId: string;
  pointerId: number;
};
type Focus = { clipId: string; finding: FindingEvent };
const findingKey = (clipId: string, findingId: string) => `${clipId}:${findingId}`;
const selectionSignature = (rows: CoverageSegment[]) =>
  JSON.stringify(
    rows.map((row) => [
      row.clip_id,
      row.source_in_s,
      row.source_out_s,
      row.reason,
      row.attempt_id ?? null,
      row.attempt_revision ?? 0,
    ]),
  );

function revalidateSelections(
  rows: CoverageSegment[],
  clipId: string,
  valid: Range[],
): CoverageSegment[] {
  return rows.flatMap((row) => {
    if (row.clip_id !== clipId) return [row];
    return valid
      .map((candidate) => ({
        from: Math.max(row.source_in_s, candidate.from),
        to: Math.min(row.source_out_s, candidate.to),
      }))
      .filter((candidate) => candidate.to > candidate.from)
      .map((candidate, index) => ({
        ...row,
        segment_id: index ? crypto.randomUUID() : row.segment_id,
        source_in_s: candidate.from,
        source_out_s: candidate.to,
      }));
  });
}

function withinRanges(range: Range, valid: Range[]): Range[] {
  return valid
    .map((candidate) => ({
      from: Math.max(range.from, candidate.from),
      to: Math.min(range.to, candidate.to),
    }))
    .filter((candidate) => candidate.to > candidate.from);
}

function subtractRanges(range: Range, blocked: Range[]): Range[] {
  let pieces = [range];
  for (const occupied of blocked) {
    pieces = pieces.flatMap((piece) => {
      if (occupied.to <= piece.from || occupied.from >= piece.to) return [piece];
      return [
        { from: piece.from, to: Math.min(piece.to, occupied.from) },
        { from: Math.max(piece.from, occupied.to), to: piece.to },
      ].filter((item) => item.to - item.from >= 0.05);
    });
  }
  return pieces;
}

function rangesOutsideIssues(
  duration: number,
  findings: FindingEvent[],
): Range[] {
  const blocked = findings
    .filter(
      (finding) =>
        finding.action !== "human_dismissed" &&
        !(
          finding.action === "human_retracted" &&
          finding.restored_action === "human_dismissed"
        ),
    )
    .map((finding) => ({
      from: Math.max(0, finding.start_s),
      to: Math.min(duration, finding.end_s),
    }))
    .filter((range) => range.to > range.from)
    .sort((a, b) => a.from - b.from || a.to - b.to)
    .reduce<Range[]>((merged, range) => {
      const previous = merged.at(-1);
      if (previous && range.from <= previous.to) {
        previous.to = Math.max(previous.to, range.to);
        return merged;
      }
      return [...merged, { ...range }];
    }, []);
  const available: Range[] = [];
  let cursor = 0;
  for (const issue of blocked) {
    if (issue.from > cursor) available.push({ from: cursor, to: issue.from });
    cursor = Math.max(cursor, issue.to);
  }
  if (cursor < duration) available.push({ from: cursor, to: duration });
  return available;
}

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
  return code
    .replaceAll(".", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function takeName(take: Take) {
  return take.take_no > 0
    ? `Take ${take.take_no}`
    : `Unnumbered · ${take.filename || take.clip_id.slice(0, 8)}`;
}

function persistedSegmentId(value: string): string | undefined {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    value,
  )
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
  focusTake = 0,
  reviewingClipId = "",
  onReviewingChange,
  sceneLabel = "",
  shotLabel = "",
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
  reviewingClipId?: string;
  onReviewingChange: (clipId: string, takeNo: number) => void;
  /** Canonical production identity; numeric route ids remain storage keys. */
  sceneLabel?: string;
  shotLabel?: string;
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
    ? (takes.find((take) => take.clip_id === verdicts?.recommended) ?? takes[0])
    : undefined;
  const setAId = (clipId: string) => {
    const take = takes.find((item) => item.clip_id === clipId);
    if (take) onReviewingChange(clipId, take.take_no);
  };
  const [focus, setFocus] = useState<Focus | null>(null);
  const [bulkReview, setBulkReview] = useState(false);
  const [bulkFindingKeys, setBulkFindingKeys] = useState<Set<string>>(new Set());
  const [bulkFindingCode, setBulkFindingCode] = useState("");
  const [reviewFilter, setReviewFilter] = useState("unresolved");
  const [issueClipId, setIssueClipId] = useState("");
  const activeReviewerId =
    reviewingClipId ||
    (focusTake ? takes.find((take) => take.take_no === focusTake)?.clip_id : "") ||
    initialClipId ||
    takes[0]?.clip_id ||
    "";
  const [inspectorTab, setInspectorTab] = useState<
    "finding" | "selects" | "shot"
  >("selects");
  const findingsForReview = useMemo(
    () =>
      analyses.flatMap((analysis) => {
        const current = new Map(
          analysis.findings.map((f) => [String(f.finding_id), f]),
        );
        const latest = new Map<string, FindingEvent>();
        for (const event of [...analysis.history].sort(
          (a, b) => a.revision - b.revision,
        )) {
          if (analysis.run && event.run_id !== analysis.run.run_id) continue;
          latest.set(String(event.finding_id), event);
        }
        for (const event of latest.values()) {
          if (
            (event.action === "human_dismissed" ||
              (event.action === "human_retracted" &&
                event.restored_action === "human_dismissed")) &&
            !current.has(String(event.finding_id))
          )
            current.set(String(event.finding_id), {
              ...event,
              action: "human_dismissed",
            });
        }
        return [...current.values()].map((finding) => ({ analysis, finding }));
      }),
    [analyses],
  );
  useEffect(() => {
    // Bulk review belongs to the take currently being reviewed, never the
    // comparison/reference take.
    setBulkFindingKeys(new Set());
    setBulkFindingCode("");
  }, [activeReviewerId]);
  useEffect(() => {
    setFocus((old) => {
      if (!old) return old;
      const latest = findingsForReview.find(
        (item) =>
          item.analysis.clip_id === old.clipId &&
          item.finding.finding_id === old.finding.finding_id,
      )?.finding;
      return latest && latest.revision > old.finding.revision
        ? { ...old, finding: latest }
        : old;
    });
  }, [findingsForReview]);
  const [range, setRange] = useState<Range>({ from: 0, to: 0 });
  const [cleanCandidate, setCleanCandidate] = useState<Range | null>(null);
  const pendingRange = useRef<{ clipId: string; range: Range } | null>(null);
  const reviewRange = useRef<{ clipId: string; end: number; segmentId?: string } | null>(null);
  const coverageBase = useRef<string | null>(null);
  const selectsRef = useRef<CoverageSegment[]>([]);
  const [selectsInitialized, setSelectsInitialized] = useState(false);
  const [recoverableSelects, setRecoverableSelects] = useState<{
    rows: CoverageSegment[];
    baseline: string;
  } | null>(null);
  const draftLoaded = useRef(false);
  const selectsDraftKey = `trimbin.shot-draft.${you}.${projectId}.${scene}.${shot}`;
  function clearSelectsDraft() {
    try {
      localStorage.removeItem(selectsDraftKey);
    } catch {
      /* optional recovery */
    }
    setRecoverableSelects(null);
  }
  const [reason, setReason] = useState<string>("better performance");
  const [notice, setNotice] = useState("");
  const [removedClip, setRemovedClip] = useState<{
    id: string;
    name: string;
  } | null>(null);
  const [adjusting, setAdjusting] = useState(false);
  const [sourceQuery, setSourceQuery] = useState("");
  const [sourceRows, setSourceRows] = useState<SourceClip[]>([]);
  const [sourcePreview, setSourcePreview] = useState<SourceClip | null>(null);
  const [sourceBusy, setSourceBusy] = useState(false);
  const [commentAt, setCommentAt] = useState<{
    clipId: string;
    at: number;
  } | null>(null);
  const [playheads, setPlayheads] = useState<Record<string, number>>({});
  const [playingClipId, setPlayingClipId] = useState("");
  const playerA = useRef<PlayerHandle>(null);
  const playerB = useRef<PlayerHandle>(null);
  const selectPlayer = useRef<PlayerHandle>(null);
  const pendingSeek = useRef<{
    clipId: string;
    at: number;
    play: boolean;
  } | null>(null);
  const initialSeekKey = useRef("");
  const [referenceId, setReferenceId] = useState("");
  const [workspaceMode, setWorkspaceMode] = useState<"inspect" | "compare">(
    "inspect",
  );
  useEffect(() => {
    if (takes.length < 2) setWorkspaceMode("inspect");
  }, [takes.length]);


  useEffect(() => {
    if (!initialClipId || !takes.some((take) => take.clip_id === initialClipId))
      return;
    const key = `${initialClipId}/${initialAt}`;
    if (initialSeekKey.current === key) return;
    initialSeekKey.current = key;
    previewMoment(initialClipId, initialAt);
  }, [initialAt, initialClipId, takes]);

  // Source preview and reference are separate from confirmed editorial choices.
  const chosen = takes.find((take) => take.clip_id === reviewingClipId)
    ?? takes.find((take) => take.take_no === focusTake)
    ?? takes.find((take) => take.clip_id === initialClipId)
    ?? takes[0];
  useEffect(() => {
    if (chosen && chosen.clip_id !== reviewingClipId)
      onReviewingChange(chosen.clip_id, chosen.take_no);
  }, [chosen?.clip_id, reviewingClipId]);
  const chosenIndex = takes.findIndex(
    (take) => take.clip_id === chosen?.clip_id,
  );
  const previous =
    takes.find(
      (take) =>
        take.clip_id === referenceId && take.clip_id !== chosen?.clip_id,
    ) ??
    (chosenIndex > 0
      ? takes[chosenIndex - 1]
      : takes.find((take) => take.clip_id !== chosen?.clip_id));
  const chooseTake = (
    clipId: string,
    preview?: { at: number; end: number },
  ) => {
    reviewRange.current = preview ? { clipId, end: preview.end } : null;
    pendingRange.current = null;
    const wanted = takes.find((take) => take.clip_id === clipId);
    if (!wanted) return;
    const keepPlaying = [playerA.current, playerB.current].some((handle) => {
      const video = handle?.element();
      return Boolean(video && !video.paused && !video.ended);
    });
    pendingSeek.current = {
      clipId: wanted.clip_id,
      at: preview?.at ?? playheads[wanted.clip_id] ?? 0,
      play: preview ? true : keepPlaying,
    };
    setAId(wanted.clip_id);
  };
  const a = chosen;
  const b = previous;
  const showComparison = workspaceMode === "compare" && Boolean(previous);
  const selected = chosen;
  const cleanRanges = useQuery({
    queryKey: ["project", projectId, "attempts", selected?.clip_id ?? ""],
    queryFn: () => api.attempts(projectId, selected!.clip_id),
    enabled: Boolean(selected),
  });
  const selectedAnalysis = selected
    ? analysisFor(analyses, selected.clip_id)
    : undefined;
  // The brief's revision, which is the shot document's revision — the same one
  // `commit_coverage` checks. `verdicts.rev` is a copy of it and is null when
  // nothing has been compared, so on a one-take shot this sent 0 forever: the
  // first save succeeded, bumped the shot to rev 1, and every save after it
  // was refused as a stale write.
  const saveCoverage = useSaveCoverage(
    projectId,
    scene,
    shot,
    screen.data?.brief.rev ?? 0,
  );
  const [selects, setSelects] = useState<CoverageSegment[]>([]);
  const segmentDrag = useRef<SegmentDrag | null>(null);
  selectsRef.current = selects;

  const segmentBounds = (segment: CoverageSegment, rows: CoverageSegment[]) => {
    const take = takes.find((item) => item.clip_id === segment.clip_id);
    const analysis = analysisFor(analyses, segment.clip_id);
    const safe = take && analysis
      ? rangesOutsideIssues(take.duration_s, analysis.findings)
      : [{ from: 0, to: take?.duration_s ?? segment.source_out_s }];
    const others = rows.filter(
      (item) => item.segment_id !== segment.segment_id && item.clip_id === segment.clip_id,
    );
    return rangeDragBounds(
      { from: segment.source_in_s, to: segment.source_out_s }, safe,
      others.map((item) => ({ from: item.source_in_s, to: item.source_out_s })),
    );
  };

  useEffect(() => {
    const move = (event: PointerEvent) => {
      const drag = segmentDrag.current;
      if (!drag || event.pointerId !== drag.pointerId) return;
      const next = draggedRange(drag, event.clientX);
      setSelects((rows) => rows.map((row) => row.segment_id === drag.id
        ? { ...row, source_in_s: next.from, source_out_s: next.to }
        : row));
      setRange(next);
      previewMoment(drag.clipId, next.from, next.to);
    };
    const up = () => { segmentDrag.current = null; };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    window.addEventListener("blur", up);
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); window.removeEventListener("pointercancel", up); window.removeEventListener("blur", up); };
  }, [analyses, takes]);
  const [selectPreviewIndex, setSelectPreviewIndex] = useState<number | null>(
    null,
  );
  const findingAction = useFindingAction(projectId, scene, shot);
  const judge = useJudge(projectId, scene, shot);
  const edits = useShotEdits(projectId, scene, shot, screen.data?.brief);
  const duration = Math.max(1, ...takes.map((take) => take.duration_s || 0));
  const pct = (value: number) =>
    `${Math.min(100, Math.max(0, (value / duration) * 100))}%`;

  useEffect(() => {
    if (!selected) return;
    const analysis = analysisFor(analyses, selected.clip_id);
    const primary = analysis?.primary_usable_range;
    setRange(
      (pendingRange.current?.clipId === selected.clip_id
        ? pendingRange.current.range
        : null) ?? {
        from: primary?.start_s ?? selected.usable_from_s ?? 0,
        to: primary?.end_s ?? selected.usable_to_s ?? selected.duration_s,
      },
    );
    pendingRange.current = null;
  }, [selected?.clip_id]);

  useEffect(() => {
    // From the shot, not from a comparison it may never have had. Reading this
    // off `verdicts` meant every saved range vanished on refresh for any shot
    // with fewer than two takes — saved correctly, then never asked for.
    if (!screen.data) return;
    const incoming = (screen.data.coverage_segments ?? []).map(
      (item, position) => ({
        ...item,
        position,
      }),
    );
    const sanitized = incoming.flatMap((item) => {
      const analysis = analyses.find(
        (candidate) => String(candidate.clip_id) === item.clip_id,
      );
      const take = takes.find((candidate) => candidate.clip_id === item.clip_id);
      const safe = analysis
        ? rangesOutsideIssues(take?.duration_s ?? item.source_out_s, analysis.findings)
        : (take?.safe_ranges ?? []).map((range) => ({
            from: range.start_s,
            to: range.end_s,
          }));
      return analysis || safe.length
        ? revalidateSelections(
            [item],
            item.clip_id,
            safe,
          )
        : [item];
    });
    const accepted: CoverageSegment[] = [];
    for (const item of sanitized) {
      const occupied = accepted
        .filter((row) => row.clip_id === item.clip_id)
        .map((row) => ({ from: row.source_in_s, to: row.source_out_s }));
      for (const piece of subtractRanges(
        { from: item.source_in_s, to: item.source_out_s },
        occupied,
      )) {
        accepted.push({
          ...item,
          segment_id:
            piece.from === item.source_in_s ? item.segment_id : crypto.randomUUID(),
          source_in_s: piece.from,
          source_out_s: piece.to,
          position: accepted.length,
        });
      }
    }
    if (
      coverageBase.current !== null &&
      coverageBase.current !== selectionSignature(selectsRef.current)
    )
      return;
    coverageBase.current = selectionSignature(incoming);
    setSelects(accepted);
    if (selectionSignature(accepted) !== selectionSignature(incoming))
      setNotice("Overlapping issue or select areas were removed. Review the adjusted ranges, then save.");
    setSelectsInitialized(true);
  }, [screen.data?.coverage_segments]);

  // Every open finding across every take, flattened once so the count in the
  // header and the rows beneath it cannot disagree.
  const openFindings = useMemo(
    () =>
      analyses.flatMap((analysis) =>
        analysis.findings
          .filter((finding) => finding.action === "machine_open")
          .map((finding) => ({ analysis, finding })),
      ),
    [analyses],
  );
  const verifiedFindings = useMemo(
    () =>
      findingsForReview.filter(
        ({ finding }) => finding.action !== "machine_open",
      ).length,
    [findingsForReview],
  );

  // Escape closes the finding. It was the first thing tried and did nothing.
  useEffect(() => {
    if (!focus) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setFocus(null);
        setAdjusting(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focus]);

  // Whether the tray differs from what is stored. The Save button stayed lit
  // after a successful save, so the only way to know whether a change had been
  // written was to reload and look.
  const savedSelects = screen.data?.coverage_segments ?? [];
  const dirty = useMemo(() => {
    return (
      selectionSignature(selects) !==
      selectionSignature(savedSelects as CoverageSegment[])
    );
  }, [selects, savedSelects]);
  useEffect(() => {
    if (!selectsInitialized || draftLoaded.current) return;
    draftLoaded.current = true;
    try {
      const stored = JSON.parse(
        localStorage.getItem(selectsDraftKey) || "null",
      );
      if (
        stored &&
        typeof stored.baseline === "string" &&
        Array.isArray(stored.rows) &&
        stored.rows.length <= 200 &&
        stored.rows.every(
          (row: CoverageSegment) =>
            typeof row.clip_id === "string" &&
            Number.isFinite(row.source_in_s) &&
            Number.isFinite(row.source_out_s),
        )
      ) {
        if (
          selectionSignature(stored.rows) !==
          selectionSignature(savedSelects as CoverageSegment[])
        )
          setRecoverableSelects(stored);
        else clearSelectsDraft();
      }
    } catch {
      /* Invalid recovery data cannot replace server state. */
    }
  }, [selectsInitialized]);
  useEffect(() => {
    if (!selectsInitialized || !dirty) return;
    try {
      localStorage.setItem(
        selectsDraftKey,
        JSON.stringify({ rows: selects, baseline: coverageBase.current }),
      );
    } catch {
      /* Explicit save stays available. */
    }
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [selectsInitialized, dirty, selects]);

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

  const issueTab = issueClipId || chosen?.clip_id || "";
  useEffect(() => setIssueClipId(chosen?.clip_id ?? ""), [chosen?.clip_id]);

  // The shot's standing decision, in one phrase.
  //
  // A shot used to have one winning take, so "Take 4" said everything. Ranges
  // from several takes have no single winner, and calling that "Take 4"
  // because take 4 happened to be first would be a lie about what plays.
  const standing = useMemo(() => {
    if (!selects.length) return "";
    const used = Array.from(new Set(selects.map((item) => item.take_no))).sort(
      (x, y) => x - y,
    );
    const ranges = `${selects.length} range${selects.length === 1 ? "" : "s"}`;
    if (used.length === 1) return `Take ${used[0]} · ${ranges}`;
    return `Custom · ${ranges} from take${used.length === 1 ? "" : "s"} ${used.join(", ")}`;
  }, [selects]);

  // A take picked in the rail opens on the A side, swapping B out of the way
  // if it was already showing it.

  const activePlayer = (clipId: string) =>
    clipId === a?.clip_id
      ? playerA.current
      : clipId === b?.clip_id
        ? playerB.current
        : null;
  function previewMoment(clipId: string, at: number, end?: number) {
    if (!takes.some((take) => take.clip_id === clipId)) return;
    pendingSeek.current = { clipId, at, play: true };
    reviewRange.current = end === undefined ? null : { clipId, end };
    playerA.current?.element()?.pause();
    playerB.current?.element()?.pause();
    const target = activePlayer(clipId);
    target?.seek(at, true);
    if ((target?.element()?.readyState ?? 0) >= 1) pendingSeek.current = null;
  }
  const inspect = (clipId: string, finding: FindingEvent) => {
    // A second click on the finding already open closes it — the same gesture
    // that opened it, which is what a person reaches for before they look for
    // a button.
    if (
      focus &&
      String(focus.finding.finding_id) === String(finding.finding_id)
    ) {
      setFocus(null);
      setAdjusting(false);
      return;
    }
    // An issue opened from the shot list is an instruction to review that take,
    // not to leave it parked as the reference. Carry the exact issue range
    // through the player swap, then play it in the Reviewing pane without
    // leaving an active comparison.
    if (clipId !== chosen?.clip_id) {
      chooseTake(clipId, { at: finding.start_s, end: finding.end_s });
    }
    setFocus({ clipId, finding });
    setInspectorTab("finding");
    if (clipId === chosen?.clip_id)
      previewMoment(clipId, finding.start_s, finding.end_s);
  };

  const toggleBulkFinding = (clipId: string, finding: FindingEvent) => {
    if (clipId !== activeReviewerId) {
      setNotice("Bulk issue review is limited to the take currently being reviewed.");
      return;
    }
    if (finding.action !== "machine_open") {
      setNotice("That issue has already been reviewed.");
      return;
    }
    const code = String(finding.code);
    if (bulkFindingCode && bulkFindingCode !== code) {
      setNotice(
        `Bulk review is limited to ${label(bulkFindingCode)}. Finish or cancel it first.`,
      );
      return;
    }
    const key = findingKey(clipId, String(finding.finding_id));
    setBulkFindingKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      if (!next.size) setBulkFindingCode("");
      else if (!bulkFindingCode) setBulkFindingCode(code);
      return next;
    });
  };

  const beginBulkReview = () => {
    const canSeed =
      focus?.clipId === activeReviewerId &&
      focus.finding.action === "machine_open";
    setBulkReview(true);
    setInspectorTab("finding");
    if (!canSeed) {
      setBulkFindingKeys(new Set());
      setBulkFindingCode("");
      setNotice("Choose one unresolved issue, then select matching issues from the timeline.");
      return;
    }
    setBulkFindingKeys(
      new Set([
        findingKey(focus.clipId, String(focus.finding.finding_id)),
      ]),
    );
    setBulkFindingCode(String(focus.finding.code));
    setNotice("Issue selected. Add the same issue type, or select all matching issues.");
  };

  const act = async (
    action: "confirm" | "dismiss" | "correct" | "adjust_range" | "retract",
    changes: {
      detail?: string;
      severity?: "note" | "attention" | "blocking";
    } = {},
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
            : action === "correct"
              ? changes
              : {}),
        },
      });
      setNotice(
        action === "dismiss"
          ? "Finding dismissed. Its history is preserved."
          : "Finding review recorded.",
      );
      const refreshed = await screen.refetch();
      const updated = refreshed.data?.analyses.find(
        (analysis) => String(analysis.clip_id) === focus.clipId,
      );
      if (updated) {
        const source = takes.find((take) => take.clip_id === focus.clipId);
        const valid = rangesOutsideIssues(
          source?.duration_s ?? focus.finding.end_s,
          updated.findings,
        );
        const nextSelects = revalidateSelections(
          selectsRef.current,
          focus.clipId,
          valid,
        );
        const clipped =
          selectionSignature(nextSelects) !==
          selectionSignature(selectsRef.current);
        setSelects(nextSelects);
        if (clipped)
          setNotice("The reviewed issue cropped the overlapping shot select. Save the updated range.");
      }
      const primary = updated?.primary_usable_range;
      if (primary)
        setRange({ from: primary.start_s, to: primary.end_s });
      setAdjusting(false);
    } catch (error) {
      setNotice(
        conflictMessage(error) ??
          (error instanceof Error
            ? error.message
            : "Could not record that review."),
      );
    }
  };

  const actOnBulkFindings = async (action: "confirm" | "dismiss") => {
    const selectedKeys = [...bulkFindingKeys];
    if (!selectedKeys.length || !activeReviewerId) return;
    const findingForKey = (
      data: typeof screen.data | undefined,
      key: string,
    ) =>
      data?.analyses
        .filter((analysis) => String(analysis.clip_id) === activeReviewerId)
        .flatMap((analysis) =>
          analysis.findings.map((finding) => ({ analysis, finding })),
        )
        .find(
          ({ analysis, finding }) =>
            finding.action === "machine_open" &&
            findingKey(
              String(analysis.clip_id),
              String(finding.finding_id),
            ) === key,
        );
    const initial = await screen.refetch();
    const failed = new Set<string>();
    let skipped = 0;
    let completed = 0;
    for (const key of selectedKeys) {
      let target = findingForKey(initial.data, key);
      if (!target) {
        skipped += 1;
        continue;
      }
      let { analysis, finding } = target;
      const clipId = String(analysis.clip_id);
      try {
        await findingAction.mutateAsync({
          clipId,
          findingId: String(finding.finding_id),
          body: { rev: finding.revision, action },
        });
        completed += 1;
      } catch {
        const retried = await screen.refetch();
        target = findingForKey(retried.data, key);
        if (!target) {
          skipped += 1;
          continue;
        }
        ({ analysis, finding } = target);
        try {
          await findingAction.mutateAsync({
            clipId: String(analysis.clip_id),
            findingId: String(finding.finding_id),
            body: { rev: finding.revision, action },
          });
          completed += 1;
        } catch {
          failed.add(key);
        }
      }
    }

    const refreshed = await screen.refetch();
    let selectionAdjusted = false;
    if (action === "confirm" && refreshed.data) {
      let adjusted = selectsRef.current;
      const clipIds = new Set([activeReviewerId]);
      for (const clipId of clipIds) {
        const updated = refreshed.data.analyses.find(
          (analysis) => String(analysis.clip_id) === clipId,
        );
        const source = takes.find((take) => take.clip_id === clipId);
        if (updated && source)
          adjusted = revalidateSelections(
            adjusted,
            clipId,
            rangesOutsideIssues(source.duration_s, updated.findings),
          );
      }
      selectionAdjusted =
        selectionSignature(adjusted) !== selectionSignature(selectsRef.current);
      if (selectionAdjusted) setSelects(adjusted);
    }

    setBulkFindingKeys(failed);
    if (!failed.size) {
      setBulkReview(false);
      setBulkFindingCode("");
      setFocus(null);
      setNotice(
        selectionAdjusted
          ? `${completed} issues accepted. Overlapping shot selects were adjusted; review and save them.`
          : `${completed} matching issues ${action === "confirm" ? "accepted" : "ignored"}.${skipped ? ` ${skipped} no longer needed review.` : " History is preserved."}`,
      );
    } else {
      setNotice(
        `${completed} issues updated. ${failed.size} could not be saved; they remain selected.`,
      );
    }
  };

  const addRange = () => {
    if (!selected) return;
    if (!(range.to > range.from)) return;
    const safe = selectedAnalysis
      ? rangesOutsideIssues(selected.duration_s, selectedAnalysis.findings)
      : (selected.safe_ranges ?? []).map((item) => ({
          from: item.start_s,
          to: item.end_s,
        }));
    const safePieces = selectedAnalysis
      ? withinRanges(range, safe)
      : safe.length
        ? withinRanges(range, safe)
        : [range];
    const occupied = selectsRef.current
      .filter((item) => item.clip_id === selected.clip_id)
      .map((item) => ({ from: item.source_in_s, to: item.source_out_s }));
    const pieces = safePieces.flatMap((piece) => subtractRanges(piece, occupied));
    if (!pieces.length) {
      setNotice("That range overlaps an issue and has no selectable portion.");
      return;
    }
    setSelects((current) => [
      ...current,
      ...pieces.map((piece, index) => ({
          segment_id: crypto.randomUUID(),
          clip_id: selected.clip_id,
          attempt_revision: 0,
          take_no: selected.take_no,
          source_in_s: piece.from,
          source_out_s: piece.to,
          position: current.length + index,
          reason,
          created_by: you,
          origin: "human" as const,
        })),
    ]);
    setNotice(
      `Take ${selected.take_no} ${tc(range.from)}–${tc(range.to)} added. Save the shot selects when ready.`,
    );
  };

  const promoteVerifiedClean = (from: number, to: number) => {
    if (!selected || !(to > from)) return;
    const analysis = analysisFor(analyses, selected.clip_id);
    const safe = analysis
      ? rangesOutsideIssues(selected.duration_s, analysis.findings)
      : selected.safe_ranges.map((item) => ({
          from: item.start_s,
          to: item.end_s,
        }));
    const verifiedPieces = withinRanges({ from, to }, safe);
    const occupied = selectsRef.current
      .filter((item) => item.clip_id === selected.clip_id)
      .map((item) => ({ from: item.source_in_s, to: item.source_out_s }));
    const pieces = verifiedPieces.flatMap((piece) => subtractRanges(piece, occupied));
    if (!pieces.length) {
      setNotice("This verified clean range is already selected or overlaps an issue.");
      return;
    }
    setSelects((current) => [
      ...current,
      ...pieces.map((piece, index) => ({
        segment_id: crypto.randomUUID(),
        clip_id: selected.clip_id,
        attempt_revision: 0,
        take_no: selected.take_no,
        source_in_s: piece.from,
        source_out_s: piece.to,
        position: current.length + index,
        reason: "verified clean range",
        created_by: you,
        origin: "human" as const,
      })),
    ]);
    setRange({ from, to });
    setCleanCandidate(null);
    setNotice("Verified clean range is now a shot select. Save the shot selects when ready.");
  };

  const updateSelectBoundary = (
    index: number,
    edge: "in" | "out",
    value: number,
  ) => {
    setSelects((rows) => {
      const item = rows[index];
      if (!item || !Number.isFinite(value)) return rows;
      const bounds = segmentBounds(item, rows);
      if (!bounds) return rows;
      const next = [...rows];
      next[index] = edge === "in"
        ? {
            ...item,
            source_in_s: Math.max(
              bounds.min,
              Math.min(value, item.source_out_s - 0.05),
            ),
          }
        : {
            ...item,
            source_out_s: Math.min(
              bounds.max,
              Math.max(value, item.source_in_s + 0.05),
            ),
          };
      return next;
    });
  };

  const constrainSelectionsToIssues = (rows: CoverageSegment[]) =>
    rows.flatMap((item) => {
      const analysis = analyses.find(
        (candidate) => String(candidate.clip_id) === item.clip_id,
      );
      if (!analysis) return [item];
      const source = takes.find((take) => take.clip_id === item.clip_id);
      return revalidateSelections(
        [item],
        item.clip_id,
        rangesOutsideIssues(
          source?.duration_s ?? item.source_out_s,
          analysis.findings,
        ),
      );
    });

  const saveSelects = async () => {
    try {
      const constrained = constrainSelectionsToIssues(selects);
      if (selectionSignature(constrained) !== selectionSignature(selects)) {
        setSelects(constrained);
        setNotice(
          "Issue ranges were removed from the shot selects. Review the split ranges, then save.",
        );
        return;
      }
      if (
        coverageBase.current !==
        selectionSignature(savedSelects as CoverageSegment[])
      )
        throw new Error(
          "Shot selects changed while you were editing. Reload saved selects before replacing another editor's changes.",
        );
      await saveCoverage.mutateAsync({
        reason: reason || "human coverage selection",
        segments: constrained.map((item) => ({
          segment_id: persistedSegmentId(item.segment_id),
          clip_id: item.clip_id,
          attempt_id: item.attempt_id,
          attempt_revision: item.attempt_revision ?? 0,
          source_in_s: item.source_in_s,
          source_out_s: item.source_out_s,
          reason: item.reason,
          origin: item.origin,
          created_by: item.created_by,
        })),
      });
      const refreshed = await screen.refetch();
      const next = refreshed.data?.coverage_segments ?? [];
      coverageBase.current = selectionSignature(next);
      setSelects(next);
      clearSelectsDraft();
      setNotice(
        `${selects.length} source range${selects.length === 1 ? "" : "s"} now stand for this shot.`,
      );
    } catch (error) {
      setNotice(
        conflictMessage(error) ??
          (error instanceof Error
            ? error.message
            : "Could not save shot selects."),
      );
    }
  };

  const previewSegment =
    selectPreviewIndex === null ? null : selects[selectPreviewIndex];
  const previewSource = previewSegment
    ? (takes.find((take) => take.clip_id === previewSegment.clip_id) ??
      sourceRows.find((source) => source.clip_id === previewSegment.clip_id))
    : null;

  const findSources = async () => {
    setSourceBusy(true);
    try {
      setSourceRows(await api.projectSources(projectId, sourceQuery));
    } catch (error) {
      setNotice(
        error instanceof Error
          ? error.message
          : "Could not search project footage.",
      );
    } finally {
      setSourceBusy(false);
    }
  };

  const addSource = (source: SourceClip) => {
    setSelects((current) => [
      ...current,
      {
        segment_id: crypto.randomUUID(),
        clip_id: source.clip_id,
        attempt_revision: 0,
        take_no: source.take_no,
        source_in_s: 0,
        source_out_s: source.duration_s,
        position: current.length,
        reason: "reused project source",
        created_by: you,
        origin: "human_reuse",
      },
    ]);
    setNotice(
      `Scene ${source.scene} / Shot ${source.shot} / Take ${source.take_no} added as a reusable source. Its slate placement did not move.`,
    );
  };

  if (screen.isPending)
    return <div className="cockpit-state">Loading shot intelligence…</div>;
  if (screen.isError)
    return (
      <div className="cockpit-state error">
        Could not load this shot.{" "}
        <button onClick={() => void screen.refetch()}>Retry</button>
      </div>
    );
  // Only a shot with no footage at all is empty. One take is a shot you can
  // watch, analyse and cut a range from; it is merely a shot nothing can be
  // compared against.
  if (!takes.length)
    return (
      <div className="cockpit-state">
        <div>
          <p>No footage has been placed in this shot yet.</p>
          <p className="policy-note">
            Upload takes, or move a clip here from the placement inbox.
          </p>
        </div>
      </div>
    );

  const humanChoiceRecorded =
    (verdicts?.rev ?? 0) > 0 ||
    selects.length > 0 ||
    takes.some(
      (take) => take.outcome === "selected" && take.decided_by === "human",
    );
  const noteClip =
    takes.find((take) => take.clip_id === playingClipId) ?? selected;
  const selectedAt = noteClip ? (playheads[noteClip.clip_id] ?? 0) : 0;

  return (
    <div className="shot-cockpit">
      <section className="cockpit-main">
        <header className="cockpit-titlebar">
          <div>
            <p className="eyebrow">SHOT REVIEW</p>
            <h1>
              Scene {sceneLabel || scene} / Shot{" "}
              {shotLabel || screen.data?.brief.slug || shot}
            </h1>
          </div>
          <div className="cockpit-summary">
            <span>{takes.length} takes</span>
            <span>
              {analyses.filter((item) => item.coverage_complete).length}/
              {takes.length} fully analysed
            </span>
            <span
              className={humanChoiceRecorded ? "live-dot complete" : "live-dot"}
              title={standing || undefined}
            >
              {standing || "No take chosen yet"}
            </span>
          </div>
        </header>
        <nav className="performance-actions" aria-label="Shot workspace mode">
          <button
            aria-pressed={workspaceMode === "inspect"}
            onClick={() => setWorkspaceMode("inspect")}
          >
            Inspect footage & issues
          </button>
          <div className="compare-toolbar" aria-label="Which take">
            <label className="reviewing-picker">Reviewing <select aria-label="Reviewing take"
              value={chosen?.clip_id ?? ""}
              disabled={takes.length < 2}
              onChange={(e) => chooseTake(e.target.value)}>
              {takes.map((take) => <option key={take.clip_id} value={take.clip_id}>{takeName(take)}</option>)}
            </select></label>
            {showComparison && previous && (
              <label className="compare-hint">
                Reference{" "}
                <select
                  aria-label="Compare against another take"
                  value={previous.clip_id}
                  onChange={(e) => setReferenceId(e.target.value)}
                >
                  {takes
                    .filter((take) => take.clip_id !== chosen?.clip_id)
                    .map((take) => (
                      <option key={take.clip_id} value={take.clip_id}>
                        {takeName(take)}
                      </option>
                    ))}
                </select>
              </label>
            )}
          </div>
          <button
            aria-pressed={workspaceMode === "compare"}
            onClick={() => setWorkspaceMode("compare")}
            disabled={takes.length < 2}
            title={
              takes.length < 2
                ? "Upload another take to compare performances."
                : undefined
            }
          >
            Compare performances
          </button>
        </nav>
        <div className="inspect-preview-group">

          <div
            className={showComparison ? "compare-players" : "compare-players single"}
          >
            {/* Inspect keeps the reviewing take alone. Comparison explicitly
                adds the reference player, so it never competes for space while
                findings and clean ranges are being reviewed. */}
            {(showComparison && previous
              ? [
                  { side: "a" as const, take: chosen, ref: playerA },
                  { side: "b" as const, take: previous, ref: playerB },
                ]
              : [{ side: "a" as const, take: chosen, ref: playerA }]
            ).map(
              ({ side, take, ref }) =>
                take && (
                  /* Choosing is the badge, not the frame. The whole panel used to
               carry the click, and it wraps a video — so pressing play on the
               left take, or scrubbing it, bubbled up and silently reassigned
               which take was chosen. You could not watch A without selecting
               it. A div is also not reachable by keyboard, so this was the
               only control here nobody could tab to. */
                  <div
                    key={side}
                    className={
                      take.clip_id === chosen?.clip_id
                        ? "compare-player active"
                        : "compare-player"
                    }
                  >
                    <button
                      type="button"
                      className="player-badge"
                      aria-pressed={take.clip_id === chosen?.clip_id}
                      onClick={() => chooseTake(take.clip_id)}
                      title={`Choose ${takeName(take)}`}
                    >
                      <small>{side === "a" ? "Reviewing" : "Reference"}</small>
                      <span>
                        {takeName(take).toUpperCase()}
                        <em>{tc(take.duration_s)}</em>
                      </span>
                    </button>
                    <Player
                      ref={ref}
                      className="player"
                      src={take.proxy_uri}
                      poster={take.sprite_uri}
                      onReady={() => {
                        const pending = pendingSeek.current;
                        if (pending?.clipId !== take.clip_id) return;
                        ref.current?.seek(pending.at, pending.play);
                        if ((ref.current?.element()?.readyState ?? 0) >= 1)
                          pendingSeek.current = null;
                      }}
                      onTimeUpdate={(at) => {
                        const bounded = reviewRange.current;
                        const live = selects.find((s) => s.segment_id === bounded?.segmentId);
                        const end = live?.source_out_s ?? bounded?.end;
                        if (bounded?.clipId === take.clip_id && end !== undefined && at >= end) {
                          ref.current?.element()?.pause();
                          ref.current?.seek(end);
                          reviewRange.current = null;
                        }
                        setPlayheads((current) => ({
                          ...current,
                          [take.clip_id]: at,
                        }));
                        if (take.clip_id === chosen?.clip_id)
                          setCommentAt((old) =>
                            old && old.clipId === take.clip_id
                              ? { ...old, at }
                              : old,
                          );
                      }}
                      onPlay={() => {
                        (ref === playerA ? playerB : playerA).current?.element()?.pause();
                        setPlayingClipId(take.clip_id);
                      }}
                    />
                    <div className="take-details">
                      <strong>{takeName(take)}</strong>
                      <span>
                        {take.proxy_uri ? "Proxy ready" : "Proxy unavailable"} ·{" "}
                        {take.fps
                          ? `${take.fps.toFixed(3).replace(/\.000$/, "")} fps`
                          : "FPS unmeasured"}{" "}
                        · {tc(take.duration_s)}
                      </span>
                      <span>
                        {analysisFor(analyses, take.clip_id)?.findings.filter(
                          (f) => f.action === "machine_open",
                        ).length ?? take.findings.length}{" "}
                        unresolved ·{" "}
                        {analysisFor(analyses, take.clip_id)?.findings.filter(
                          (f) => f.action !== "machine_open",
                        ).length ?? 0}{" "}
                        reviewed
                      </span>
                    </div>
                  </div>
                ),
            )}
          </div>

          {selected?.can_delete && (
            <div className="clip-lifecycle-actions">
              <span>This clip was uploaded by you.</span>
              <button
                className="ghost danger"
                onClick={async () => {
                  if (
                    !window.confirm(
                      "Remove this clip from current project views? The source remains recoverable.",
                    )
                  )
                    return;
                  const removed = {
                    id: selected.clip_id,
                    name: takeName(selected),
                  };
                  await api.removeClip(projectId, selected.clip_id);
                  setRemovedClip(removed);
                  setNotice(
                    `${removed.name} removed from current project views.`,
                  );
                  await screen.refetch();
                }}
              >
                Remove my clip
              </button>
            </div>
          )}
        </div>

        <section className="issue-lanes">
          <header>
            <div>
              <p className="eyebrow">
                TAKE ANALYSIS · USABLE RANGES &amp; ISSUES
              </p>
              <h2>{showComparison ? "Every take on one clock" : "Reviewing take on one clock"}</h2>
            </div>
            <div className="lane-header-actions">
              <div className="lane-legend">
                <span className="clean-key">Candidate usable</span>
                <span className="selected-key">Shot select</span>
                <span className="reviewed-clean-key">Reviewed clean</span>
                <span className="warn-key">Issue</span>
                <span className="slate-key">Slate / exit</span>
              </div>
              <div className="bulk-review-actions">
                {!bulkReview ? (
                  <button
                    disabled={!canComment}
                    onClick={beginBulkReview}
                  >
                    Select issues
                  </button>
                ) : (
                  <>
                    <span>{bulkFindingKeys.size} selected</span>
                    {bulkFindingCode && (
                      <button
                        onClick={() => {
                          const visible = new Set(
                            [chosen?.clip_id].filter(Boolean),
                          );
                          setBulkFindingKeys(
                            new Set(
                              findingsForReview
                                .filter(
                                  ({ analysis, finding }) =>
                                    visible.has(String(analysis.clip_id)) &&
                                    String(finding.code) === bulkFindingCode &&
                                    finding.action === "machine_open",
                                )
                                .map(({ analysis, finding }) =>
                                  findingKey(
                                    String(analysis.clip_id),
                                    String(finding.finding_id),
                                  ),
                                ),
                            ),
                          );
                        }}
                      >
                        All matching
                      </button>
                    )}
                    <button
                      disabled={!bulkFindingKeys.size || findingAction.isPending}
                      onClick={() => void actOnBulkFindings("confirm")}
                    >
                      Accept
                    </button>
                    <button
                      disabled={!bulkFindingKeys.size || findingAction.isPending}
                      onClick={() => void actOnBulkFindings("dismiss")}
                    >
                      Ignore
                    </button>
                    <button
                      onClick={() => {
                        setBulkReview(false);
                        setBulkFindingKeys(new Set());
                        setBulkFindingCode("");
                      }}
                    >
                      Cancel
                    </button>
                  </>
                )}
              </div>
            </div>
          </header>
          <div className="time-ruler">
            <span>00:00</span>
            <span>{tc(duration * 0.25)}</span>
            <span>{tc(duration * 0.5)}</span>
            <span>{tc(duration * 0.75)}</span>
            <span>{tc(duration)}</span>
          </div>
          {(showComparison ? [chosen, previous] : [chosen])
            .filter((take): take is Take => Boolean(take))
            .map((take) => {
            const analysis = analysisFor(analyses, take.clip_id);
            const findings = analysis?.findings ?? [];
            const markerEnds: number[] = [];
            const findingMarkers = [...findings]
              .sort((a, b) => a.start_s - b.start_s || a.end_s - b.end_s)
              .map((finding) => {
                let row = markerEnds.findIndex((end) => finding.start_s >= end);
                if (row < 0) row = markerEnds.length;
                markerEnds[row] = finding.end_s;
                return { finding, row };
              });
            // An in-progress analysis deliberately exposes no safe ranges. Keep
            // the last completed comparison suggestion visible until the new
            // run is complete, then replace it with the freshly issue-adjusted
            // clean portions.
            // Candidate bars use every current finding, including note-level
            // slate/exit evidence. Backend safe_ranges intentionally omits
            // some notes, but a Verify clean candidate must never cross any
            // visible issue.
            const safe = analysis
              ? rangesOutsideIssues(take.duration_s, findings)
              : take.safe_ranges.map((item) => ({
                  from: item.start_s,
                  to: item.end_s,
                }));
            const needsReview =
              take.clip_id === chosen?.clip_id &&
              (!screen.data?.decision_fresh ||
                !verdicts?.takes.some(
                  (item) => item.clip_id === take.clip_id,
                ));
            return (
              <div
                className={
                  `${selected?.clip_id === take.clip_id ? "issue-lane selected" : "issue-lane"}${needsReview ? " needs-review" : ""}`
                }
                key={take.clip_id}
              >
                <button
                  className="lane-label"
                  onClick={() => previewMoment(take.clip_id, 0, take.duration_s)}
                  title={`Play ${takeName(take)}`}
                >
                  {take.take_no ? `T${take.take_no}` : "UN"}
                  <small>{tc(take.duration_s)}</small>
                </button>
                <div
                  className="lane-track"
                  style={{ height: Math.max(32, markerEnds.length * 12) }}
                >
                  <span
                    className="lane-empty"
                    style={{ width: pct(take.duration_s) }}
                  />
                  {safe.map((item, index) => (
                    <button
                      key={`safe-${index}`}
                      className="lane-safe"
                      style={{
                        left: pct(item.from),
                        width: pct(item.to - item.from),
                      }}
                      onClick={() => {
                        pendingRange.current = {
                          clipId: take.clip_id,
                          range: { from: item.from, to: item.to },
                        };
                        previewMoment(take.clip_id, item.from, item.to);
                        setRange({ from: item.from, to: item.to });
                        setCleanCandidate({ from: item.from, to: item.to });
                        setInspectorTab("selects");
                        setNotice(
                          "Range selected. Adjust In / Out in the inspector, then mark reviewed clean or add to shot selects.",
                        );
                      }}
                      aria-label={`Clean candidate ${tc(item.from)} to ${tc(item.to)}`}
                      title={`Clean candidate ${tc(item.from)}–${tc(item.to)}. Review it before marking clean or adding it to shot selects.`}
                    ><span>Clean candidate</span></button>
                  ))}
                  {findingMarkers.map(({ finding, row }) => (
                    <button
                      key={String(finding.finding_id)}
                      className={`lane-finding severity-${finding.severity} review-${finding.action}${focus && String(focus.finding.finding_id) === String(finding.finding_id) ? " open" : ""}${bulkFindingKeys.has(findingKey(take.clip_id, String(finding.finding_id))) ? " bulk-selected" : ""}`}
                      style={{
                        left: pct(finding.start_s),
                        width: pct(
                          Math.max(0.4, finding.end_s - finding.start_s),
                        ),
                        top: row * 18,
                        bottom: "auto",
                        height: 16,
                      }}
                      onClick={() =>
                        bulkReview
                          ? toggleBulkFinding(take.clip_id, finding)
                          : inspect(take.clip_id, finding)
                      }
                      aria-pressed={
                        bulkReview
                          ? bulkFindingKeys.has(
                              findingKey(take.clip_id, String(finding.finding_id)),
                            )
                          : undefined
                      }
                      title={`${label(finding.code)} · ${finding.action === "machine_open" ? "Unresolved" : label(finding.action.replace("human_", ""))} · ${tc(finding.start_s)}–${tc(finding.end_s)}`}
                    >
                      <span>{label(finding.code)}</span>
                    </button>
                  ))}
                  {take.clip_id === selected?.clip_id && (cleanRanges.data?.items ?? []).filter((item) => item.state === "clean").map((item) => (
                    <button key={`clean-${item.id}`} className="lane-reviewed-clean"
                      style={{ left: pct(item.start_s), width: pct(item.end_s - item.start_s) }}
                      title={`Reviewed clean ${tc(item.start_s)}–${tc(item.end_s)}`}
                      onClick={() => {
                        setRange({ from: item.start_s, to: item.end_s });
                        previewMoment(take.clip_id, item.start_s, item.end_s);
                        setInspectorTab("selects");
                      }}>Clean</button>
                  ))}
                  {selects.filter((s) => s.clip_id === take.clip_id).map((segment) => (
                    <button key={segment.segment_id} className="lane-shot-select"
                      style={{ left: pct(segment.source_in_s), width: pct(segment.source_out_s - segment.source_in_s) }}
                      title={`Shot select ${tc(segment.source_in_s)}–${tc(segment.source_out_s)}`}
                      onPointerDown={(event) => {
                        if (!canComment || event.button !== 0) return;
                        const track = event.currentTarget.parentElement;
                        if (!track) return;
                        const width = track.getBoundingClientRect().width;
                        if (width <= 0) return;
                        const handle = (event.target as HTMLElement).closest(".range-handle");
                        const bounds = segmentBounds(segment, selectsRef.current);
                        if (!bounds) {
                          event.preventDefault();
                          setNotice("This selection overlaps an issue or another selection. Use Save shot selects to review the usable portions before trimming; dragging will not shorten it automatically.");
                          return;
                        }
                        event.currentTarget.setPointerCapture(event.pointerId);
                        segmentDrag.current = {
                          id: segment.segment_id,
                          clipId: segment.clip_id,
                          pointerId: event.pointerId,
                          kind: handle
                            ? handle.classList.contains("range-handle-in")
                              ? "in"
                              : "out"
                            : "move",
                          width,
                          duration,
                          min: bounds.min,
                          max: bounds.max,
                          pointerStart: event.clientX,
                          rangeStart: segment.source_in_s,
                          rangeEnd: segment.source_out_s,
                        };
                        event.preventDefault();
                      }}
                      onClick={() => {
                        pendingRange.current = { clipId: take.clip_id, range: { from: segment.source_in_s, to: segment.source_out_s } };
                        setRange({ from: segment.source_in_s, to: segment.source_out_s });
                        setInspectorTab("selects");
                        previewMoment(take.clip_id, segment.source_in_s, segment.source_out_s);
                      }}><i className="range-handle range-handle-in" /><span>Selected</span><i className="range-handle range-handle-out" /></button>
                  ))}
                </div>
              </div>
            );
            })}
        </section>

        <details className="performance-entry">
          <summary>Finding decision history · undo a mistaken review</summary>
          {analyses.map((analysis) => {
            const grouped = new Map<string, FindingEvent[]>();
            for (const event of analysis.history) {
              if (analysis.run && event.run_id !== analysis.run.run_id)
                continue;
              const events = grouped.get(event.finding_id) ?? [];
              events.push(event);
              grouped.set(event.finding_id, events);
            }
            return [...grouped.values()].map((events) => {
              events.sort((a, b) => a.revision - b.revision);
              const withdrawn = new Set(
                events
                  .filter((e) => e.action === "human_retracted")
                  .map((e) => e.retracts_event_id),
              );
              const valid = events.filter(
                (e) =>
                  e.action !== "human_retracted" && !withdrawn.has(e.event_id),
              );
              const target = valid[valid.length - 1],
                latest = events[events.length - 1];
              if (!events.some((e) => e.action.startsWith("human_")))
                return null;
              return (
                <div key={latest.finding_id} className="finding-history-row">
                  <button
                    onClick={() =>
                      previewMoment(
                        analysis.clip_id,
                        latest.start_s,
                        latest.end_s,
                      )
                    }
                  >
                    {label(latest.code)} · {tc(latest.start_s)}
                  </button>
                  <span>{events.length - 1} review events</span>
                  <button
                    disabled={
                      !canComment ||
                      findingAction.isPending ||
                      !target?.action.startsWith("human_") ||
                      target.actor_id !== you
                    }
                    onClick={async () => {
                      try {
                        await findingAction.mutateAsync({
                          clipId: analysis.clip_id,
                          findingId: latest.finding_id,
                          body: { rev: latest.revision, action: "retract" },
                        });
                        setNotice(
                          "Your last active review was retracted. Previous evidence and history are preserved.",
                        );
                      } catch (error) {
                        setNotice(
                          error instanceof Error
                            ? error.message
                            : "Could not retract review.",
                        );
                      }
                    }}
                  >
                    Undo my last review
                  </button>
                  <details>
                    <summary>Show events</summary>
                    {events.map((e) => (
                      <p key={e.event_id}>
                        r{e.revision} · {e.action.replaceAll("_", " ")} ·{" "}
                        {e.actor_id === you ? "You" : e.actor_role} · {e.detail}
                      </p>
                    ))}
                  </details>
                </div>
              );
            });
          })}
          <p className="policy-note">
            Only the author can retract a review. New corrections remain
            possible; undo never erases another editor&apos;s judgement.
          </p>
        </details>

        {/* Beneath the clock it belongs to. This sat in the right-hand column,
            so the bar showing where the issues are and the list naming them
            were on opposite sides of the screen and only one of them could be
            read at a time. */}
        <section className="finding-list-panel">
          <header>
            <p className="eyebrow">ISSUES ON THIS SHOT</p>
            <select
              aria-label="Filter review status"
              value={reviewFilter}
              onChange={(e) => setReviewFilter(e.target.value)}
            >
              <option value="unresolved">Unresolved</option>
              <option value="reviewed">Reviewed</option>
              <option value="all">All findings</option>
            </select>
            <span>
              {openFindings.length} to verify · {verifiedFindings} verified
            </span>
          </header>
          <div className="finding-list">
            <div className="finding-tabs" role="tablist">
              {takes.map((take) => {
                  const count = openFindings.filter(
                    ({ analysis }) =>
                      String(analysis.clip_id) === take.clip_id,
                  ).length;
                  return (
                    <button
                      key={take.clip_id}
                      role="tab"
                      aria-selected={take.clip_id === issueTab}
                      className={
                        take.clip_id === issueTab
                          ? "finding-tab on"
                          : "finding-tab"
                      }
                      onClick={() => setIssueClipId(take.clip_id)}
                    >
                      {takeName(take)}
                      <span>{count}</span>
                    </button>
                  );
                })}
            </div>
            {(() => {
              const rows = findingsForReview.filter(({ analysis, finding }) => {
                const take = takes.find(
                  (t) => t.clip_id === String(analysis.clip_id),
                );
                return (
                  take?.clip_id === issueTab &&
                  (reviewFilter === "all" ||
                    (reviewFilter === "unresolved"
                      ? finding.action === "machine_open"
                      : finding.action !== "machine_open"))
                );
              });
              if (!rows.length)
                return (
                  <p className="empty-panel">
                    No {reviewFilter === "all" ? "" : reviewFilter} findings on
                    this take.
                  </p>
                );
              return rows.map(({ analysis, finding }) => (
                <button
                  key={String(finding.finding_id)}
                  className={
                    focus &&
                    String(focus.finding.finding_id) ===
                      String(finding.finding_id)
                      ? "open"
                      : ""
                  }
                  onClick={() => inspect(String(analysis.clip_id), finding)}
                >
                  <span
                    className={`finding-dot severity-${finding.severity}`}
                  />
                  <span>
                    <b>
                      <span className="review-status">
                        {finding.action === "machine_open"
                          ? "Unresolved"
                          : label(finding.action.replace("human_", ""))}{" "}
                        ·{" "}
                      </span>
                      {tc(finding.start_s)}–{tc(finding.end_s)}{" "}
                      {label(finding.code)}
                    </b>
                    <small>{finding.detail}</small>
                  </span>
                  <i>›</i>
                </button>
              ));
            })()}
          </div>
        </section>
      </section>

      <aside className="cockpit-inspector">
        <nav className="inspector-tabs" aria-label="Inspector">
          <button
            aria-pressed={inspectorTab === "finding"}
            onClick={() => setInspectorTab("finding")}
          >
            Finding
          </button>
          <button
            aria-pressed={inspectorTab === "selects"}
            onClick={() => setInspectorTab("selects")}
          >
            Ranges & selects
          </button>
          <button
            aria-pressed={inspectorTab === "shot"}
            onClick={() => setInspectorTab("shot")}
          >
            Brief & notes
          </button>
        </nav>
        {inspectorTab === "finding" && !focus && (
          <p className="empty-panel">
            Select a finding from the timeline or issue list to review it.
          </p>
        )}
        {/* Shown *above* the shot's own controls, never instead of them. It
            used to replace the entire column, so opening an issue took away
            Add range, Shot selects and every way back — and nothing closed it:
            not the shot, not Escape, not clicking the issue again. */}
        {focus && inspectorTab === "finding" && (
          <FindingInspector
            focus={focus}
            onClose={() => {
              setFocus(null);
              setAdjusting(false);
            }}
            take={takes.find((take) => take.clip_id === focus.clipId)}
            adjusting={adjusting}
            setAdjusting={setAdjusting}
            onChange={(start, end) =>
              setFocus({
                ...focus,
                finding: { ...focus.finding, start_s: start, end_s: end },
              })
            }
            onConfirm={() => void act("confirm")}
            onDismiss={() => void act("dismiss")}
            onCorrect={(detail, severity) =>
              void act("correct", { detail, severity })
            }
            onAdjust={() => void act("adjust_range")}
            onWithdraw={() => void act("retract")}
            canWithdraw={focus.finding.actor_id === you}
            pending={findingAction.isPending}
            canAct={canComment}
          />
        )}
        <>
          <>
            <div hidden={inspectorTab !== "selects"}>
              <p className="eyebrow">
                {compared ? "AI RECOMMENDATION" : "NOT COMPARED"}
              </p>
              {/* A field of one has no winner, and a score of 0% beside the only
                take reads as a verdict against it. Say what is true instead. */}
              {compared && recommended ? (
                <>
                  <div className="recommendation">
                    <span className="recommend-icon">✦</span>
                    <div>
                      <h2>Take {recommended.take_no} suggested</h2>
                      <p>
                        {recommended.reason ||
                          "Best observable technical coverage."}
                      </p>
                    </div>
                    <b title="Relative technical ranking, not a probability of correctness">
                      {Math.round(recommended.score * 100)}
                      <small> / 100 technical</small>
                    </b>
                  </div>
                </>
              ) : (
                <>
                  <div className="recommendation not-compared">
                    <span className="recommend-icon">◇</span>
                    <div>
                      <h2>
                        {takes.length === 1
                          ? "One recording — check its performance attempts"
                          : `${takes.length} takes, not compared`}
                      </h2>
                      <p>
                        {takes.length === 1
                          ? "Cut the ranges you want."
                          : "Compare them, or cut ranges yourself."}
                      </p>
                    </div>
                  </div>
                  {canCurate && takes.length > 1 && (
                    <button
                      className="primary"
                      disabled={judge.isPending}
                      onClick={() => void judge.mutateAsync()}
                    >
                      {judge.isPending
                        ? "Comparing full takes…"
                        : "Analyse & compare takes"}
                    </button>
                  )}
                </>
              )}
              {selected && (
                <div className="selection-card">
                  <h3>Add source range</h3>
                  <div className="selection-take">
                    Take {selected.take_no}
                    <span>
                      {!compared
                        ? "Not compared"
                        : selected.clip_id === recommended?.clip_id
                          ? "AI suggestion"
                          : "Alternative"}
                    </span>
                  </div>
                  <label>
                    Use range
                    <div className="range-inputs">
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        max={selected.duration_s}
                        value={range.from}
                        onChange={(event) => {
                          setCleanCandidate(null);
                          setRange({
                            ...range,
                            from: Number(event.target.value),
                          });
                        }}
                      />
                      <span>→</span>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        max={selected.duration_s}
                        value={range.to}
                        onChange={(event) => {
                          setCleanCandidate(null);
                          setRange({ ...range, to: Number(event.target.value) });
                        }}
                      />
                    </div>
                  </label>
                  <ReviewedRanges
                    key={selected.clip_id}
                    projectId={projectId}
                    clipId={selected.clip_id}
                    start={range.from}
                    end={range.to}
                    duration={selected.duration_s}
                    canEdit={canCurate}
                    candidate={Boolean(cleanCandidate && cleanCandidate.from === range.from && cleanCandidate.to === range.to)}
                    blockedRanges={(selectedAnalysis?.findings ?? [])
                      .filter((finding) => finding.action !== "human_dismissed" && !(finding.action === "human_retracted" && finding.restored_action === "human_dismissed"))
                      .map((finding) => ({ from: finding.start_s, to: finding.end_s }))}
                    onVerified={
                      cleanCandidate
                        ? (from, to) => promoteVerifiedClean(from, to)
                        : undefined
                    }
                    onSelect={(from, to) => {
                      setCleanCandidate(null);
                      setRange({ from, to });
                      previewMoment(selected.clip_id, from);
                    }}
                  />
                  {selected.clip_id !== recommended?.clip_id && (
                    <div className="reason-chips">
                      {HUMAN_REASONS.map((item) => (
                        <button
                          key={item}
                          className={reason === item ? "chip on" : "chip"}
                          onClick={() => setReason(item)}
                        >
                          {item}
                        </button>
                      ))}
                    </div>
                  )}
                  <button
                    className="ghost cockpit-confirm"
                    disabled={!canComment || !(range.to > range.from)}
                    onClick={addRange}
                  >
                    {canComment
                      ? `Add Take ${selected.take_no} range`
                      : "Sign in to select ranges"}
                  </button>
                  <button
                    className="ghost cockpit-confirm"
                    disabled={
                      !canCurate ||
                      !(
                        range.from >= 0 &&
                        range.to > range.from &&
                        range.to <= selected.duration_s
                      )
                    }
                    onClick={async () => {
                      try {
                        const film = await api.film(projectId);
                        await api.saveFilm(projectId, {
                          rev: film.rev,
                          command_id: crypto.randomUUID(),
                          name: film.name,
                          ranges: [
                            ...(film.entries ?? []).map(
                              ({
                                source,
                                available,
                                record_start_s,
                                ...item
                              }) => item,
                            ),
                            {
                              id: crypto.randomUUID(),
                              clip_id: selected.clip_id,
                              start_s: range.from,
                              end_s: range.to,
                              attempt_revision: 0,
                              note: reason,
                            },
                          ],
                        });
                        setNotice("Range appended to the saved Film sequence.");
                      } catch (error) {
                        setNotice(
                          error instanceof Error
                            ? error.message
                            : "Could not add to Film sequence.",
                        );
                      }
                    }}
                  >
                    Add range to Film sequence
                  </button>
                  <div className="shot-selects">
                    {recoverableSelects && (
                      <p role="status" className="policy-note">
                        Unsaved shot selects are available from this browser.
                        <button
                          disabled={
                            dirty ||
                            recoverableSelects.baseline !==
                              selectionSignature(
                                savedSelects as CoverageSegment[],
                              )
                          }
                          onClick={() => {
                            coverageBase.current = recoverableSelects.baseline;
                            setSelects(recoverableSelects.rows);
                            setRecoverableSelects(null);
                          }}
                        >
                          Restore draft
                        </button>
                        <button onClick={clearSelectsDraft}>
                          Discard recovery
                        </button>
                        {recoverableSelects.baseline !==
                          selectionSignature(
                            savedSelects as CoverageSegment[],
                          ) &&
                          " Shared selects have changed since this draft; the saved selection remains authoritative."}
                      </p>
                    )}
                    <div className="shot-selects-head">
                      <b>Shot selects</b>
                      <span>
                        {selects.length} range{selects.length === 1 ? "" : "s"}
                      </span>
                    </div>
                    {selects.map((item, index) => (
                      <div className="shot-select-row" key={item.segment_id}>
                        <span>
                          <b>
                            {index + 1}. Take {item.take_no}
                          </b>
                          <span className="select-range-inputs">
                            <input
                              disabled={!canComment}
                              aria-label={`Select ${index + 1} in`}
                              type="number"
                              min="0"
                              step="0.01"
                              value={item.source_in_s}
                              onChange={(event) =>
                                updateSelectBoundary(index, "in", Number(event.target.value))
                              }
                            />
                            <i>→</i>
                            <input
                              disabled={!canComment}
                              aria-label={`Select ${index + 1} out`}
                              type="number"
                              min="0"
                              step="0.01"
                              value={item.source_out_s}
                              onChange={(event) =>
                                updateSelectBoundary(index, "out", Number(event.target.value))
                              }
                            />
                          </span>
                        </span>
                        <span className="select-order">
                          <button
                            disabled={!canComment || !index}
                            onClick={() =>
                              setSelects((rows) => {
                                const next = [...rows];
                                [next[index - 1], next[index]] = [
                                  next[index],
                                  next[index - 1],
                                ];
                                return next;
                              })
                            }
                          >
                            ↑
                          </button>
                          <button
                            disabled={
                              !canComment || index === selects.length - 1
                            }
                            onClick={() =>
                              setSelects((rows) => {
                                const next = [...rows];
                                [next[index + 1], next[index]] = [
                                  next[index],
                                  next[index + 1],
                                ];
                                return next;
                              })
                            }
                          >
                            ↓
                          </button>
                          <button
                            type="button"
                            disabled={!canComment}
                            className="remove-select"
                            aria-label={`Remove select ${index + 1}`}
                            title="Remove select"
                            onClick={() =>
                              setSelects((rows) =>
                                rows.filter((_, at) => at !== index),
                              )
                            }
                          >
                            ✕
                          </button>
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="film-row-actions">
                    <button
                      className="ghost small"
                      disabled={!dirty}
                      onClick={() => {
                        coverageBase.current = selectionSignature(
                          savedSelects as CoverageSegment[],
                        );
                        setSelects(savedSelects as CoverageSegment[]);
                        clearSelectsDraft();
                      }}
                    >
                      Discard draft / reload saved
                    </button>
                    <button
                      className="ghost small"
                      disabled={!canComment || dirty || saveCoverage.isPending}
                      onClick={async () => {
                        try {
                          await api.undo(
                            projectId,
                            scene,
                            shot,
                            screen.data?.brief.rev ?? 0,
                          );
                          coverageBase.current = null;
                          await screen.refetch();
                          setNotice("Previous shot decision restored.");
                        } catch (error) {
                          setNotice(
                            error instanceof Error
                              ? error.message
                              : "Could not undo decision.",
                          );
                        }
                      }}
                    >
                      Undo saved decision
                    </button>
                  </div>
                  <details className="source-library">
                    <summary>Reuse footage from another shot or scene</summary>
                    <p className="policy-note">
                      Adds a source range here without changing where its slate
                      placed the clip.
                    </p>
                    <div className="source-search">
                      <input
                        aria-label="Find footage from another shot or scene"
                        value={sourceQuery}
                        onChange={(event) => setSourceQuery(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") void findSources();
                        }}
                        placeholder="Scene, shot, description or clip ID"
                      />
                      <button
                        className="ghost"
                        disabled={sourceBusy}
                        onClick={() => void findSources()}
                      >
                        {sourceBusy ? "Finding…" : "Find"}
                      </button>
                    </div>
                    {sourcePreview?.proxy_uri && (
                      <Player
                        className="source-preview"
                        src={sourcePreview.proxy_uri}
                        poster={sourcePreview.sprite_uri}
                      />
                    )}
                    {sourceRows.map((source) => (
                      <div className="source-row" key={source.clip_id}>
                        <button
                          className="source-ident"
                          onClick={() => setSourcePreview(source)}
                        >
                          <b>
                            Scene {source.scene_code || source.scene} · Shot{" "}
                            {source.shot_code || source.shot} · Take{" "}
                            {source.take_no}
                          </b>
                          <small>
                            {tc(source.duration_s)}
                            {source.description
                              ? ` · ${source.description}`
                              : ""}
                          </small>
                        </button>
                        <button
                          className="ghost"
                          disabled={!canComment}
                          onClick={() => addSource(source)}
                        >
                          Add range
                        </button>
                      </div>
                    ))}
                  </details>
                  {previewSegment && previewSource?.proxy_uri && (
                    <div className="shot-select-preview">
                      <Player
                        ref={selectPlayer}
                        src={previewSource.proxy_uri}
                        poster={previewSource.sprite_uri}
                        onReady={() =>
                          selectPlayer.current?.seek(
                            previewSegment.source_in_s,
                            true,
                          )
                        }
                        onTimeUpdate={(at) => {
                          if (at >= previewSegment.source_out_s - 0.05)
                            setSelectPreviewIndex((index) =>
                              index !== null && index + 1 < selects.length
                                ? index + 1
                                : null,
                            );
                        }}
                      />
                      <small>
                        Playing select {(selectPreviewIndex ?? 0) + 1} of{" "}
                        {selects.length} · Take {previewSegment.take_no} ·{" "}
                        {tc(previewSegment.source_in_s)}–
                        {tc(previewSegment.source_out_s)}
                      </small>
                    </div>
                  )}
                  <button
                    className="ghost cockpit-confirm"
                    disabled={!selects.length}
                    onClick={() => setSelectPreviewIndex(0)}
                  >
                    ▶ Play this shot
                  </button>
                  <button
                    className="primary cockpit-confirm"
                    disabled={!canComment || saveCoverage.isPending || !dirty}
                    onClick={() => void saveSelects()}
                  >
                    {saveCoverage.isPending
                      ? "Saving…"
                      : !dirty
                        ? selects.length
                          ? `✓ ${selects.length} range${selects.length === 1 ? "" : "s"} saved`
                          : "Nothing to save"
                        : `Save ${selects.length} shot select${selects.length === 1 ? "" : "s"}`}
                  </button>
                </div>
              )}
            </div>
            <div hidden={inspectorTab !== "shot"}>
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
                    setNotice(
                      who
                        ? `Assigned to ${who.split("@")[0]}.`
                        : "Left unclaimed.",
                    );
                  } catch (error) {
                    setNotice(
                      conflictMessage(error) ??
                        "Could not change who is on this shot.",
                    );
                  }
                }}
                onState={async (next) => {
                  try {
                    await edits.setState.mutateAsync(next);
                    setNotice(
                      next
                        ? `Marked ${next.replaceAll("_", " ")}.`
                        : "Status cleared.",
                    );
                  } catch (error) {
                    setNotice(
                      conflictMessage(error) ?? "Could not change the status.",
                    );
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
            </div>
          </>
        </>
        {notice && (
          <p className="cockpit-notice">
            {notice}
            {removedClip && (
              <button
                className="linkish"
                onClick={async () => {
                  await api.restoreClip(projectId, removedClip.id);
                  setNotice(`${removedClip.name} restored.`);
                  setRemovedClip(null);
                  await screen.refetch();
                }}
              >
                Undo remove
              </button>
            )}
          </p>
        )}
        <div hidden={inspectorTab !== "shot"}>
          {canComment && noteClip && (
            <button
              className="ghost note-at-playhead"
              onClick={() =>
                setCommentAt({ clipId: noteClip.clip_id, at: selectedAt })
              }
            >
              ＋ Add note to {takeName(noteClip)} at {tc(selectedAt)}
            </button>
          )}
          <Comments
            hideOwnTrigger
            projectId={projectId}
            scene={scene}
            shot={shot}
            canComment={canComment}
            comments={screen.data?.comments ?? []}
            takes={takes.map((take) => ({
              clip_id: take.clip_id,
              take_no: take.take_no,
            }))}
            pending={commentAt}
            onConsumedPending={() => setCommentAt(null)}
            onOpen={previewMoment}
          />
        </div>
      </aside>
    </div>
  );
}

function FindingInspector({
  focus,
  take,
  adjusting,
  setAdjusting,
  onChange,
  onConfirm,
  onDismiss,
  onCorrect,
  onAdjust,
  pending,
  canAct,
  onClose,
  onWithdraw,
  canWithdraw,
}: {
  focus: Focus;
  onClose: () => void;
  take?: Take;
  adjusting: boolean;
  setAdjusting: (value: boolean) => void;
  onChange: (start: number, end: number) => void;
  onConfirm: () => void;
  onDismiss: () => void;
  onCorrect: (
    detail: string,
    severity: "note" | "attention" | "blocking",
  ) => void;
  onAdjust: () => void;
  pending: boolean;
  canAct: boolean;
  onWithdraw: () => void;
  canWithdraw: boolean;
}) {
  const finding = focus.finding;
  const evidence = useRef<PlayerHandle>(null);
  const [correcting, setCorrecting] = useState(false);
  const [changing, setChanging] = useState(false);
  const [detail, setDetail] = useState(finding.detail);
  const [severity, setSeverity] = useState<"note" | "attention" | "blocking">(
    findingSeverity(finding.severity),
  );
  useEffect(() => {
    setCorrecting(false);
    setChanging(false);
    setDetail(finding.detail);
    setSeverity(findingSeverity(finding.severity));
  }, [finding.finding_id, finding.detail, finding.severity, finding.revision]);
  return (
    <div className="finding-inspector">
      <header className="finding-inspector-head">
        <p className="eyebrow">FINDING · TAKE {take?.take_no ?? "—"}</p>
        <button
          type="button"
          className="finding-close"
          onClick={onClose}
          aria-label="Close this finding"
        >
          ✕
        </button>
      </header>
      <h2>
        {tc(finding.start_s)}–{tc(finding.end_s)} {label(finding.code)}
      </h2>
      <p className={`review-status review-${finding.action}`} role="status">
        {finding.action === "machine_open"
          ? "Unresolved · awaiting review"
          : `Reviewed · ${label(finding.action.replace("human_", ""))} · revision ${finding.revision}`}
      </p>
      {finding.action !== "machine_open" && (
        <div className="finding-actions">
          <button
            disabled={!canAct || pending}
            onClick={() => setChanging((value) => !value)}
          >
            {changing ? "Cancel change" : "Change decision"}
          </button>
          <button
            disabled={!canAct || !canWithdraw || pending}
            onClick={onWithdraw}
          >
            Withdraw my decision
          </button>
        </div>
      )}
      {take?.proxy_uri ? (
        <Player
          ref={evidence}
          className="evidence-player"
          src={take.proxy_uri}
          poster={take.sprite_uri}
          onReady={() => evidence.current?.seek(finding.start_s)}
        />
      ) : (
        <div className="evidence-placeholder">Evidence frame unavailable</div>
      )}
      <div className="frame-meta">
        <span>
          {take?.fps
            ? `${Math.max(1, Math.round((finding.end_s - finding.start_s) * take.fps))} frames`
            : `${tc(finding.end_s - finding.start_s)} duration`}
        </span>
        <span>{finding.severity}</span>
        <span>{finding.sources.join(" + ") || "AI observation"}</span>
      </div>
      <section>
        <p className="eyebrow">AI TECHNICAL NOTE</p>
        <p>
          {finding.detail ||
            "The model detected a visible technical inconsistency in this range."}
        </p>
      </section>
      {adjusting && (
        <div className="range-inputs">
          <input
            aria-label="Finding start"
            type="number"
            step="0.01"
            value={finding.start_s}
            onChange={(event) =>
              onChange(Number(event.target.value), finding.end_s)
            }
          />
          <span>→</span>
          <input
            aria-label="Finding end"
            type="number"
            step="0.01"
            value={finding.end_s}
            onChange={(event) =>
              onChange(finding.start_s, Number(event.target.value))
            }
          />
        </div>
      )}
      {correcting && (
        <div className="finding-correction">
          <label>
            Correct technical note
            <textarea
              value={detail}
              maxLength={500}
              onChange={(event) => setDetail(event.target.value)}
            />
          </label>
          <label>
            Severity
            <select
              value={severity}
              onChange={(event) =>
                setSeverity(event.target.value as typeof severity)
              }
            >
              <option value="note">Note</option>
              <option value="attention">Attention</option>
              <option value="blocking">Blocking</option>
            </select>
          </label>
          <button
            className="primary"
            disabled={pending || !detail.trim()}
            onClick={() => onCorrect(detail.trim(), severity)}
          >
            Save correction
          </button>
        </div>
      )}
      <div
        className="finding-actions"
        hidden={finding.action !== "machine_open" && !changing}
      >
        <button
          className="ghost"
          disabled={!canAct || pending}
          onClick={() =>
            onCorrect(
              `Intentional technique / style, per human review: ${finding.detail}`.slice(
                0,
                500,
              ),
              "note",
            )
          }
        >
          Intentional / keep as note
        </button>
        <button
          className="primary"
          disabled={!canAct || pending}
          onClick={onConfirm}
        >
          Issue is correct
        </button>
        <button
          className="ghost"
          disabled={!canAct || pending}
          onClick={onDismiss}
        >
          Dismiss issue
        </button>
        <button
          className="ghost"
          disabled={!canAct || pending}
          onClick={() => setCorrecting((value) => !value)}
        >
          {correcting ? "Cancel correction" : "Correct finding"}
        </button>
        {adjusting ? (
          <button
            className="ghost"
            disabled={!canAct || pending}
            onClick={onAdjust}
          >
            Save adjusted range
          </button>
        ) : (
          <button
            className="ghost"
            disabled={!canAct}
            onClick={() => setAdjusting(true)}
          >
            Adjust range
          </button>
        )}
      </div>
      {/* Two controls with nearly the same name do two unrelated things, and the
        only way to tell was to press one. */}
      <p className="policy-note">
        This corrects <b>where the problem is</b> — it moves the issue&rsquo;s
        own timecodes, and changes no footage. Choosing which parts of a take
        you actually use is <b>Add range</b>, under Shot selects.
      </p>
      {!canAct && (
        <p className="policy-note">
          Sign in to confirm, correct, dismiss, or adjust this finding.
        </p>
      )}
    </div>
  );
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
              {person === you
                ? `${person.split("@")[0]} (you)`
                : person.split("@")[0]}
            </option>
          ))}
        </select>
        {canAct && you && !mine && (
          <button
            className="ghost small"
            disabled={pending}
            onClick={() => onAssign(you)}
          >
            Claim
          </button>
        )}
        {canAct && mine && (
          <button
            className="ghost small"
            disabled={pending}
            onClick={() => onAssign("")}
          >
            Release
          </button>
        )}
      </div>
      <div className="who-row">
        <select
          aria-label="Shot status"
          value={state}
          disabled={!canAct || pending}
          onChange={(event) =>
            onState(event.target.value as "" | "in_progress" | "approved")
          }
        >
          <option value="">No status</option>
          <option value="in_progress">In progress</option>
          <option value="approved">Approved</option>
        </select>
      </div>
      <p className="policy-note">
        Claiming hides it from everyone else&apos;s queue. Approved closes it.
      </p>
    </div>
  );
}
