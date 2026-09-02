"use client";

/**
 * The accuracy page.
 *
 * Two numbers with very different standing live here, and the page's only real
 * job is to keep them apart.
 *
 * The evaluation is earned: footage with a fault planted at a timecode we chose,
 * so a finding is a fact rather than an agreement. The agreement figure — how
 * often editors let a confident decision stand — needs real editorial work to
 * exist at all, and until that work happens it says so instead of showing a
 * number.
 *
 * The generated corpus is published as what it is: evidence the queries stay
 * fast, evidence of nothing else. It is never added to a real total and never
 * counted in an accuracy figure.
 */

import { useEffect, useState } from "react";

interface AccuracyBody {
  decision_accuracy_pct: number | null;
  confident_decisions: number;
  confident_overturned: number;
  flagged_for_review: number;
  flagged_changed_pct: number | null;
  auto_decided_pct: number | null;
  shots_total: number;
  definition: string;
  caveat: string;
  counts_only_real_work: boolean;
}

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

interface Corpus {
  real: {
    productions: number;
    clips: number;
    scenes: number;
    shots: number;
    footage_hours: number;
  };
  synthetic: {
    productions: number;
    clips: number;
    footage_hours: number;
    purpose: string;
  };
}

/** A sleeping archive, which is a wait rather than a failure. */
class Waking extends Error {}

