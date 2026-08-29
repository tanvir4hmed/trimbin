/**
 * The API surface, typed once.
 *
 * Mirrors the Python contracts deliberately rather than generating from them.
 * A generated client would drift silently when a field is renamed on one side;
 * a hand-written one fails to compile, which is the failure mode you want at a
 * boundary two languages meet.
 *
 * The vocabulary is scene → shot → take throughout. A *shot* is one camera
 * position — 12A the wide, 12B her close-up — and a *take* is one attempt at
 * it. The word used to be "setup", which is a real word on set for the same
 * object but not the one anybody says afterwards.
 */

import { currentToken } from "./auth";

/**
 * How bad a finding is — and the empty string, which is not a level.
 *
 * Rows written before severity was stored carry no level. That is a fourth
 * state and the interface keeps it distinct: a finding drawn as "attention"
 * because nothing was recorded looks exactly like one a panel judged, and the
 * whole argument of this system is that a judgement is either made or absent.
 */
export type Severity = "note" | "attention" | "blocking" | "";

export type Role = "lead" | "editor" | "guest";

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
  camera: string;
  captured_at: string | null;
}

export interface Verdicts {
  project_id: number;
  scene: number;
  shot: number;
  takes: Take[];
  recommended: string | null;
  /** What the room preferred on the day. Never shown to the panel. */
  circled_take: number;
  circled_by: string;
  differs_from_circle: boolean;
  assignee: string;
  state: ShotState;
}

/** What a person set, as distinct from what the system derived. */
export type ShotState = "" | "needs_review" | "in_progress" | "approved";

export type ShotStatus =
  | "too_few_takes"
  | "not_judged"
  | "needs_review"
  | "differs_from_circle"
  | "decided"
  | "confirmed";

export interface ShotNode {
  shot: number;
  slug: string;
  label: string;
  takes: number;
  unusable: number;
  status: ShotStatus;
  state: ShotState;
  assignee: string;
  circled_take: number;
  chosen_take: number;
  differs_from_circle: boolean;
  margin: number;
  cameras: string[];
  shoot_day: string;
  open_notes: number;
}

export interface SceneNode {
  scene: number;
  shots: ShotNode[];
}

export interface Tree {
  project_id: number;
  scenes: SceneNode[];
  /** The axes this project actually has, so a filter never offers nothing. */
  cameras: string[];
  shoot_days: string[];
  review_margin: number;
}

/** What a shot was meant to be — the lined script, as a script supervisor writes it. */
export interface Brief {
  scene: number;
  shot: number;
  slug: string;
  heading: string;
  action: string;
  line: string;
  notes: string;
  look: string;
  circled_take: number;
  circled_by: string;
  assignee: string;
  state: ShotState;
  state_by: string;
  state_at: string | null;
  updated_at: string;
  updated_by: string;
  is_empty: boolean;
  note?: string;
}

export interface Comment {
  comment_id: string;
  parent_id: string | null;
  clip_id: string | null;
  author: string;
  author_role: string;
  body: string;
  at_s: number;
  to_s: number;
  whole_take: boolean;
  created_at: string;
  resolved_by: string;
  resolved: boolean;
  is_reply?: boolean;
}

export interface Project {
  project_id: number;
  name: string;
  owner_email: string;
  member_emails: string[];
  is_public: boolean;
  created_at: string;
  you_are_owner: boolean;
  you_can_upload: boolean;
  /** Present only when the list was asked for with detail. */
  scenes?: number;
  shots?: number;
  takes?: number;
  settled?: number;
  waiting?: number;
  progress_pct?: number | null;
}

export interface PlannedShot {
  shot: number;
  slug: string;
  description: string;
}

export interface PlannedScene {
  scene: number;
  heading: string;
  shots: PlannedShot[];
}

export interface Plan {
  project_id: number;
  scenes: PlannedScene[];
  next_scene: number;
}

/** One shot the footage landed in, as the upload screen shows it. */
export interface UploadGroup {
  scene: number;
  shot: number;
  takes: number;
  unread_slates: number;
  mismatches: { filename: string; detail: string; slate_raw: string }[];
  status: "clean" | "unread" | "mismatch";
}

