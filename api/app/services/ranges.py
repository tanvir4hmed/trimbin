"""Which part of a take is safe to use.

The first thing this product promises, and the one that changes what an editor
does. A take with a focus miss at six seconds is not a bad take — it is sixty
good seconds and two bad ones, and the difference between those two readings is
whether the footage gets used.

So nothing here rejects a take. It subtracts the spans that carry risk and hands
back what is left, and where nothing is left it says so rather than inventing a
range.

Two things this deliberately does not do:

It does not decide where a cut goes. The safe range is the material an editor
may draw from; choosing the moment inside it is a story question.

It does not trim on the model's word alone. A finding a model observed and a
finding ffmpeg measured are treated differently — see SUBTRACTED below.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Codes that remove time from the usable range.
#
# Narrow on purpose. Everything else is worth telling an editor about and not
# worth cutting on their behalf: "the camera moved more here" is a note, and
# subtracting it would quietly discard the handheld energy someone chose.
#
# What is here has one thing in common — the footage carries no usable image or
# no usable line at all during the span. Frozen, black, out of focus, or the
# board still in shot.
SUBTRACTED = frozenset(
    {
        "clip.black",
        "frames.frozen",
        "focus.lost",
        "slate.present",
        "action.pre_roll",
        "action.post_roll",
    }
)

# Findings the panel observed that also remove time.
#
# Kept separate from the measured ones because the evidence is different in
# kind. ffmpeg either detected a frozen frame or it did not; a model saying a
# boom entered frame is an observation that can be wrong. Both are subtracted,
# but a range built only from model findings is marked as such so an editor
# knows which claim they are trusting.
OBSERVED_SUBTRACTED = frozenset(
    {
        "frame.boom_visible",
        "frame.crew_visible",
        "frame.subject_exits",
    }
)

# Spans shorter than this are not worth cutting around.
#
# Removing a third of a second leaves two fragments an editor cannot use and a
# range list that is harder to read than the problem it describes.
MIN_GAP_S = 0.4

# What is left has to be long enough to cut.
#
# Below this there is no shot in it — a quarter-second of clean footage is not a
# usable range, it is noise in the list.
MIN_USABLE_S = 1.0


@dataclass(slots=True)
class Range:
    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


def safe_ranges(
    duration_s: float,
    findings: list[dict],
    include_observed: bool = True,
) -> tuple[list[Range], list[str]]:
    """The take, minus the spans nothing can be pulled from.

    Returns the ranges and the codes that removed time, so the interface can say
    *why* a take is shorter than it looks rather than presenting a mysterious
    trim.

    An empty range list is a real answer and means the take is unusable — not
    that the computation failed. That distinction is why this returns a list
    rather than a single range.
    """
    if duration_s <= 0:
        return [], []

    removable = SUBTRACTED | (OBSERVED_SUBTRACTED if include_observed else frozenset())

    blocked: list[Range] = []
    causes: list[str] = []
    for f in findings:
        code = f.get("code")
        if code not in removable:
            continue
        start = max(0.0, float(f.get("start_s") or 0.0))
        end = min(duration_s, float(f.get("end_s") or 0.0))

        # Once the subject exits, the following dead tail is not a second clean
        # performance. Model spans often mark only the exit movement itself;
        # treating their end as a return to usable action offered post-cut room
        # as the primary range. Keep everything before the exit, block through
        # the end of the source.
        if code in {"frame.subject_exits", "action.post_roll"} and start < duration_s:
            end = duration_s

        # A finding with no span applies to the whole take. Those are real —
        # "underexposed throughout" — and the honest reading is that nothing is
        # safe, not that nothing was found.
        if end <= start:
            if start == 0.0 and end == 0.0:
                return [], [str(code)]
            continue

        if end - start < MIN_GAP_S:
            continue

        blocked.append(Range(start, end))
        causes.append(str(code))

    if not blocked:
        return [Range(0.0, duration_s)], []

    return _subtract(duration_s, blocked), sorted(set(causes))


def _subtract(duration_s: float, blocked: list[Range]) -> list[Range]:
    """What is left of the clip once the blocked spans are removed.

    Overlapping spans are merged first. Two findings covering the same seconds —
    a freeze inside a black span, say — would otherwise each punch a hole and
    produce a fragment between them that does not exist.
    """
    merged: list[Range] = []
    for span in sorted(blocked, key=lambda r: r.start_s):
        if merged and span.start_s <= merged[-1].end_s:
            merged[-1].end_s = max(merged[-1].end_s, span.end_s)
        else:
            merged.append(Range(span.start_s, span.end_s))

    safe: list[Range] = []
    cursor = 0.0
    for span in merged:
        if span.start_s - cursor >= MIN_USABLE_S:
            safe.append(Range(round(cursor, 2), round(span.start_s, 2)))
        cursor = max(cursor, span.end_s)

    if duration_s - cursor >= MIN_USABLE_S:
        safe.append(Range(round(cursor, 2), round(duration_s, 2)))

    return safe


def longest(ranges: list[Range]) -> Range | None:
    """The single span an assembly would use if it had to pick one.

    Editors work with the whole list; a stringout needs one contiguous piece per
    take, and the longest clean run is the least surprising choice.
    """
    return max(ranges, key=lambda r: r.duration_s, default=None)