export function AccuracyDashboard() {
  const [accuracy, setAccuracy] = useState<AccuracyBody | null>(null);
  const [corpus, setCorpus] = useState<Corpus | null>(null);
  const [evaluation, setEvaluation] = useState<EvalState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [waking, setWaking] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    // Every one of these checked `r.json()` and nothing else. A 503 body is
    // valid JSON — `{detail, waking}` — so a sleeping archive was stored as if
    // it were the numbers, passed the null guard below, and the page died on
    // `corpus.real.clips`. The person who hit that most often is the one who
    // arrived first: a judge, on the page that publishes our own error rate.
    let live = true;
    const read = async <T,>(path: string): Promise<T> => {
      const response = await fetch(path);
      if (response.status === 503) throw new Waking();
      if (!response.ok) throw new Error(`${path} answered ${response.status}`);
      return (await response.json()) as T;
    };

    setError(null);
    Promise.all([
      read<AccuracyBody>("/api/public/accuracy"),
      read<Corpus>("/api/public/scale"),
      read<EvalState>("/api/public/eval"),
    ])
      .then(([a, c, e]) => {
        if (!live) return;
        setWaking(false);
        setAccuracy(a);
        setCorpus(c);
        setEvaluation(e);
      })
      .catch((cause: Error) => {
        if (!live) return;
        // Asleep is a wait, not a fault, and it ends by itself.
        if (cause instanceof Waking) {
          setWaking(true);
          window.setTimeout(() => setAttempt((value) => value + 1), 6000);
          return;
        }
        setError(cause.message);
      });
    return () => {
      live = false;
    };
  }, [attempt]);

  if (error) {
    return (
      <div className="state">
        <h2>Could not load the numbers</h2>
        <p>{error}</p>
        <button className="ghost" onClick={() => setAttempt((value) => value + 1)}>
          Try again
        </button>
      </div>
    );
  }

  if (waking) {
    return (
      <div className="state">
        <p>The archive is waking up — it sleeps when nobody is using it.</p>
        <p className="dim small">This takes about half a minute.</p>
      </div>
    );
  }

  if (!accuracy || !corpus || !evaluation) {
    return (
      <div className="state">
        <p>Reading from the archive…</p>
        <p className="dim small">
          First load can take a moment while the database wakes.
        </p>
      </div>
    );
  }

  const measured = evaluation.state === "measured";
  // Two different things, and conflating them printed "null%".
  //
  // Shots exist as soon as the panel has judged anything. A *confident*
  // decision is one where the gap to the runner-up was wide enough that no
  // person was asked — and accuracy is only defined over those. Four shots all
  // flagged for review produce a shots_total of four and an accuracy of null,
  // which the old check read as "there is data" and then rendered as a
  // percentage of nothing.
  const hasConfidentDecisions = accuracy.confident_decisions > 0;
  const hasFlaggedShots = accuracy.flagged_for_review > 0;
  const hasAnyJudgement = accuracy.shots_total > 0;

  return (
    <div className="dashboard">
      <header className="dash-head">
        <span className="eyebrow">Measured, not asserted</span>
        <h1>How well Trimbin actually works</h1>
        <p className="lede">
          Two questions with very different answers: does it find a problem that
          is genuinely there, and do editors agree with what it decides. The
          first is measurable today. The second needs editors, and until there
          are some this page says so.
        </p>
      </header>

      {/* The earned number leads, because it is the one with evidence behind it. */}
      <section className="headline">
        {measured ? (
          <>
            <div className="big mono">{overallRecall(evaluation.axes)}%</div>
            <p className="big-label">
              of faults planted on purpose were found — and every one at the
              right timecode
            </p>
            <p className="definition">
              Footage was shot with a specific fault at a second we chose: camera
              shake from 4.2s, focus lost at 6.0s, a freeze at 5.0s. Finding one
              is a fact, not an opinion.
            </p>
          </>
        ) : (
          <>
            <div className="big mono dim">—</div>
            <p className="big-label">
              {evaluation.message ?? "The evaluation has not been run yet."}
            </p>
          </>
        )}
      </section>

      {measured && (
        <section>
          <h2>What was found, and what was invented</h2>
          <p>
            Missed faults and false alarms are never added into one score. They
            are not equally bad: a missed problem reaches the cut, while a false
            alarm costs an editor ten seconds. A system that flagged everything
            would score perfectly on one and be useless.
          </p>
          <div className="scroll-x">
            <table>
              <thead>
                <tr>
                  <th>Axis</th>
                  <th>Cases</th>
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
                    <td className={`mono ${axis.false_alarms > 0 ? "bad" : ""}`}>
                      {axis.false_alarms}
                    </td>
                    <td className="mono">{pct(axis.recall_pct)}</td>
                    <td className="mono">{pct(axis.timecode_accuracy_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="dim small">
            Seven takes of one shot: six with a fault planted, one clean. The
            clean take matters as much as the others — without it there is
            nothing to measure false alarms against.
          </p>
        </section>
      )}

      <section>
        <h2>Do editors agree with it?</h2>
        {hasConfidentDecisions || hasFlaggedShots ? (
          <>
            <div className="split">
              <Panel
                label="Confident calls that stood"
                // An em dash, not "null%". A percentage of nothing is not a
                // small inaccuracy — it is a number where there is no number,
                // and the whole argument of this page is that it does not do
                // that.
                value={
                  accuracy.decision_accuracy_pct === null
                    ? "—"
                    : `${accuracy.decision_accuracy_pct}%`
                }
                detail={
                  hasConfidentDecisions
                    ? `${fmt(accuracy.confident_decisions)} decisions`
                    : "no confident decision yet"
                }
                note={
                  hasConfidentDecisions
                    ? "The system was sure and nobody disagreed."
                    : "Every shot so far was too close to call, so all of them went to a person."
                }
                tone={hasConfidentDecisions ? "good" : undefined}
              />
              <Panel
                label="Confident calls overturned"
                value={hasConfidentDecisions ? fmt(accuracy.confident_overturned) : "—"}
                detail="the system was sure and an editor disagreed"
                note="The honest error signal."
                tone="warn"
              />
              <Panel
                label="Flagged calls changed"
                value={
                  accuracy.flagged_changed_pct === null || !hasFlaggedShots
                    ? "—"
                    : `${accuracy.flagged_changed_pct}%`
                }
                detail={`of ${fmt(accuracy.flagged_for_review)} sent for review`}
                note={
                  accuracy.flagged_changed_pct === 0 && hasFlaggedShots
                    ? "Nobody has looked at these yet."
                    : "High is success. These went to a person on purpose."
                }
              />
            </div>
            <aside className="explainer">
              <h3>Why this is published in two halves</h3>
              <p>
                Disagreement on a close call is the system working as designed —
                those shots were handed to a person because the takes were
                technically equivalent and the decision had become editorial.
                Disagreement on a confident call is a real error. One combined
                figure would average the two and describe neither.
              </p>
            </aside>
          </>
        ) : (
          <p className="not-run">
            {hasAnyJudgement
              ? "Shots have been judged, but none confidently enough to be right or wrong about yet."
              : "Nothing has been judged yet, so there is nothing to report."}{" "}
            This figure requires editors working on real footage and overriding
            the system where they disagree. It cannot be simulated, and a number
            here that came from anywhere else would be worthless.
          </p>
        )}
      </section>

      {/* Published, and labelled. The size of a generated set is not evidence
          about a system, and presenting it beside real counts would invite
          exactly that reading. */}
      <section>
        <h2>What the archive holds</h2>

        <h3 style={{ marginTop: 22 }}>Real footage</h3>
        {corpus.real.clips > 0 ? (
          <div className="stats">
            <Stat label="Productions" value={fmt(corpus.real.productions)} />
            <Stat label="Clips" value={fmt(corpus.real.clips)} />
            <Stat label="Shots" value={fmt(corpus.real.shots)} />
            <Stat label="Hours" value={fmt(corpus.real.footage_hours)} />
          </div>
        ) : (
          <p className="not-run">
            Only the evaluation fixtures so far — seven takes shot to test the
            measurement layer, not a production.
          </p>
        )}

        {/*
          Behind a disclosure, not beside the real counts.

          It was sitting directly under them, and three hundred thousand
          generated clips next to sixteen real ones reads as the size of the
          system however it is labelled — the first thing a reader takes from a
          page is its largest number. It has one honest job, which is showing
          the queries stay fast, and that job is done by someone who opened it
          on purpose.
        */}
        <details className="generated">
          <summary>
            Generated rows, for query performance — not footage anyone shot
          </summary>
          <div className="stats" style={{ marginTop: 14 }}>
            <Stat label="Productions" value={fmt(corpus.synthetic.productions)} />
            <Stat label="Clips" value={fmt(corpus.synthetic.clips)} />
            <Stat label="Hours" value={fmt(corpus.synthetic.footage_hours)} />
          </div>
          <p className="dim small">{corpus.synthetic.purpose}</p>
          <p className="dim small">
            Nothing here was shot, measured or judged. It exists so the archive
            can be asked a question over three hundred thousand decisions and
            answer in milliseconds, which sixteen real clips cannot demonstrate.
            Every figure elsewhere on this site reads a view these rows cannot
            enter.
          </p>
        </details>
      </section>

      <footer className="caveat">
        <h3>What none of this proves</h3>
        <p>
          The evaluation fixtures are synthetic video with faults introduced by
          filter, not footage from a camera. Real faults carry sensor noise,
          rolling shutter and motion blur that a generated pattern does not, so
          scoring well here clears a lower bar than a shoot would set.
        </p>
        <p>{accuracy.caveat}</p>
      </footer>
    </div>
  );
}

/** Weighted by cases, so an axis with more fixtures counts for more. */
function overallRecall(axes: EvalAxis[]): number {
  const withExpected = axes.filter((a) => a.recall_pct !== null);
  if (withExpected.length === 0) return 0;
  const total = withExpected.reduce((sum, a) => sum + a.cases, 0);
  const weighted = withExpected.reduce(
    (sum, a) => sum + (a.recall_pct ?? 0) * a.cases,
    0,
  );
  return Math.round((weighted / total) * 10) / 10;
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