export interface JobStatus {
  job_id: string;
  state: string;
  done: boolean;
  total: number;
  completed: number;
  failed: number;
  failures: { clip_id: string; reason: string }[];
  target: { scene: number; shot: number } | null;
  groups: UploadGroup[];
  needs_a_look: number;
  started_at: string;
  finished_at: string | null;
}

export interface Limits {
  projects: number;
  scenes: number;
  takes_per_shot: number;
  clip_seconds: number;
  retention_days: number;
}

/**
 * Who is asking, and what the API will let them do.
 *
 * Asked rather than worked out. A page that decides whether to draw the upload
 * button by comparing an address against a list is a second implementation of
 * the permission rules, and the two will disagree — the failure being a button
 * that is drawn and then refused, which is worse than no button.
 */
export interface Me {
  email: string | null;
  signed_in: boolean;
  role: Role;
  can_read: boolean;
  can_comment: boolean;
  can_override: boolean;
  /** Running the panel, describing a shot, circling, assigning, statusing —
   *  in *our* productions. Inside a project you own you can do all of it. */
  can_curate_team_projects: boolean;
  can_upload_to_team_projects: boolean;
  can_create_own_project: boolean;
  can_add_members: boolean;
  can_supersede: boolean;
  limits: Limits;
  demo_project_id: number;
}

export interface QueueItem {
  project_id: number;
  project_name: string;
  scene: number;
  shot: number;
  slug: string;
  takes: number;
  margin: number;
  reason: string;
  assignee: string;
  state: ShotState;
  circled_take: number;
  chosen_take: number;
  open_comments: number;
}

export interface RecentDecision {
  project_id: number;
  project_name: string;
  scene: number;
  shot: number;
  take_no: number;
  decided_by: "agent" | "human";
  actor: string;
  reason: string;
  decided_at: string | null;
  margin: number;
}

export interface RecentNote {
  project_id: number;
  project_name: string;
  scene: number;
  shot: number;
  author: string;
  body: string;
  created_at: string;
}

export interface Dashboard {
  you: string;
  role: Role;
  queue: QueueItem[];
  queue_total: number;
  totals: { waiting: number; yours: number; unassigned: number; projects: number };
  projects: (Project & {
    members: number;
    scenes: number;
    shots: number;
    takes: number;
    settled: number;
    waiting: number;
    progress_pct: number | null;
  })[];
  recent: RecentDecision[];
  notes: RecentNote[];
  limits: Limits;
}

/** One shot's place in the assembled scene. */
export interface StringoutEntry {
  scene: number;
  shot: number;
  slug: string;
  clip_id: string;
  take_no: number;
  start_s: number;
  end_s: number;
  duration_s: number;
  proxy_uri: string;
  sprite_uri: string;
  reason: string;
  decided_by: "agent" | "human";
  actor: string;
  margin: number;
  needs_review: boolean;
  circled_take: number;
  differs_from_circle: boolean;
  open_comments: number;
}

/**
 * The scene assembled from the takes that were chosen.
 *
 * A cutting room calls this a **stringout**, and it is what an assistant editor
 * hands the editor: every shot of the scene, in order, one take each. It is not
 * an edit — nothing here decides where a cut goes, which is a story question.
 */
export interface Stringout {
  project_id: number;
  scene: number;
  entries: StringoutEntry[];
  duration_s: number;
  shots: number;
  unresolved: number;
  disagreements: number;
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
  /** Who is asking, and what they may do. Works signed out, and answers truthfully. */
  me: () => request<Me>("/me"),

  /**
   * Which ways in this deployment has.
   *
   * Asked before a sign-in screen is drawn. Offering Google where there is no
   * OAuth client draws a button that does nothing; hiding the password form
   * where there is one leaves a door nobody finds.
   */
  authOptions: () =>
    request<{ google: boolean; password: boolean }>("/auth/options"),

  /** The queue, the project cards, and what the team did while you were away. */
  dashboard: () => request<Dashboard>("/dashboard"),

