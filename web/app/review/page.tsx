"use client";

/**
 * The review queue: only the shots where a person adds something.
 *
 * One at a time, top two takes side by side, because that is how the comparison
 * is actually made. Keyboard: 1 and 2 choose, S skips.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Player from "@/components/Player";
import type { Verdicts } from "@/lib/api";
import { ApiError, api } from "@/lib/api";
import { currentIdentity } from "@/lib/auth";
import { useChooseTake, useDashboard } from "@/lib/queries";

const REASONS = [
  "better performance",
  "director's call",
  "cuts better",
  "stronger read",
] as const;

export default function ReviewPage() {
  const router = useRouter();
  const [at, setAt] = useState(0);
  const [verdicts, setVerdicts] = useState<Verdicts | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  // The same cache entry the dashboard reads. A choice made here invalidates
  // it, so the count behind this screen is right by the time you go back.
  const dashboard = useDashboard();
  const queue = dashboard.data?.queue ?? [];
  const loading = dashboard.isPending;

  useEffect(() => {
    if (!currentIdentity()) router.replace("/");
  }, [router]);

  useEffect(() => {
    if (dashboard.error instanceof ApiError && dashboard.error.status === 401) {
      router.replace("/");
    }
  }, [dashboard.error, router]);

  const item = queue[at];

  useEffect(() => {
    if (!item) {
      setVerdicts(null);
      return;
    }
    setReason("");
    void api
      .verdicts(item.project_id, item.scene, item.shot)
      .then(setVerdicts)
      .catch(() => setVerdicts(null));
  }, [item]);

  const ranked = verdicts ? [...verdicts.takes].sort((a, b) => b.score - a.score) : [];
  const top = ranked.slice(0, 2);

  // The mutation is keyed to whichever shot is on screen, so its invalidation
  // names the right entry.
  const chooseTake = useChooseTake(
    item?.project_id ?? 0,
    item?.scene ?? 0,
    item?.shot ?? 0,
    verdicts?.rev ?? 0,
  );
  const busy = chooseTake.isPending;

  const choose = useCallback(
    async (clipId: string, why: string) => {
      if (!item || why.trim().length < 3) return;
      try {
        await chooseTake.mutateAsync({ clip_id: clipId, reason: why.trim() });
        setAt((n) => n + 1);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not record that.");
      }
    },
    [item, chooseTake],
  );

  // 1 and 2 pick, S skips. An editor working a queue does not reach for a mouse.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      if (e.key === "s") setAt((n) => n + 1);
      if ((e.key === "1" || e.key === "2") && top.length === 2) {
        const pick = top[Number(e.key) - 1];
        void choose(pick.clip_id, reason || "chosen in review");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [top, reason, choose]);

  if (loading) return <main className="shell"><p className="waiting">Loading.</p></main>;

  if (queue.length === 0 || at >= queue.length) {
    return (
      <main className="shell">
        <div className="first-run">
          <h2>{queue.length === 0 ? "Nothing needs you" : "Queue cleared"}</h2>
          <p>
            {queue.length === 0
              ? "Every shot is settled or in somebody else's hands."
              : `${queue.length} shot${queue.length === 1 ? "" : "s"} reviewed.`}
          </p>
          <Link href="/dashboard" className="ghost">
            Back to your work
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="shell">
      <div className="rq-head">
        <div>
          <span className="num">{item.reason.toUpperCase()}</span>
          <h2>
            {item.project_name} · Scene {item.scene} · {item.slug || `Shot ${item.shot}`}
          </h2>
          <div className="rq-why">
            {item.reason === "close call"
              ? `Top two takes are within ${(item.margin * 100).toFixed(0)}%. The technical difference has run out.`
              : item.reason.startsWith("director")
                ? `The director circled take ${item.circled_take}; the measurements chose take ${item.chosen_take}.`
                : "No comparison has been run."}
          </div>
        </div>
        <div className="prog">
          {at + 1} of {queue.length}
        </div>
      </div>

      {error && <p className="error small">{error}</p>}

      {!verdicts ? (
        <p className="waiting">Loading takes.</p>
      ) : top.length < 2 ? (
        <div className="first-run">
          <p>This shot has not been compared yet.</p>
          <Link
            href={`/project/${item.project_id}?scene=${item.scene}&shot=${item.shot}`}
            className="ghost"
          >
            Open it
          </Link>
        </div>
      ) : (
        <>
          <div className="compare">
            {top.map((t, i) => (
              <div key={t.clip_id} className={i === 0 ? "cand rec" : "cand"}>
                <Player className="cvid" src={t.proxy_uri} poster={t.sprite_uri} />
                <div className="chead">
                  <span className="cbadge">
                    <kbd>{i + 1}</kbd> Take {t.take_no}
                    {i === 0 ? " · recommended" : " · alternative"}
                    {verdicts.circled_take === t.take_no && " ◎"}
                  </span>
                  <span className="cscore">{Math.round(t.score * 100)}%</span>
                </div>
                <div className="creason">{t.reason}</div>
                {t.findings.slice(0, 3).map((f, k) => (
                  <div key={k} className="find">
                    <span className="fcode">{f.code}</span>
                    <span className="ftime">
                      {f.end_s > f.start_s ? `${f.start_s.toFixed(1)}s` : "throughout"}
                    </span>
                  </div>
                ))}
                <button
                  type="button"
                  className="primary"
                  disabled={busy || reason.trim().length < 3}
                  onClick={() => void choose(t.clip_id, reason)}
                >
                  Use take {t.take_no}
                </button>
              </div>
            ))}
          </div>

          <div className="rq-reason">
            <div className="chips">
              {REASONS.map((r) => (
                <button
                  key={r}
                  type="button"
                  className={reason === r ? "chip on" : "chip"}
                  onClick={() => setReason(r)}
                >
                  {r}
                </button>
              ))}
            </div>
            <input
              type="text"
              value={reason}
              placeholder="or say why in your own words"
              aria-label="Reason"
              onChange={(e) => setReason(e.target.value)}
            />
          </div>

          <div className="actions">
            <button type="button" className="ghost" onClick={() => setAt((n) => n + 1)}>
              Decide later
            </button>
            <Link
              href={`/project/${item.project_id}?scene=${item.scene}&shot=${item.shot}`}
              className="ghost"
            >
              See all {verdicts.takes.length} takes
            </Link>
            <span className="hint">
              <kbd>1</kbd> <kbd>2</kbd> choose · <kbd>S</kbd> skip
            </span>
          </div>
        </>
      )}
    </main>
  );
}
