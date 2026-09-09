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

type Interval = { from: number; to: number };

export function rangeDragBounds(range: Interval, safe: Interval[], others: Interval[]) {
  // A partially intersecting safe interval is NOT a resize boundary: clamping
  // a long selection into its first fragment makes it collapse on pointermove.
  const containing = safe.find((item) => item.from <= range.from && item.to >= range.to);
  if (!containing || others.some((item) => item.from < range.to && range.from < item.to))
    return null;
  return {
    min: others.filter((item) => item.to <= range.from)
      .reduce((edge, item) => Math.max(edge, item.to), containing.from),
    max: others.filter((item) => item.from >= range.to)
      .reduce((edge, item) => Math.min(edge, item.from), containing.to),
  };
}

// Use the same shared clock as rendering, and preserve the exact grab offset.
// Every event is relative to pointer-down, never to the previous rendered range.
export function draggedRange(drag: TimelineDrag, pointerX: number) {
  // Never silently repair stale/conflicting selections during a drag gesture.
  if (drag.width <= 0 || drag.min > drag.rangeStart || drag.max < drag.rangeEnd)
    return { from: drag.rangeStart, to: drag.rangeEnd };
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
