"use client";

/**
 * Accuracy, one production at a time.
 *
 * A single figure across every project is the wrong shape for this. Accuracy on
 * a scene of locked-off interiors and accuracy on a handheld chase are
 * different claims, and averaging them describes neither — an editor asking how
 * well this works on their footage cannot be answered by a mean over somebody
 * else's.
 *
 * The counts sit beside the percentage rather than under a disclosure, because
 * a percentage over four shots and one over four hundred look identical and
 * mean nothing alike.
 */

import { useEffect, useState } from "react";

interface ProjectAccuracy {
  project_id: number;
  name: string | null;
  is_public: boolean;
  decision_accuracy_pct: number | null;
  confident_decisions: number;
  confident_overturned: number;
  flagged_for_review: number;
  flagged_changed_pct: number | null;
  auto_decided_pct: number | null;
  shots_total: number;
  clips: number;
  scenes: number;
  shots: number;
  unusable: number;
  footage_hours: number;
}

interface Body {
  projects: ProjectAccuracy[];
  definition: string;
}

export function PerProjectAccuracy() {
  const [body, setBody] = useState<Body | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chosen, setChosen] = useState<number | null>(null);

  useEffect(() => {
    fetch("/api/public/accuracy/by-project")
      .then(async (r) => {
        if (!r.ok) throw new Error(`Could not read the breakdown (${r.status})`);
        return (await r.json()) as Body;
      })
      .then((b) => {
        setBody(b);
        // Default to the largest real project rather than the first id. The
        // first is whatever was created first, which is rarely the one worth
        // looking at.
        const biggest = [...b.projects].sort((a, c) => c.clips - a.clips)[0];
        setChosen(biggest?.project_id ?? null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return (
      <section>
        <h2>Per project</h2>
        <p className="dim small">{error}</p>
      </section>
    );
  }

  if (!body) {
    return (
      <section>
        <h2>Per project</h2>
        <p className="dim small">Reading…</p>
      </section>
    );
  }

  if (body.projects.length === 0) {
    return (
      <section>
        <h2>Per project</h2>
        <p className="dim small">No footage has been ingested yet.</p>
      </section>
    );
  }

  const current = body.projects.find((p) => p.project_id === chosen) ?? body.projects[0];

  return (
    <section>
      <h2>Per project</h2>
      <p className="dim small">
        The same definition, production by production. Accuracy on one kind of
        footage says little about another.
      </p>

      <div className="project-picker">
        <label htmlFor="project-select">Project</label>
        <select
          id="project-select"
          value={current.project_id}
          onChange={(e) => setChosen(Number(e.target.value))}
        >
          {body.projects.map((p) => (
            <option key={p.project_id} value={p.project_id}>
              {/* A private project is a number and its counts. A list of project
                  names on a public page is a list of who is using this. */}
              {p.name ?? `Project ${p.project_id}`}
            </option>
          ))}
        </select>
      </div>

      <div className="stats">
        <Stat
          label="Decision accuracy"
          value={
            current.decision_accuracy_pct === null
              ? "—"
              : `${current.decision_accuracy_pct}%`
          }
          note={
            current.decision_accuracy_pct === null
              ? "No confident decision has been made here yet"
              : `over ${current.confident_decisions} confident decisions`
          }
        />
        <Stat
          label="Sent to a person"
          value={String(current.flagged_for_review)}
          note={`of ${current.shots_total} shot${current.shots_total === 1 ? "" : "s"} with a decision`}
        />
        <Stat
          label="Takes"
          value={String(current.clips)}
          note={`${current.shots} shot${current.shots === 1 ? "" : "s"} · ${current.footage_hours.toFixed(2)} h`}
        />
        <Stat
          label="Unusable"
          value={String(current.unusable)}
          note={
            current.unusable === 0
              ? "nothing was rejected outright"
              : "recorded with a reason, not dropped"
          }
        />
      </div>

      {current.decision_accuracy_pct === null && (
        <p className="dim small">
          Null, not zero. A system with no confident decisions is not a system
          that is wrong every time — and every shot in this project came back
          too close to call, which is the honest answer to twelve competently
          shot takes rather than a failure to produce one.
        </p>
      )}

      <p className="dim small">{body.definition}</p>
    </section>
  );
}

function Stat({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="stat">
      <div className="stat-value mono">{value}</div>
      <div className="stat-label">{label}</div>
      {note && <div className="stat-note dim small">{note}</div>}
    </div>
  );
}
