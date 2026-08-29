"use client";

/**
 * Where the day starts.
 *
 * The screen an editor opens in the morning and leaves open, and the one place
 * that answers "what should I be doing". Everything on it spans projects,
 * because a person works on three at once and a dashboard that makes them open
 * each one is a dashboard that gets opened once.
 *
 * Four blocks, in the order somebody needs them:
 *
 * **Needs you** — the queue. This is the product's claim made concrete: not
 * "here is your footage" but "here is the small part of it that is your job".
 *
 * **Your projects** — with a progress bar, because "how far through are we" is
 * the question a lead editor is asked every day and previously could not answer.
 *
 * **Recently decided** — what the team did while you were away. Three editors
 * sharing projects need to see each other's calls or they redo them.
 *
 * **Ask the archive** — one line, always there.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import NewProject from "@/components/NewProject";
import type { Dashboard, QueueItem } from "@/lib/api";
import { ApiError, api } from "@/lib/api";
import { currentIdentity } from "@/lib/auth";

const REASON_TONE: Record<string, string> = {
  "close call": "warn",
  "not compared yet": "cold",
  "someone is on it": "cool",
};

function toneFor(reason: string): string {
  if (reason.startsWith("director circled")) return "hot";
  return REASON_TONE[reason] ?? "warn";
}

function when(iso: string | null): string {
  if (!iso) return "";
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.round(ms / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [question, setQuestion] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.dashboard());
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        router.replace("/");
        return;
      }
      if (e instanceof ApiError && e.waking) {
        setError(
          "The archive is still waking up. It sleeps when nobody is using it.",
        );
      } else {
        setError(e instanceof Error ? e.message : "Could not load your work.");
      }
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    if (!currentIdentity()) {
      router.replace("/");
      return;
    }
    void load();
  }, [load, router]);

  if (loading) {
    return (
      <main className="shell">
        <p className="waiting">Loading — the archive may be waking up.</p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="shell">
        <p className="error">{error}</p>
        <button type="button" className="ghost" onClick={() => void load()}>
          Try again
        </button>
      </main>
    );
  }

  if (!data) return null;

  const empty = data.projects.length === 0;

  return (
    <main className="shell dash">
      <header className="dash-top">
        <div>
          <h1>
            {data.totals.waiting === 0
              ? "Nothing is waiting on you"
              : `${data.totals.waiting} shot${data.totals.waiting === 1 ? "" : "s"} need you`}
          </h1>
          <p className="dim">
            {data.totals.waiting === 0
              ? "Every shot in your projects is settled or in somebody's hands."
              : `${data.totals.yours} assigned to you · ${data.totals.unassigned} unclaimed · across ${data.totals.projects} project${data.totals.projects === 1 ? "" : "s"}`}
          </p>
        </div>
        <NewProject
          limits={data.limits}
          role={data.role}
          owned={data.projects.filter((p) => p.you_are_owner).length}
          onCreated={(id) => router.push(`/project/${id}`)}
        />
      </header>

      {empty ? (
        <FirstRun role={data.role} />
      ) : (
        <>
          <Queue items={data.queue} total={data.queue_total} you={data.you} />

          <section className="block">
            <h2>Your projects</h2>
            <div className="project-cards">
              {data.projects.map((p) => (
                <Link
                  key={p.project_id}
                  href={`/project/${p.project_id}`}
                  className="project-card"
                >
                  <span className="pc-name">{p.name}</span>
                  <span className="pc-counts">
                    {p.scenes} scene{p.scenes === 1 ? "" : "s"} · {p.shots} shot
                    {p.shots === 1 ? "" : "s"} · {p.takes} take
                    {p.takes === 1 ? "" : "s"}
                  </span>
                  <Progress pct={p.progress_pct} />
                  <span className={p.waiting ? "pc-waiting" : "pc-done"}>
                    {p.waiting
                      ? `${p.waiting} need${p.waiting === 1 ? "s" : ""} you`
                      : p.shots
                        ? "all settled"
                        : "no footage yet"}
                  </span>
                </Link>
              ))}
            </div>
          </section>

          <div className="dash-split">
            <section className="block">
              <h2>Recently decided</h2>
              {data.recent.length === 0 ? (
                <p className="hint">Nothing decided yet.</p>
              ) : (
                <ul className="activity">
                  {data.recent.map((r, i) => (
                    <li key={`${r.project_id}-${r.scene}-${r.shot}-${i}`}>
                      <Link href={`/project/${r.project_id}?scene=${r.scene}&shot=${r.shot}`}>
                        <span className="who">
                          {r.decided_by === "human"
                            ? r.actor.split("@")[0]
                            : "Panel"}
                        </span>{" "}
                        <span className="what">
                          {r.decided_by === "human" ? "chose" : "chose"} take{" "}
                          {r.take_no}
                        </span>{" "}
                        <span className="where">
                          in {r.project_name} · scene {r.scene}, shot {r.shot}
                        </span>
                        {r.reason && <span className="why">{r.reason}</span>}
                      </Link>
                      <span className="ago">{when(r.decided_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="block">
              <h2>Open notes</h2>
              {data.notes.length === 0 ? (
                <p className="hint">Nobody has left a note.</p>
              ) : (
                <ul className="activity">
                  {data.notes.map((n, i) => (
                    <li key={i}>
                      <Link href={`/project/${n.project_id}?scene=${n.scene}&shot=${n.shot}`}>
                        <span className="who">{n.author.split("@")[0]}</span>{" "}
                        <span className="why">{n.body}</span>
                        <span className="where">
                          {n.project_name} · scene {n.scene}, shot {n.shot}
                        </span>
                      </Link>
                      <span className="ago">{when(n.created_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </>
      )}

      <section className="block">
        <h2>Ask the archive</h2>
        <form
          className="ask-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (question.trim())
              router.push(`/archive?q=${encodeURIComponent(question.trim())}`);
          }}
        >
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Which takes were rejected for continuity?"
            aria-label="Ask the archive"
          />
          <button type="submit" className="primary">
            Ask
          </button>
        </form>
      </section>
    </main>
  );
}

/**
 * The queue.
 *
 * Ordered yours, then unassigned, then everybody else's — and within each, the
 * closest call first. Assignment sorts above urgency deliberately: a queue that
 * put the tightest margin at the top regardless of whose shot it is sends two
 * editors to the same row.
 */
