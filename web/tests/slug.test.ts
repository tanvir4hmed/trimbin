import { describe, expect, it } from "vitest";
import { paths, projectIdFromSlug, projectSlug } from "@/lib/slug";

describe("project slugs", () => {
  it("reads as the production, and resolves by the id", () => {
    expect(projectSlug("Kill Bill", 6)).toBe("kill-bill-6");
    expect(projectIdFromSlug("kill-bill-6")).toBe(6);
  });

  it("survives a rename, which is the whole point of the trailing id", () => {
    const before = projectSlug("Kill Bill", 6);
    const after = projectSlug("Kill Bill Vol. 2", 6);
    expect(before).not.toBe(after);
    expect(projectIdFromSlug(before)).toBe(projectIdFromSlug(after));
  });

  it("accepts a bare id, so a hand-typed or older link still opens", () => {
    expect(projectIdFromSlug("6")).toBe(6);
  });

  it("takes the trailing number, not one inside the name", () => {
    expect(projectIdFromSlug(projectSlug("Se7en 1995", 42))).toBe(42);
  });

  it("survives a name with nothing sluggable left in it", () => {
    expect(projectIdFromSlug(projectSlug("!!!", 9))).toBe(9);
    expect(projectIdFromSlug(projectSlug("", 9))).toBe(9);
  });

  it("gives a falsy 0 when there is no id to read, never NaN", () => {
    // I wrote this expecting NaN and the function returns 0. 0 is the better
    // contract and the one the doc comment states: it is falsy, so a caller
    // can guard with `if (!id)`, and it compares equal to itself. NaN does
    // neither. The test was wrong, not the function — but nothing pinned the
    // contract either way until now.
    expect(projectIdFromSlug("kill-bill")).toBe(0);
    expect(projectIdFromSlug("")).toBe(0);
    expect(projectIdFromSlug("kill-bill-")).toBe(0);
  });

  it("builds the same id-bearing path with or without a name", () => {
    expect(projectIdFromSlug(paths.shot(6, 1, 2, "Kill Bill").split("/")[2])).toBe(6);
    expect(projectIdFromSlug(paths.shot(6, 1, 2).split("/")[2])).toBe(6);
  });
});
