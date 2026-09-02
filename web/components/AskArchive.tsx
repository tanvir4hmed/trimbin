"use client";

/**
 * Asking the archive a question, and seeing the answer with its evidence.
 *
 * Three things are shown together and none is optional: the sentence, the takes
 * it is about, and the query that produced them. A sentence alone is something
 * to trust; a sentence beside the rows and the SQL is something to check.
 *
 * An empty result says so. It is never softened with near misses presented as
 * an answer — a person who asked about scene 12 would act on rows from scene 9
 * without noticing they were not what they asked for.
 */

import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";

interface AskMatch {
  clip_id: string;
  group_id: number;
  subgroup_id: number;
  take_no: number;
  outcome: string;
  reason: string;
  decided_by: string;
  description: string;
  duration_s: number;
  playlist_uri: string;
  where: { start_s: number; end_s: number } | null;
  relevance: number;
}

interface Answer {
  question: string;
  outcome: "found" | "no_match" | "widened" | "needs_clarification" | "failed";
  answer: string;
  suggestion: string;
  matches: AskMatch[];
  sql: string;
  filters: Record<string, unknown>;
  elapsed_ms: number;
}

export default function AskArchive({
  projectId,
  onOpen,
  initialQuestion,
  collapsible = false,
}: {
  projectId: number;
  /** Jump to a take in the workspace, at the timecode if there is one. */
  onOpen?: (scene: number, shot: number, at?: number, clipId?: string) => void;
  /** Rendered on the archive screen, where the box is the whole page. */
  initialQuestion?: string;
  /**
   * Folded away until asked for.
   *
   * In the workspace this sat as a full-width band between the filters and the
   * work, so opening a shot meant scrolling past a question box every time.
   * Search already has its own place in the bar; here it is a thing you reach
   * for occasionally, and it should cost one line until you do.
   */
  collapsible?: boolean;
}) {
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [result, setResult] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSql, setShowSql] = useState(false);
  const [open, setOpen] = useState(!collapsible);

  useEffect(() => {
    api
      .suggestions(projectId)
      .then((s) => setSuggestions(s.suggestions))
      .catch(() => setSuggestions([]));
  }, [projectId]);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (trimmed.length < 2) return;

      setAsking(true);
      setError(null);
      setShowSql(false);
      try {
        setResult((await api.ask(projectId, trimmed)) as Answer);
      } catch (e) {
        if (e instanceof ApiError && e.waking) {
          setError("The archive is waking up. It sleeps when nobody is using it.");
        } else {
          setError(e instanceof Error ? e.message : "The search did not run.");
        }
        setResult(null);
      } finally {
        setAsking(false);
      }
    },
    [projectId],
  );

  // A question arriving in the URL is asked straight away. Somebody who typed
  // it on the dashboard has already asked it once; making them press the button
  // again on the next screen is asking twice.
  useEffect(() => {
    if (!initialQuestion) return;
    setQuestion(initialQuestion);
    void send(initialQuestion);
  }, [initialQuestion, send]);

  if (collapsible && !open) {
    return (
      <section className="ask ask-folded">
        <button type="button" className="ask-open" onClick={() => setOpen(true)}>
          <span className="ask-open-label">Ask the archive</span>
          <span className="ask-open-hint">Search every decision and its reason</span>
          <i aria-hidden>+</i>
        </button>
      </section>
    );
  }

  return (
    <section className="ask">
      <h2>
        Ask the archive
        {collapsible && (
          <button type="button" className="linkish ask-close" onClick={() => setOpen(false)}>
            close
          </button>
        )}
      </h2>
      <p className="dim small">
        Every decision is kept with the reason recorded at the time. This is how
        you get one back.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send(question);
        }}
        className="ask-form"
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Which takes were rejected for continuity?"
          aria-label="Your question"
          maxLength={500}
        />
        <button type="submit" className="primary" disabled={asking || question.trim().length < 2}>
          {asking ? "Looking…" : "Ask"}
        </button>
      </form>

      {suggestions.length > 0 && !result && (
        <div className="reasons">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              className="chip"
              onClick={() => {
                setQuestion(s);
                void send(s);
              }}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {error && <p className="error">{error}</p>}

      {result && (
        <div className="ask-result">
          <p className="ask-answer">{result.answer}</p>

          {result.outcome === "widened" && (
            // Labelled, never quietly substituted.
            <p className="dim small">
              Nothing matched exactly. These are the nearest, with one filter
              removed.
            </p>
          )}

          {result.outcome === "no_match" && result.suggestion && (
            <p className="dim small">{result.suggestion}</p>
          )}

          {result.matches.length > 0 && (
            <ul className="ask-matches">
              {result.matches.map((m) => (
                <li key={m.clip_id}>
                  <button
                    type="button"
                    className="ask-match"
                    onClick={() =>
                      onOpen?.(m.group_id, m.subgroup_id, m.where?.start_s, m.clip_id)
                    }
                    disabled={!onOpen}
                  >
                    <span className="where">
                      Scene {m.group_id} · Shot {m.subgroup_id} · Take {m.take_no}
                    </span>
                    <span className={`outcome ${m.outcome}`}>{m.outcome}</span>
                    <span className="ask-reason">{m.reason}</span>
                    <span className="dim small">
                      {m.decided_by === "human" ? `by ${m.decided_by}` : "by the panel"}
                      {m.where && ` · ${m.where.start_s.toFixed(1)}s`}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          <p className="dim small">
            {result.matches.length} row
            {result.matches.length === 1 ? "" : "s"} in {result.elapsed_ms}ms ·{" "}
            <button
              type="button"
              className="linkish"
              onClick={() => setShowSql(!showSql)}
            >
              {showSql ? "hide the query" : "show the query"}
            </button>
          </p>

          {showSql && (
            // Shown because a result somebody can check is worth more than one
            // they have to trust, and that is this whole system's argument.
            <pre className="ask-sql">{result.sql}</pre>
          )}
        </div>
      )}
    </section>
  );
}
