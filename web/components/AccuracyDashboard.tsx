"use client";

/**
 * The accuracy page — public, no account, computed live.
 *
 * Most AI products never publish an error rate. Doing so is the most credible
 * move available, and it happens to be an ideal demonstration of the engine
 * underneath: these are aggregations over hundreds of thousands of rows,
 * recomputed on request rather than cached nightly. Precomputed, the page would
 * be a report; computed live, it is evidence, and a visitor can tell the
 * difference between a running system and a screenshot.
 *
 * The hardest thing to get right here is honesty about what is not known. A
 * fresh deployment has no measurements, and rendering that as 0% would claim the
 * system is wrong every time. Null and zero mean different things and the page
 * keeps them apart.
 */

import { useEffect, useState } from "react";
import type { AccuracySummary, Scale } from "@/lib/api";
import { api } from "@/lib/api";

interface EvalAxis {
  axis: string;
  cases: number;
  missed: number;
  false_alarms: number;
  recall_pct: number | null;
  precision_pct: number | null;
  timecode_accuracy_pct: number | null;
  last_run: string;
}

interface EvalState {
  state: "not_run" | "measured";
  message?: string;
  axes: EvalAxis[];
}

interface AccuracyBody extends AccuracySummary {
  definition: string;
  caveat: string;
}

export function AccuracyDashboard() {
  const [accuracy, setAccuracy] = useState<AccuracyBody | null>(null);
  const [scale, setScale] = useState<Scale | null>(null);
  const [evaluation, setEvaluation] = useState<EvalState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.accuracy() as Promise<AccuracyBody>,
      api.scale(),
      fetch("/api/public/eval").then((r) => r.json() as Promise<EvalState>),
    ])
      .then(([a, s, e]) => {
        setAccuracy(a);
        setScale(s);
        setEvaluation(e);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="state">
        <h2>Could not load the numbers</h2>
        <p>{error}</p>
      </div>
    );
  }

  if (!accuracy || !scale || !evaluation) {
    // The first request after a quiet period wakes an idling database, which
    // takes a moment. Saying so is better than a spinner that looks stuck.
    return (
      <div className="state">
        <p>Reading from the archive…</p>
        <p className="dim small">First load can take a moment while the database wakes.</p>
      </div>
    );
  }

  const hasData = accuracy.shots_total > 0;

  return (
    <div className="dashboard">
      <header className="dash-head">
        <span className="eyebrow">Live from production</span>
        <h1>How often Trimbin is right</h1>
        <p className="lede">
          Recomputed on every load from the same archive the editors work in.
          Nothing here is cached overnight or filled in by hand.
        </p>
      </header>

      {/* The headline. Deliberately alone — everything else on this page exists
          to qualify it, and a wall of equally weighted tiles would let a reader
          pick whichever number flattered us. */}
      <section className="headline">
        {hasData ? (
          <>
            <div className="big mono">{accuracy.decision_accuracy_pct}%</div>
            <p className="big-label">
              of the decisions it made confidently, no editor later replaced
            </p>
            <p className="definition">{accuracy.definition}</p>
          </>
        ) : (
          <>
            <div className="big mono dim">—</div>
            <p className="big-label">Not enough decisions yet to report accuracy.</p>
          </>
        )}
      </section>

      {hasData && (
        <>
          <section className="split">
            <Panel
              label="Decided without a person"
              value={`${accuracy.auto_decided_pct}%`}
              detail={`${fmt(accuracy.confident_decisions)} of ${fmt(accuracy.shots_total)} shots`}
              note="The claim this product rests on: most shots need nobody."
            />
            <Panel
              label="Confident calls overturned"
              value={`${accuracy.confident_overturned}`}
              detail="the system was sure and an editor disagreed"
              note="The honest error signal. Lower is better."
              tone="warn"
            />
            <Panel
              label="Flagged calls changed"
              value={`${accuracy.flagged_changed_pct}%`}
              detail={`of ${fmt(accuracy.flagged_for_review)} shots sent for review`}
              note="High is success here. These were handed to a person on purpose."
              tone="good"
            />
          </section>

          {/* Why one combined number would have been worse than useless. */}
          <aside className="explainer">
            <h3>Why the override rate is published in two halves</h3>
            <p>
              Disagreement on a close call is the system working as designed —
              those shots were handed to a person deliberately, because the takes
              were technically equivalent and the decision had become an
              editorial one. Disagreement on a confident call is a real error. A
              single combined figure would average the two and describe neither.
            </p>
          </aside>
        </>
      )}

      <section className="evaluation">
        <h2>Against footage with faults planted deliberately</h2>
        <p className="lede">
          The number above measures whether editors disagreed with us. This
          measures whether we found something we know is there, because we put it
          there at a timecode we chose. Harder, and a much smaller sample.
        </p>

        {evaluation.state === "not_run" ? (
          <p className="not-run">{evaluation.message}</p>
        ) : (
          <div className="scroll-x">
            <table>
              <thead>
                <tr>
                  <th>Axis</th>
                  <th>Cases</th>
                  {/* Never summed into one score. A missed problem reaches the
                      cut; a false alarm costs ten seconds of attention. */}
                  <th>Missed</th>
                  <th>False alarms</th>
                  <th>Found</th>
                  <th>Timecode on target</th>
                </tr>
              </thead>
              <tbody>
                {evaluation.axes.map((axis) => (
                  <tr key={axis.axis}>
                    <td>{axis.axis}</td>
                    <td className="mono">{axis.cases}</td>
                    <td className={`mono ${axis.missed > 0 ? "bad" : ""}`}>
                      {axis.missed}
                    </td>
                    <td className="mono">{axis.false_alarms}</td>
                    <td className="mono">{pct(axis.recall_pct)}</td>
                    <td className="mono">{pct(axis.timecode_accuracy_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="scale">
        <h2>What the archive holds</h2>
        <div className="stats">
          <Stat label="Productions" value={fmt(scale.productions)} />
          <Stat label="Clips" value={fmt(scale.clips)} />
          <Stat label="Scenes" value={fmt(scale.scenes)} />
          <Stat label="Shots" value={fmt(scale.shots)} />
          <Stat label="Decisions" value={fmt(scale.decisions)} />
          <Stat label="Hours of footage" value={fmt(scale.footage_hours)} />
        </div>
        <p className="dim small">
          Accuracy over three hundred thousand decisions means something
          different from accuracy over three hundred. Both numbers are here so
          neither has to be taken on trust.
        </p>
      </section>

      <footer className="caveat">
        <h3>What this number does not prove</h3>
        <p>{accuracy.caveat}</p>
      </footer>
    </div>
  );
}

function Panel({
  label,
  value,
  detail,
  note,
  tone,
}: {
  label: string;
  value: string;
  detail: string;
  note: string;
  tone?: "good" | "warn";
}) {
  return (
    <article className={`panel ${tone ?? ""}`}>
      <span className="panel-label">{label}</span>
      <span className="panel-value mono">{value}</span>
      <span className="panel-detail">{detail}</span>
      <span className="panel-note">{note}</span>
    </article>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <span className="stat-value mono">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

function fmt(n: number): string {
  return n.toLocaleString("en-US");
}

/** Null means not measured, which is not the same as zero. */
function pct(value: number | null): string {
  return value === null ? "—" : `${value}%`;
}
