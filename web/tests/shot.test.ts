import { describe, expect, it } from "vitest";
import { needsAPerson, waitingCount } from "@/lib/shot";
import type { ShotStatus } from "@/lib/api";

const shot = (status: ShotStatus) => ({ status });

describe("does a shot still want somebody", () => {
  it("counts a shot nothing has compared yet", () => {
    expect(needsAPerson(shot("not_judged"))).toBe(true);
  });

  it("counts a single-take shot nobody has chosen for", () => {
    // Treated as settled once, which is how a one-take shot could sit
    // unresolved forever without appearing in anybody's queue.
    expect(needsAPerson(shot("too_few_takes"))).toBe(true);
  });

  it("counts a call that went against the circled take", () => {
    expect(needsAPerson(shot("differs_from_circle"))).toBe(true);
  });

  it("leaves a decided shot alone", () => {
    expect(needsAPerson(shot("decided"))).toBe(false);
  });

  it("gives the tree and the overview one number, not three", () => {
    const scene = [shot("decided"), shot("not_judged"), shot("too_few_takes")];
    expect(waitingCount(scene)).toBe(2);
  });

  it("is zero when everything is decided, and says so honestly", () => {
    expect(waitingCount([shot("decided"), shot("confirmed")])).toBe(0);
    expect(waitingCount([])).toBe(0);
  });

  it("has an answer for every status the server can send", () => {
    // Exhaustive on purpose. A status added to the API and not considered here
    // silently falls through to "nobody is needed", which is the failure this
    // whole module exists to stop: a shot that wants a decision and appears in
    // no queue. If this list stops matching ShotStatus, tsc fails on the
    // annotation and somebody has to make the call deliberately.
    const every: Record<ShotStatus, boolean> = {
      not_judged: true,
      needs_review: true,
      differs_from_circle: true,
      too_few_takes: true,
      decided: false,
      confirmed: false,
    };
    for (const [status, expected] of Object.entries(every)) {
      expect(needsAPerson(shot(status as ShotStatus))).toBe(expected);
    }
  });
});
