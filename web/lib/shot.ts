import type { ShotStatus } from "@/lib/api";

/**
 * Whether a shot still wants a person — asked once.
 *
 * This rule was written out twice in the interface, in the rail and in the
 * project overview, and both copies also re-derived it from `segments` after
 * the server had already accounted for them. Three implementations of one
 * question is how the tree came to say "Everything is decided" beside a
 * cockpit asking for a decision and a queue that listed neither.
 *
 * The server decides. `services/assessment.py` is the single rule — it reads
 * the take count, the comparison, the circled take, the set state and the
 * chosen ranges, and returns a status. Everything here does is name which of
 * those statuses mean somebody is needed, and that list is the same list the
 * server's `waiting_reason` is non-null for.
 */
const NEEDS_A_PERSON: ReadonlySet<ShotStatus> = new Set<ShotStatus>([
  // Nothing has compared it yet.
  "not_judged",
  // The call was close enough that a person should look.
  "needs_review",
  // The room circled one take and the measurements chose another.
  "differs_from_circle",
  // Nothing to compare, and nobody has chosen what stands for it. This one
  // used to be treated as settled, which is why a single-take shot could sit
  // unresolved forever without appearing in anybody's queue.
  "too_few_takes",
]);

export function needsAPerson(shot: { status: ShotStatus }): boolean {
  return NEEDS_A_PERSON.has(shot.status);
}

/** How many shots in a list still want somebody. */
export function waitingCount(shots: readonly { status: ShotStatus }[]): number {
  return shots.filter(needsAPerson).length;
}