function Queue({
  items,
  total,
  you,
}: {
  items: QueueItem[];
  total: number;
  you: string;
}) {
  if (items.length === 0) {
    return (
      <section className="block queue empty">
        <h2>Needs you</h2>
        <p className="hint">
          Nothing is waiting. Every shot is settled, confirmed, or in somebody
          else&rsquo;s hands.
        </p>
      </section>
    );
  }

  return (
    <section className="block queue">
      <h2>
        Needs you
        <span className="count">
          {total} shot{total === 1 ? "" : "s"}
          {total > items.length && ` · showing ${items.length}`}
        </span>
      </h2>
      <ul className="queue-list">
        {items.map((q) => (
          <li key={`${q.project_id}-${q.scene}-${q.shot}`}>
            <Link href={`/project/${q.project_id}?scene=${q.scene}&shot=${q.shot}`}>
              <span className={`why-chip ${toneFor(q.reason)}`}>{q.reason}</span>
              <span className="q-where">
                {q.project_name} · scene {q.scene} ·{" "}
                <strong>{q.slug || `shot ${q.shot}`}</strong>
              </span>
              <span className="q-meta">
                {q.takes} take{q.takes === 1 ? "" : "s"}
                {q.reason === "close call" && (
                  <> · margin {q.margin.toFixed(2)}</>
                )}
                {q.open_comments > 0 && <> · {q.open_comments} note</>}
              </span>
              <span className="q-who">
                {q.assignee
                  ? q.assignee === you
                    ? "yours"
                    : q.assignee.split("@")[0]
                  : "unclaimed"}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Progress({ pct }: { pct: number | null | undefined }) {
  // Null and zero are different things and the bar has to keep them apart. A
  // project with no footage is not a project that is nought per cent done.
  if (pct === null || pct === undefined) {
    return <span className="bar none" aria-label="nothing to measure yet" />;
  }
  return (
    <span
      className="bar"
      role="img"
      aria-label={`${pct}% settled`}
      title={`${pct}% settled`}
    >
      <span style={{ width: `${pct}%` }} />
    </span>
  );
}

function FirstRun({ role }: { role: string }) {
  return (
    <section className="block first-run">
      <h2>Nothing here yet</h2>
      <p>
        Make a project and drop a folder of takes into it. Everything is
        measured, grouped by shot, and compared against the other takes of its
        own shot.
      </p>
      {role === "guest" && (
        <p className="hint">
          You can also open one of our productions and work it as if it were
          yours — comment on any shot, overrule any call. The only thing reserved
          to the editors here is putting footage in.{" "}
          <Link href="/project/1">Open one</Link>.
        </p>
      )}
    </section>
  );
}
