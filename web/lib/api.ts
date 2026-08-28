/**
 * The API surface, typed once.
 *
 * Mirrors the Python contracts deliberately rather than generating from them.
 * A generated client would drift silently when a field is renamed on one side;
 * a hand-written one fails to compile, which is the failure mode you want at a
 * boundary two languages meet.
 */

export type Severity = "note" | "attention" | "blocking";

export type ReviewReason =
  | "narrow_margin"
  | "no_winner"
  | "blocking"
  | "inferred_grouping";

export interface TimeRange {
  start_s: number;
  end_s: number;
}

/**
 * An observation about a clip, anchored in time where possible.
 *
 * `where` is what makes a finding clickable. Without it the reader is told
 * something is wrong and left to search a thirty-second take for it, which is
 * the difference between a note and a destination.
 */
export interface Finding {
  code: string;
  detail: string;
  severity: Severity;
  where?: TimeRange | null;
}

export interface Take {
  clip_id: string;
  take_no: number;
  duration_s: number;
  score: number;
  reason: string;
  findings: Finding[];
  playlist_uri: string;
  sprite_uri: string;
  is_selected: boolean;
}

export interface ReviewItem {
  group_id: number;
  subgroup_id: number;
  scene_slug: string;
  reason: ReviewReason;
  detail: string;
  margin: number;
  takes: Take[];
  /** Set once someone has looked, so two people never review the same shot. */
  reviewed_by?: string | null;
}

export interface Project {
  project_id: number;
  name: string;
  genre: string;
  clips: number;
  shots: number;
  /** The number that matters on the projects screen: how much needs a person. */
  awaiting_review: number;
  updated_at: string;
}

export interface AccuracySummary {
  /**
   * Null when there is not enough data to say anything.
   *
   * Distinct from zero, and the interface must keep them distinct: a system
   * with no measurements yet is not a system that is wrong every time.
   */
  decision_accuracy_pct: number | null;
  confident_decisions: number;
  confident_overturned: number;
  flagged_for_review: number;
  flagged_changed_pct: number | null;
  auto_decided_pct: number | null;
  shots_total: number;
}

export interface Scale {
  productions: number;
  clips: number;
  scenes: number;
  shots: number;
  decisions: number;
  footage_hours: number;
}

export type QueryOutcome =
  | "found"
  | "no_match"
  | "widened"
  | "needs_clarification"
  | "failed";

export interface Match {
  clip_id: string;
  group_id: number;
  subgroup_id: number;
  take_no: number;
  duration_s: number;
  description: string;
  outcome: string;
  reason: string;
  decided_by: string;
  playlist_uri: string;
  where?: TimeRange | null;
  relevance: number;
}

export interface QueryResult {
  question: string;
  outcome: QueryOutcome;
  matches: Match[];
  answer: string;
  suggestion: string;
  /** Shown in the interface, so a result can be checked rather than trusted. */
  sql: string;
  elapsed_ms: number;
}

/** A shot in the assembled cut, for the timeline. */
export interface CutEntry {
  group_id: number;
  subgroup_id: number;
  scene_slug: string;
  take_no: number;
  start_s: number;
  end_s: number;
  reason: string;
  needs_review: boolean;
  note_count: number;
}

export interface Cut {
  playlist_uri: string;
  duration_s: number;
  entries: CutEntry[];
}

/**
 * Everything goes through /api on the same origin.
 *
 * In production the load balancer routes that prefix straight to the API and
 * strips it, so Next never sees the request. In development a rewrite in
 * next.config does the same thing. Either way the browser makes a same-origin
 * call: no CORS preflight, and no API address baked into client code where
 * changing it would mean a rebuild.
 *
 * The first arrangement had the browser call bare paths and Next proxy them,
 * which put the Next container in the path of every API call for no benefit —
 * and it failed in production, because a server-side fetch inside Next has its
 * own timeout that a cold-starting API can exceed. Routing at the edge removes
 * the hop and the failure mode together.
 */
const BASE = "/api";

class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    // Prefer the server's explanation. A generic failure message leaves the
    // person with nothing to act on, and the API already knows what went wrong.
    const detail = await response
      .json()
      .then((body) => body?.detail as string | undefined)
      .catch(() => undefined);
    throw new ApiError(detail ?? `Request failed (${response.status})`, response.status);
  }

  return response.json() as Promise<T>;
}

export const api = {
  projects: () => request<Project[]>("/projects"),

  reviewQueue: (projectId: number) =>
    request<ReviewItem[]>(`/projects/${projectId}/review`),

  cut: (projectId: number) => request<Cut>(`/projects/${projectId}/cut`),

  /**
   * Record an override.
   *
   * The reason is required by the API, not merely encouraged. An override
   * without one is the moment the archive was supposed to capture, arriving
   * empty — and it is the only record anywhere of a human editorial judgement.
   */
  override: (
    projectId: number,
    subgroupId: number,
    clipId: string,
    reason: string,
  ) =>
    request<{ ok: true }>(`/projects/${projectId}/shots/${subgroupId}/select`, {
      method: "POST",
      body: JSON.stringify({ clip_id: clipId, reason }),
    }),

  ask: (projectId: number, question: string) =>
    request<QueryResult>(`/projects/${projectId}/ask`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),

  accuracy: () => request<AccuracySummary>("/public/accuracy"),
  scale: () => request<Scale>("/public/scale"),
};

export { ApiError };
