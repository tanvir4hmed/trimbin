import { describe, expect, it } from "vitest";
import { draggedRange, rangeDragBounds, type TimelineDrag } from "../lib/timeline-drag";

const drag: TimelineDrag = {
  kind: "out", duration: 100, width: 1000, min: 0, max: 70,
  pointerStart: 493, rangeStart: 20, rangeEnd: 50,
};

describe("shared-clock range dragging", () => {
  it("never collapses a selection into the first safe fragment", () => {
    expect(rangeDragBounds({ from: 10, to: 60 }, [
      { from: 0, to: 15 }, { from: 20, to: 70 },
    ], [])).toBeNull();
    expect(draggedRange({ ...drag, max: 25 }, 494)).toEqual({ from: 20, to: 50 });
  });
  it("rejects overlapping neighbours instead of inventing movement bounds", () => {
    expect(rangeDragBounds({ from: 10, to: 40 }, [{ from: 0, to: 70 }], [
      { from: 30, to: 50 },
    ])).toBeNull();
  });
  it("uses the containing safe interval for different takes and adjacent ranges", () => {
    expect(rangeDragBounds({ from: 20, to: 50 }, [{ from: 15, to: 68 }], [
      { from: 15, to: 20 }, { from: 60, to: 65 },
    ])).toEqual({ min: 20, max: 60 });
  });
  it("does not jump when grabbing inside an edge handle", () => {
    expect(draggedRange(drag, 493)).toEqual({ from: 20, to: 50 });
  });
  it("tracks the mouse at the shared ruler scale, even for shorter takes", () => {
    expect(draggedRange(drag, 593)).toEqual({ from: 20, to: 60 });
  });
  it("left trim preserves the opposite edge and grab offset", () => {
    expect(draggedRange({ ...drag, kind: "in" }, 443)).toEqual({ from: 15, to: 50 });
  });
  it("body movement preserves duration", () => {
    expect(draggedRange({ ...drag, kind: "move" }, 593)).toEqual({ from: 30, to: 60 });
  });
  it("clamps at issue/neighbour boundaries and reverses without incremental drift", () => {
    expect(draggedRange(drag, 993)).toEqual({ from: 20, to: 70 });
    expect(draggedRange(drag, 543)).toEqual({ from: 20, to: 55 });
    expect(draggedRange(drag, 493)).toEqual({ from: 20, to: 50 });
  });
});
