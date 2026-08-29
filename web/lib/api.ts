/**
 * The API surface, typed once.
 *
 * Mirrors the Python contracts deliberately rather than generating from them.
 * A generated client would drift silently when a field is renamed on one side;
 * a hand-written one fails to compile, which is the failure mode you want at a
 * boundary two languages meet.
 */

import { currentToken } from "./auth";

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
  /** 0-0 means the finding applies to the whole take rather than a moment. */
  start_s: number;
  end_s: number;
  detail?: string;
  severity?: Severity;
  /** Whether ffmpeg measured this or a specialist observed it. */
  source?: "measured" | "observed";
}

/**
 * One take, as the archive returns it.
 *
 * `criteria` is a map rather than fixed fields because the axis list will grow —
 * continuity is one axis today and will probably become several — and a typed
 * record per axis means a schema change on both sides for each new one.
 */
export interface Take {
  clip_id: string;
  take_no: number;
  outcome: "selected" | "runner_up" | "not_selected" | "unusable";
  score: number;
  margin: number;
  reason: string;
  reason_code: string;
  findings: Finding[];
  criteria: Record<string, number>;
  /** Every usable stretch. A take with a fault in the middle has two. */
  safe_ranges: TimeRange[];
  /** Codes that removed time, so a trim is never a mystery. */
  trim_reasons: string[];
  /** The single span an assembly would use. */
  usable_from_s: number;
  usable_to_s: number;
  duration_s: number;
  proxy_uri: string;
  sprite_uri: string;
  decided_by: "agent" | "human";
  actor: string;
  model_id: string;
  prompt_version: string;
  panel_convened: boolean;
  decided_at: string | null;
}

export interface Verdicts {
  project_id: number;
  scene: number;
  setup: number;
  takes: Take[];
  recommended: string | null;
}

export type SetupStatus =
  | "too_few_takes"
  | "not_judged"
  | "needs_review"
  | "decided"
  | "confirmed";

export interface SetupNode {
  setup: number;
  label: string;
  takes: number;
  unusable: number;
  status: SetupStatus;
  margin: number;
}

export interface SceneNode {
  scene: number;
  setups: SetupNode[];
}

export interface Tree {
  project_id: number;
  scenes: SceneNode[];
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
  owner_email: string;
  member_emails: string[];
  is_public: boolean;
  created_at: string;
  you_are_owner: boolean;
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
    /** True when the archive was merely asleep. A different sentence entirely. */
    readonly waking = false,
  ) {
    super(message);
  }
}

/** How long to wait before trying again while the archive gets up. */
const WAKE_RETRY_MS = 12_000;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function request<T>(path: string, init?: RequestInit, retriedWake = false): Promise<T> {
  // The token is attached here rather than at each call site. A route that
  // forgets it does not fail loudly — it 401s, and the page shows an empty
  // state that looks like "no data" rather than "not signed in".
  const token = currentToken();

  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    // Prefer the server's explanation. A generic failure message leaves the
    // person with nothing to act on, and the API already knows what went wrong.
    const body = await response.json().catch(() => undefined);
    const detail = body?.detail as string | undefined;

    // A sleeping database is a wait, not a failure. One quiet retry covers the
    // common case — the person arrived first and the service is getting up —
    // and only a second failure is worth telling them about.
    if (response.status === 503 && body?.waking && !retriedWake) {
      await sleep(WAKE_RETRY_MS);
      return request<T>(path, init, true);
    }

    throw new ApiError(
      detail ?? `Request failed (${response.status})`,
      response.status,
      Boolean(body?.waking),
    );
  }

  // 204 and friends. Parsing an empty body throws, and the throw arrives at the
  // caller looking like the request failed when it succeeded.
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  /** Projects this person can open. */
  projects: () =>
    request<{ you: string; projects: Project[] }>("/projects"),

  createProject: (name: string) =>
    request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  addMember: (projectId: number, email: string) =>
    request<{ status: string; email: string }>(
      `/projects/${projectId}/members`,
      { method: "POST", body: JSON.stringify({ email }) },
    ),

  /** Every scene and setup, with enough to draw the tree. One request. */
  tree: (projectId: number) => request<Tree>(`/review/${projectId}`),

  /** Setups with takes and no verdict yet. */
  pending: (projectId: number) =>
    request<{ pending: { scene: number; setup: number; takes: number }[] }>(
      `/review/${projectId}/pending`,
    ),

  /** What was decided about one setup, and why — every take, not only the winner. */
  verdicts: (projectId: number, scene: number, setup: number) =>
    request<Verdicts>(`/review/${projectId}/${scene}/${setup}`),

  /** Ask the panel to judge a setup. Spends money; hence a POST. */
  judge: (projectId: number, scene: number, setup: number) =>
    request<{ status: string; margin?: number; needs_review?: boolean; rationale?: string }>(
      `/review/${projectId}/${scene}/${setup}`,
      { method: "POST" },
    ),

  /**
   * Record an editor's choice.
   *
   * The reason is required by the API, not merely encouraged. An override
   * without one is the moment the archive was supposed to capture, arriving
   * empty — and it is the only record anywhere of a human editorial judgement.
   *
   * Confirming the panel is recorded too. "The editor agreed" is evidence;
   * silence is not.
   */
  select: (
    projectId: number,
    scene: number,
    setup: number,
    body: { clip_id: string; reason: string; in_point_s?: number; out_point_s?: number },
  ) =>
    request<{
      status: string;
      agreed_with_panel: boolean;
      previously_recommended: string | null;
      now_selected: string;
    }>(`/review/${projectId}/${scene}/${setup}/select`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  accuracy: () => request<AccuracySummary>("/public/accuracy"),
  scale: () => request<Scale>("/public/scale"),
};

export { ApiError };
