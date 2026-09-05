import { describe, expect, it } from "vitest";
import { type AskMatch, state } from "@/components/AskArchive";

const match = (over: Partial<AskMatch> = {}): AskMatch => ({
  clip_id: "c", group_id: 1, subgroup_id: 1, take_no: 1,
  outcome: "selected", reason: "", decided_by: "agent", actor: "",
  description: "", duration_s: 0, playlist_uri: "", where: null,
  play_from_s: 0, relevance: 0, ...over,
});

/**
 * The QA blocker in one function.
 *
 * Search returned a take labelled *selected · by the panel* while the cockpit
 * said it had never been compared. Two faults compounded: the query defaulted
 * a missing Enum to `selected`, and this attributed that phantom to a panel.
 * A suggestion is not a choice, and no decision at all is neither.
 */
describe("what the archive actually knows", () => {
  it("says no decision was recorded rather than inventing one", () => {
    const s = state(match({ outcome: "analysed" }));
    expect(s.label).toBe("analysed");
    expect(s.who).toBe("no decision recorded");
  });

  it("never attributes anything to a panel", () => {
    for (const m of [
      match({ outcome: "analysed" }),
      match({ outcome: "selected", decided_by: "agent" }),
      match({ outcome: "rejected", decided_by: "agent" }),
      match({ outcome: "selected", decided_by: "human", actor: "dipon" }),
    ]) {
      expect(state(m).who).not.toContain("panel");
    }
  });

  it("distinguishes a machine suggestion from a person's call", () => {
    expect(state(match({ decided_by: "agent" })).label).toBe("AI suggested");
    expect(state(match({ decided_by: "human", actor: "dipon" })).label).toBe("human selected");
  });

  it("names the person who decided, when there is one", () => {
    expect(state(match({ decided_by: "human", actor: "dipon" })).who).toBe("by dipon");
  });

  it("still says a person decided when the name did not survive", () => {
    expect(state(match({ decided_by: "human", actor: "" })).who).toBe("by an editor");
  });

  it("keeps a rejection a rejection", () => {
    const s = state(match({ outcome: "rejected", decided_by: "human", actor: "dipon" }));
    expect(s.label).toBe("human rejected");
    expect(s.tone).toBe("rejected");
  });

  it("gives the five states five distinct labels", () => {
    const labels = new Set([
      state(match({ outcome: "analysed" })).label,
      state(match({ outcome: "selected", decided_by: "agent" })).label,
      state(match({ outcome: "rejected", decided_by: "agent" })).label,
      state(match({ outcome: "selected", decided_by: "human", actor: "a" })).label,
      state(match({ outcome: "rejected", decided_by: "human", actor: "a" })).label,
    ]);
    expect(labels.size).toBe(5);
  });
});
