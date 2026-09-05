import { describe, expect, it } from "vitest";
import { matches } from "@/components/Upload";

const f = (name: string, size: number, lastModified: number) => ({ name, size, lastModified });

/**
 * Resuming an interrupted ingest.
 *
 * A browser cannot hand a page back its file bytes after a reload, so the
 * saved grant is matched against what the person picks the second time. Get
 * this wrong and footage uploads against another take's slate.
 */
describe("resuming an interrupted batch", () => {
  const saved = [f("A001.mov", 1000, 111), f("A002.mov", 2000, 222)];

  it("resumes when the same files come back", () => {
    expect(matches(saved, [f("A001.mov", 1000, 111), f("A002.mov", 2000, 222)])).toBe(true);
  });

  it("resumes when the picker returns them in another order", () => {
    // A file picker promises no order, so this must be a set comparison.
    expect(matches(saved, [f("A002.mov", 2000, 222), f("A001.mov", 1000, 111)])).toBe(true);
  });

  it("refuses different footage wearing the same filename", () => {
    // The blocker. Same names, different bytes — a re-export, or another
    // card. Accepting this uploads the wrong footage against saved tickets.
    expect(matches(saved, [f("A001.mov", 9999, 111), f("A002.mov", 2000, 222)])).toBe(false);
  });

  it("refuses the same bytes recorded at a different time", () => {
    expect(matches(saved, [f("A001.mov", 1000, 999), f("A002.mov", 2000, 222)])).toBe(false);
  });

  it("refuses a short pick and refuses an extra file", () => {
    expect(matches(saved, [f("A001.mov", 1000, 111)])).toBe(false);
    expect(matches(saved, [...saved, f("A003.mov", 3000, 333)])).toBe(false);
  });

  it("counts duplicates rather than just checking membership", () => {
    // Two identical files is not the same batch as one of them twice over.
    const twice = [f("A001.mov", 1000, 111), f("A001.mov", 1000, 111)];
    expect(matches(twice, twice)).toBe(true);
    expect(matches(twice, [f("A001.mov", 1000, 111), f("A002.mov", 2000, 222)])).toBe(false);
  });

  it("treats two empty batches as a match, and does not crash on them", () => {
    expect(matches([], [])).toBe(true);
  });
});