  /** Projects this person can open. `detail` adds the counts a list screen needs. */
  projects: (detail = false) =>
    request<{ you: string; role: Role; limits: Limits; projects: Project[] }>(
      detail ? "/projects?detail=true" : "/projects",
    ),

  project: (projectId: number) => request<Project>(`/projects/${projectId}`),

  createProject: (name: string) =>
    request<Project & { limits: Limits }>("/projects", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  addMember: (projectId: number, email: string) =>
    request<{ status: string; email: string }>(
      `/projects/${projectId}/members`,
      { method: "POST", body: JSON.stringify({ email }) },
    ),

  /**
   * Every scene and shot, with enough to draw the tree. One request.
   *
   * The filters are the axes a real bin is cut on — scene, camera, shoot day,
   * who is on it. A tree with one axis cannot answer "everything from Tuesday".
   */
  tree: (
    projectId: number,
    filters?: { scene?: number; camera?: string; shoot_day?: string; assignee?: string },
  ) => {
    const q = new URLSearchParams();
    if (filters?.scene !== undefined) q.set("scene", String(filters.scene));
    if (filters?.camera) q.set("camera", filters.camera);
    if (filters?.shoot_day) q.set("shoot_day", filters.shoot_day);
    if (filters?.assignee) q.set("assignee", filters.assignee);
    const query = q.toString();
    return request<Tree>(`/review/${projectId}${query ? `?${query}` : ""}`);
  },

  /** Shots with takes and no verdict yet. */
  pending: (projectId: number) =>
    request<{ pending: { scene: number; shot: number; takes: number }[] }>(
      `/review/${projectId}/pending`,
    ),

  /** What was decided about one shot, and why — every take, not only the winner. */
  verdicts: (projectId: number, scene: number, shot: number) =>
    request<Verdicts>(`/review/${projectId}/${scene}/${shot}`),

  /** Ask the panel to judge a shot. Spends money; hence a POST. */
  judge: (projectId: number, scene: number, shot: number) =>
    request<{ status: string; margin?: number; needs_review?: boolean; rationale?: string }>(
      `/review/${projectId}/${scene}/${shot}`,
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
    shot: number,
    body: { clip_id: string; reason: string; in_point_s?: number; out_point_s?: number },
  ) =>
    request<{
      status: string;
      agreed_with_panel: boolean;
      previously_recommended: string | null;
      now_selected: string;
    }>(`/review/${projectId}/${scene}/${shot}/select`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** Put back what stood before the last human decision. Written forward, never deleted. */
  undo: (projectId: number, scene: number, shot: number) =>
    request<{ status: string; restored: string; undone_from: string }>(
      `/review/${projectId}/${scene}/${shot}/undo`,
      { method: "POST" },
    ),

  brief: (projectId: number, scene: number, shot: number) =>
    request<Brief>(`/review/${projectId}/${scene}/${shot}/brief`),

  saveBrief: (
    projectId: number,
    scene: number,
    shot: number,
    body: Partial<Pick<Brief, "slug" | "heading" | "action" | "line" | "notes" | "look">>,
  ) =>
    request<Brief>(`/review/${projectId}/${scene}/${shot}/brief`, {
      method: "PUT",
      body: JSON.stringify({
        slug: "", heading: "", action: "", line: "", notes: "", look: "",
        ...body,
      }),
    }),

  /** The take the room circled. Zero clears it. Never shown to the panel. */
  circle: (projectId: number, scene: number, shot: number, take_no: number) =>
    request<Brief>(`/review/${projectId}/${scene}/${shot}/circle`, {
      method: "PUT",
      body: JSON.stringify({ take_no }),
    }),

  assign: (projectId: number, scene: number, shot: number, assignee: string) =>
    request<Brief>(`/review/${projectId}/${scene}/${shot}/assignee`, {
      method: "PUT",
      body: JSON.stringify({ assignee }),
    }),

  setState: (projectId: number, scene: number, shot: number, state: ShotState) =>
    request<Brief>(`/review/${projectId}/${scene}/${shot}/state`, {
      method: "PUT",
      body: JSON.stringify({ state }),
    }),

  comments: (projectId: number, scene: number, shot: number) =>
    request<{ comments: Comment[]; open: number }>(
      `/review/${projectId}/${scene}/${shot}/comments`,
    ),

  comment: (
    projectId: number,
    scene: number,
    shot: number,
    body: { body: string; clip_id?: string | null; at_s?: number; to_s?: number; parent_id?: string },
  ) =>
    request<Comment>(`/review/${projectId}/${scene}/${shot}/comments`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  resolveComment: (projectId: number, scene: number, shot: number, commentId: string) =>
    request<{ status: string }>(
      `/review/${projectId}/${scene}/${shot}/comments/${commentId}/resolve`,
      { method: "POST" },
    ),

  /** Which scenes a project has. */
  scenes: (projectId: number) =>
    request<{ scenes: number[] }>(`/scenes/${projectId}`),

  /** The scene as it currently stands, shot by shot. */
  stringout: (projectId: number, scene: number) =>
    request<Stringout>(`/scenes/${projectId}/${scene}`),

  /**
   * Where the exports live.
   *
   * Returned as URLs rather than fetched, because these are downloads: the
   * browser has a perfectly good way to save a file and reimplementing it with
   * a blob would break the filename the server already chose.
   */
  edlUrl: (projectId: number, scene: number, fps = 24) =>
    `${BASE}/scenes/${projectId}/${scene}/edl?fps=${fps}`,
  markersUrl: (projectId: number, scene: number, fps = 24) =>
    `${BASE}/scenes/${projectId}/${scene}/markers.csv?fps=${fps}`,

  /** What a guest account may hold, from the API that enforces it. */
  guestLimits: () =>
    request<Limits & { note: string }>("/public/limits"),

  grantUpload: (
    projectId: number,
    filenames: string[],
    target?: { scene: number; shot: number },
  ) =>
    request<{
      job_id: string;
      tickets: {
        clip_id: string;
        filename: string;
        upload_url: string;
        headers: Record<string, string>;
      }[];
      expires_in_s: number;
    }>("/uploads/grant", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        filenames,
        scene: target?.scene ?? 0,
        shot: target?.shot ?? 0,
      }),
    }),

