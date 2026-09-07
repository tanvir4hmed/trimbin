"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { currentIdentity } from "@/lib/auth";

export function AccuracyDashboard() {
  const params = useSearchParams();
  const router = useRouter();
  const [project, setProject] = useState(0);
  const requestedProject = Number(params.get("project") || 0);
  useEffect(() => setProject(requestedProject), [requestedProject]);
  const query = useQuery({
    queryKey: ["quality", currentIdentity()?.email ?? "anonymous"],
    queryFn: api.quality,
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
  });
  const data = query.data;
  const selected = data?.projects.find((p) => p.project_id === project);
  const stats = project ? selected : data?.overall;
  return (
    <section className="quality-page">
      <header>
        <p className="eyebrow">LIVE PROJECT DATA</p>
        <h1>Accuracy & review</h1>
        <p>What has been analysed, and what editors have actually checked.</p>
      </header>
      {data && project > 0 && !selected && (
        <p className="error">
          This project is unavailable in your review measurements. Choose an
          available project or All visible projects.
        </p>
      )}
      <div className="quality-toolbar">
        <label>
          Project{" "}
          <select
            value={selected?.project_id ?? 0}
            onChange={(e) =>
              router.replace(
                e.target.value === "0"
                  ? "/accuracy"
                  : `/accuracy?project=${e.target.value}`,
              )
            }
          >
            <option value={0}>All visible projects</option>
            {data?.projects.map((p) => (
              <option key={p.project_id} value={p.project_id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <button
          className="ghost"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          {query.isFetching ? "Refreshing…" : "Refresh now"}
        </button>
        <small role="status">
          {data
            ? `Updated ${new Date(data.measured_at).toLocaleTimeString()} · refreshes every 15s`
            : "Loading live measurements…"}
        </small>
      </div>
      {query.isError && (
        <p className="error" role="alert">
          Could not refresh measurements.{" "}
          {data ? "The last successful reading is shown." : "Try Refresh now."}
        </p>
      )}
      {stats && (
        <>
          <div className="quality-grid">
            <article>
              <small>Footage processed</small>
              <strong>{stats.clips}</strong>
              <p>
                {stats.placed} placed ·{" "}
                {Math.max(0, stats.clips - stats.placed)} awaiting placement
              </p>
            </article>
            <article>
              <small>Full-take analysis</small>
              <strong>
                {stats.analysed} / {stats.clips}
              </strong>
              <p>
                Completed across the recorded duration. This is coverage, not
                accuracy.
              </p>
            </article>
            <article>
              <small>Findings checked by editors</small>
              <strong>
                {stats.reviewed} / {stats.findings}
              </strong>
              <p>
                {Math.max(0, stats.findings - stats.reviewed)} not yet reviewed
              </p>
            </article>
            <article>
              <small>First-review agreement</small>
              <strong>
                {stats.agreement_pct === null
                  ? "Not measured"
                  : `${stats.agreement_pct}%`}
              </strong>
              <p>
                {stats.confirmed} confirmed unchanged out of {stats.reviewed}{" "}
                reviewed findings
              </p>
            </article>
          </div>
          <div className="quality-breakdown">
            <span>{stats.confirmed} confirmed</span>
            <span>{stats.corrected} corrected / range adjusted</span>
            <span>{stats.dismissed} dismissed</span>
          </div>
          <p className="hint">
            {stats.reviewed < 20
              ? "Small review sample — do not treat this as overall model accuracy."
              : "Agreement reflects reviewed findings, not undetected issues or creative preferences."}
          </p>
          <details className="quality-method">
            <summary>How these numbers are calculated</summary>
            <p>
              Agreement = confirmed unchanged ÷ (confirmed + corrected +
              dismissed). Each finding counts once, using its first non-withdrawn human review
              in the current analysis run. Confirming a corrected finding later
              does not turn the original suggestion into a correct one. Retracting
              an accidental review removes that judgement, not its history.
            </p>
            <p>
              Unreviewed findings, take preferences and synthetic evaluation
              data do not count as correctness. A small or self-selected sample
              is not overall model accuracy; missed issues require independently
              labelled footage to measure recall.
            </p>
            <p>
              Uploads change the footage count after processing; placement and
              completed analysis update their own counts. Confirm, correct or
              dismiss an issue in Shot Review, then refresh here. Archive
              delivery can briefly lag behind a saved review.
            </p>
            <small>
              {data?.scope}. Deleted footage is excluded. No review means “Not
              measured,” never 100%.
            </small>
          </details>
        </>
      )}
    </section>
  );
}
