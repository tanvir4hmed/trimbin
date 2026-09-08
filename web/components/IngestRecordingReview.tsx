"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Player, { type PlayerHandle } from "./Player";
import { api } from "@/lib/api";

export default function IngestRecordingReview({
  projectId,
  clipId,
  canEdit,
}: {
  projectId: number;
  clipId: string;
  canEdit: boolean;
}) {
  const player = useRef<PlayerHandle>(null);
  const [error, setError] = useState("");
  const [queuing, setQueuing] = useState(false);
  const attempts = useQuery({
    queryKey: ["project", projectId, "attempts", clipId],
    queryFn: () => api.attempts(projectId, clipId),
    refetchInterval: (q) =>
      ["pending", "queued", "processing"].includes(
        q.state.data?.analysis_state ?? "",
      )
        ? 5000
        : false,
  });
  const analysis = useQuery({
    queryKey: ["project", projectId, "recording-analysis", clipId],
    queryFn: () => api.recordingAnalysis(projectId, clipId),
  });
  const phase = attempts.data?.analysis_state ?? "";
  useEffect(() => {
    if (phase === "completed") void analysis.refetch();
  }, [phase]);
  const busy = queuing || ["pending", "queued", "processing"].includes(phase);
  const data = analysis.data;
  return (
    <details className="performance-entry recording-preview">
      <summary>
        Recording preview & analysis ·{" "}
        {phase.replaceAll("_", " ") || "checking"}
      </summary>
      {data && (
        <Player
          ref={player}
          src={data.clip.proxy_uri}
          poster={data.clip.sprite_uri}
          className="recording-player"
        />
      )}
      <p>
        Placement and analysis are separate. Unassigned footage remains here
        until you choose its destination.
      </p>
      {analysis.isError && (
        <p role="alert">
          Preview could not load.{" "}
          <button onClick={() => void analysis.refetch()}>Retry</button>
        </p>
      )}
      {attempts.isError && (
        <p role="alert">
          Analysis status could not load.{" "}
          <button onClick={() => void attempts.refetch()}>Retry</button>
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {attempts.data?.analysis_error && (
        <p role="status">{attempts.data.analysis_error}</p>
      )}
      <p>
        {data?.coverage_complete
          ? `${data.findings.length} open observations; this is not a guarantee that footage is clean.`
          : "Full-duration analysis is not complete."}
      </p>
      {data?.description && <p>{data.description}</p>}
      {(data?.findings ?? []).map((finding) => (
        <button
          key={finding.finding_id}
          onClick={() => player.current?.seek(finding.start_s, true)}
        >
          {finding.start_s.toFixed(2)}–{finding.end_s.toFixed(2)}s ·{" "}
          {finding.code.replaceAll(".", " ")} · {finding.severity}
        </button>
      ))}
      {(attempts.data?.items ?? []).map((item) => (
        <button
          key={item.id}
          onClick={() => player.current?.seek(item.start_s, true)}
        >
          {item.label} · {item.start_s.toFixed(2)}–{item.end_s.toFixed(2)}s
        </button>
      ))}
      {canEdit && (
        <button
          disabled={busy}
          onClick={async () => {
            setQueuing(true);
            setError("");
            try {
              await api.analyseAttempts(projectId, clipId);
              await attempts.refetch();
            } catch (e) {
              setError(
                e instanceof Error ? e.message : "Could not queue analysis.",
              );
            } finally {
              setQueuing(false);
            }
          }}
        >
          {busy
            ? "Analysis in progress…"
            : data?.coverage_complete
              ? "Refresh analysis"
              : "Analyse / retry recording"}
        </button>
      )}
    </details>
  );
}