  completeUpload: (
    jobId: string,
    clipIds: string[],
    filenamesByClip: Record<string, string> = {},
  ) =>
    request<{ status: string; queued: string; missing: string }>(
      "/uploads/complete",
      {
        method: "POST",
        body: JSON.stringify({
          job_id: jobId,
          clip_ids: clipIds,
          filenames_by_clip: filenamesByClip,
        }),
      },
    ),

  jobStatus: (jobId: string) => request<JobStatus>(`/uploads/jobs/${jobId}`),

  /** The scenes and shots somebody declared, before any footage exists. */
  plan: (projectId: number) => request<Plan>(`/structure/${projectId}`),

  addScene: (projectId: number, scene: number, heading: string) =>
    request<PlannedScene>(`/structure/${projectId}/scenes`, {
      method: "POST",
      body: JSON.stringify({ scene, heading }),
    }),

  addShot: (
    projectId: number,
    scene: number,
    shot: number,
    slug: string,
    description: string,
  ) =>
    request<PlannedScene>(`/structure/${projectId}/scenes/${scene}/shots`, {
      method: "POST",
      body: JSON.stringify({ shot, slug, description }),
    }),

  removeShot: (projectId: number, scene: number, shot: number) =>
    request<PlannedScene>(
      `/structure/${projectId}/scenes/${scene}/shots/${shot}`,
      { method: "DELETE" },
    ),

  /** Questions worth asking, so an empty box is not a blank page. */
  suggestions: (projectId: number) =>
    request<{ suggestions: string[] }>(`/ask/${projectId}/suggestions`),

  /**
   * A question in plain language.
   *
   * The reply carries the SQL that ran. A result somebody can check is worth
   * more than one they have to trust, and that is the argument this whole
   * system rests on.
   */
  ask: (projectId: number, question: string) =>
    request<QueryResult>(`/ask/${projectId}`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),

  accuracy: () => request<AccuracySummary>("/public/accuracy"),
  scale: () => request<Scale>("/public/scale"),
};

export { ApiError };
