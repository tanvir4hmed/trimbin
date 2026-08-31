"use client";

/**
 * One cache, keyed by entity, invalidated by the mutations that touch it.
 *
 * Every page fetched independently and held its own copy. Override a take on the
 * shot screen and the dashboard's "needs you" count stayed wrong until a reload;
 * assign a shot and the tree beside it did not move. Each screen was correct
 * about the moment it loaded and about nothing since.
 *
 * The fix is not more fetching. It is one cache with keys that describe what the
 * data is *about*, so a mutation can say which facts it invalidated and every
 * mounted screen holding one of them refetches. That is the whole of cross-page
 * consistency, and it is a library rather than an architecture.
 *
 * Keys are hierarchical on purpose: invalidating `["project", 3]` also
 * invalidates `["project", 3, "shot", 12, 1]`, because a prefix match is how
 * TanStack Query compares them. Choosing that shape means "something in this
 * project changed" is one line rather than a list somebody has to keep current.
 */

import {
  QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type { Brief, ShotState } from "./api";
import { ApiError, api } from "./api";

/**
 * The key vocabulary.
 *
 * Written once, as functions, because a key typed by hand at a call site is a
 * cache miss nobody notices — the query runs, the data arrives, and the entry it
 * writes is one no invalidation will ever match.
 */
export const keys = {
  me: () => ["me"] as const,
  dashboard: () => ["dashboard"] as const,
  projects: (detail = false) => ["projects", detail] as const,

  project: (id: number) => ["project", id] as const,
  projectScreen: (id: number, filters?: Record<string, string | undefined>) =>
    ["project", id, "screen", filters ?? {}] as const,
  plan: (id: number) => ["project", id, "plan"] as const,
  activity: (id: number) => ["project", id, "activity"] as const,
  scenes: (id: number) => ["project", id, "scenes"] as const,
  stringout: (id: number, scene: number) =>
    ["project", id, "scene", scene] as const,

  shot: (id: number, scene: number, shot: number) =>
    ["project", id, "shot", scene, shot] as const,

  job: (jobId: string) => ["job", jobId] as const,
};

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // The archive sleeps and takes half a minute to wake. Data that is a
        // few seconds stale is not a problem here; a screen that refetches
        // everything on every window focus, against a cold database, is.
        staleTime: 15_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          // A 401 or a 404 will not become a 200 by asking again, and retrying
          // one is how a signed-out visitor waits three times for the same
          // refusal.
          if (error instanceof ApiError && error.status < 500 && !error.waking) {
            return false;
          }
          return failureCount < 2;
        },
      },
    },
  });
}

// ---------------------------------------------------------------------------
// Reads
// ---------------------------------------------------------------------------

export function useMe() {
  return useQuery({ queryKey: keys.me(), queryFn: api.me });
}

export function useDashboard() {
  return useQuery({ queryKey: keys.dashboard(), queryFn: api.dashboard });
}

export function useProjectScreen(
  projectId: number,
  filters?: { scene?: number; camera?: string; shoot_day?: string; assignee?: string },
) {
  return useQuery({
    queryKey: keys.projectScreen(projectId, {
      camera: filters?.camera,
      shoot_day: filters?.shoot_day,
      assignee: filters?.assignee,
    }),
    queryFn: () => api.projectScreen(projectId, filters),
    enabled: Number.isFinite(projectId),
  });
}

export function useShotScreen(projectId: number, scene: number, shot: number) {
  return useQuery({
    queryKey: keys.shot(projectId, scene, shot),
    queryFn: () => api.shotScreen(projectId, scene, shot),
    enabled: Number.isFinite(projectId) && Number.isFinite(scene),
  });
}

export function useStringout(projectId: number, scene: number) {
  return useQuery({
    queryKey: keys.stringout(projectId, scene),
    queryFn: () => api.stringout(projectId, scene),
  });
}

// ---------------------------------------------------------------------------
// Writes
// ---------------------------------------------------------------------------

/**
 * What a mutation invalidates.
 *
 * Deciding this per mutation rather than clearing everything: a page that
 * refetches its whole world after each keystroke is a page that spends the
 * archive's wake-up budget on nothing. A shot edit touches the shot, the tree it
 * sits in, and the cross-project queue that counts it.
 */
function useShotInvalidation(projectId: number, scene: number, shot: number) {
  const client = useQueryClient();
  return async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: keys.shot(projectId, scene, shot) }),
      // A prefix, so the tree and the scene assembly both go.
      client.invalidateQueries({ queryKey: keys.project(projectId) }),
      // The count on the dashboard is derived from this shot's status.
      client.invalidateQueries({ queryKey: keys.dashboard() }),
    ]);
  };
}

export function useChooseTake(projectId: number, scene: number, shot: number) {
  const invalidate = useShotInvalidation(projectId, scene, shot);
  return useMutation({
    mutationFn: (input: {
      clip_id: string;
      reason: string;
      in_point_s?: number;
      out_point_s?: number;
    }) => api.select(projectId, scene, shot, input),
    onSuccess: invalidate,
  });
}

export function useUndo(projectId: number, scene: number, shot: number) {
  const invalidate = useShotInvalidation(projectId, scene, shot);
  return useMutation({
    mutationFn: () => api.undo(projectId, scene, shot),
    onSuccess: invalidate,
  });
}

export function useJudge(projectId: number, scene: number, shot: number) {
  const invalidate = useShotInvalidation(projectId, scene, shot);
  return useMutation({
    mutationFn: () => api.judge(projectId, scene, shot),
    onSuccess: invalidate,
  });
}

/**
 * The four edits that carry a revision.
 *
 * `rev` is read from the brief the screen was shown, so a stale page is refused
 * with a 409 rather than silently overwriting whoever edited it meanwhile.
 */
export function useShotEdits(
  projectId: number,
  scene: number,
  shot: number,
  brief: Brief | undefined,
) {
  const invalidate = useShotInvalidation(projectId, scene, shot);
  const rev = brief?.rev;

  const circle = useMutation({
    mutationFn: (take_no: number) =>
      api.circle(projectId, scene, shot, take_no, rev),
    onSuccess: invalidate,
  });

  const assign = useMutation({
    mutationFn: (assignee: string) =>
      api.assign(projectId, scene, shot, assignee, rev),
    onSuccess: invalidate,
  });

  const setState = useMutation({
    mutationFn: (state: ShotState) =>
      api.setState(projectId, scene, shot, state, rev),
    onSuccess: invalidate,
  });

  const saveBrief = useMutation({
    mutationFn: (fields: Parameters<typeof api.saveBrief>[3]) =>
      api.saveBrief(projectId, scene, shot, fields, rev),
    onSuccess: invalidate,
  });

  return { circle, assign, setState, saveBrief };
}

export function useComment(projectId: number, scene: number, shot: number) {
  const invalidate = useShotInvalidation(projectId, scene, shot);

  const add = useMutation({
    mutationFn: (input: Parameters<typeof api.comment>[3]) =>
      api.comment(projectId, scene, shot, input),
    onSuccess: invalidate,
  });

  const resolve = useMutation({
    mutationFn: (commentId: string) =>
      api.resolveComment(projectId, scene, shot, commentId),
    onSuccess: invalidate,
  });

  return { add, resolve };
}

/** What a conflict says, so a screen can name it rather than say "error". */
export function conflictMessage(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  return "Somebody else changed this while you had it open. Reloading their version.";
}
