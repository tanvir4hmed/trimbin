export type TimelineDrag = {
  kind: "in" | "out" | "move";
  duration: number;
  width: number;
  min: number;
  max: number;
  pointerStart: number;
  rangeStart: number;
  rangeEnd: number;
};

// Use the same shared clock as rendering, and preserve the exact grab offset.
// Every event is relative to pointer-down, never to the previous rendered range.
export function draggedRange(drag: TimelineDrag, pointerX: number) {
  const delta = ((pointerX - drag.pointerStart) / drag.width) * drag.duration;
  const tolerance = (4 / drag.width) * drag.duration;
  const snap = (value: number, target: number) =>
    Math.abs(value - target) <= tolerance ? target : value;
  if (drag.kind === "move") {
    const length = drag.rangeEnd - drag.rangeStart;
    const wanted = snap(snap(drag.rangeStart + delta, drag.min), drag.max - length);
    const from = Math.max(drag.min, Math.min(drag.max - length, wanted));
    return { from, to: from + length };
  }
  if (drag.kind === "in") {
    return {
      from: Math.max(drag.min, Math.min(snap(drag.rangeStart + delta, drag.min), drag.rangeEnd - 0.05)),
      to: drag.rangeEnd,
    };
  }
  return {
    from: drag.rangeStart,
    to: Math.min(drag.max, Math.max(snap(drag.rangeEnd + delta, drag.max), drag.rangeStart + 0.05)),
  };
}
