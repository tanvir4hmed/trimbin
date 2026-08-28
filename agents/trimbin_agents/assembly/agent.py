"""Assembly: turn verdicts into a cut, an EDL, and a stream.

The deliberately boring agent. Almost everything here is arithmetic, and that is
the point — this sits between AI judgement and what an editor sees, and a
boundary you can read the arithmetic of is what makes the rest trustworthy.

No model is called for anything a query can answer. Ranking, thresholds and
duration maths are not judgement, and asking a language model to compare two
numbers is slower, dearer and less reliable than comparing two numbers.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from ..config import settings
from ..contracts.analysis import AnalysisResult
from ..contracts.assembly import AssemblyResult, ReviewItem, ReviewReason, Selection
from ..contracts.base import Provenance, Severity, TimeRange

log = logging.getLogger(__name__)

PROMPT_VERSION = "assembly/v1"

# Trimmed from the head of every take: the slate being pulled, the settle, the
# pause before someone calls action. Editors cut this off by reflex, and leaving
# it in would put a clapperboard in the middle of the assembled cut.
HEAD_TRIM_S = 1.0

# And from the tail: the beat after the action ends, before the camera stops.
TAIL_TRIM_S = 0.7

# Below this, trimming has taken more than it should and the take is better left
# whole for a person to judge.
MIN_USABLE_S = 1.5


class AssemblyAgent:
    """Applies verdicts. Holds no model client, because it needs none."""

    def assemble(
        self,
        project_id: int,
        group_id: int,
        analyses: list[AnalysisResult],
        durations: dict[UUID, float],
        take_numbers: dict[UUID, int],
        inferred_groupings: set[int] | None = None,
    ) -> AssemblyResult:
        inferred = inferred_groupings or set()
        selections: list[Selection] = []
        review: list[ReviewItem] = []

        for analysis in analyses:
            selection = self._select(analysis, group_id, durations, take_numbers)
            if selection is None:
                # Nothing here was usable. There is no selection to put in the
                # cut, but the shot is exactly what an editor most needs to hear
                # about — an unusable shot that vanishes quietly turns up in the
                # edit weeks later when nothing can be done about it.
                review.append(
                    ReviewItem(
                        group_id=group_id,
                        subgroup_id=analysis.subgroup_id,
                        reason=ReviewReason.NO_WINNER,
                        detail="No take in this shot was usable.",
                        margin=0.0,
                        candidates=[v.clip_id for v in analysis.verdicts[:3]],
                    )
                )
                continue

            selections.append(selection)

            if item := self._needs_review(analysis, selection, group_id, inferred):
                review.append(item)

        log.info(
            "scene %d: %d selected, %d for review",
            group_id, len(selections), len(review),
        )

        return AssemblyResult(
            project_id=project_id,
            group_id=group_id,
            selections=sorted(selections, key=lambda s: s.subgroup_id),
            review=sorted(review, key=lambda r: r.margin),
            provenance=Provenance(
                model_id="none",
                prompt_version=PROMPT_VERSION,
                produced_at=datetime.now(UTC),
                run_hash=f"{abs(hash((project_id, group_id, len(analyses)))):016x}",
            ),
        )

    def _select(
        self,
        analysis: AnalysisResult,
        group_id: int,
        durations: dict[UUID, float],
        take_numbers: dict[UUID, int],
    ) -> Selection | None:
        if analysis.winner_id is None:
            return None

        winner = next(
            (v for v in analysis.verdicts if v.clip_id == analysis.winner_id), None
        )
        if winner is None:
            return None

        duration = durations.get(analysis.winner_id, 0.0)
        span = self._span_for(duration, winner.findings)
        if span is None:
            return None

        return Selection(
            group_id=group_id,
            subgroup_id=analysis.subgroup_id,
            clip_id=analysis.winner_id,
            take_no=take_numbers.get(analysis.winner_id, 0),
            span=span,
            reason=winner.reason,
            score=winner.score,
            margin=analysis.margin,
            findings=winner.findings,
        )

    def _span_for(self, duration_s: float, findings: list) -> TimeRange | None:
        """Where the usable material is.

        Starts from the take minus its head and tail, then avoids any timecoded
        problem if a clean run survives. Trimbin does not offer a trimming
        interface — this marks where the material is and hands that to the NLE,
        which is better at trimming than anything built here would be.
        """
        if duration_s <= 0:
            return None

        start = min(HEAD_TRIM_S, duration_s * 0.15)
        end = max(start, duration_s - min(TAIL_TRIM_S, duration_s * 0.1))

        if end - start < MIN_USABLE_S:
            # Trimming has eaten the take. Better to hand over the whole thing
            # and let a person look than to emit a fragment.
            return TimeRange(start_s=0.0, end_s=duration_s)

        problems = sorted(
            (f.where for f in findings if f.where and f.severity is not Severity.NOTE),
            key=lambda w: w.start_s,
        )
        if not problems:
            return TimeRange(start_s=start, end_s=end)

        # Take the longest stretch that avoids every flagged span. A take with a
        # jolt in the middle usually has a usable half either side, and finding
        # it is the difference between discarding the take and using it.
        best = self._longest_clear_run(start, end, problems)
        if best and best.end_s - best.start_s >= MIN_USABLE_S:
            return best

        # Nothing clean survives, so hand the trimmed take over with its findings
        # attached rather than pretending a clear run exists.
        return TimeRange(start_s=start, end_s=end)

    @staticmethod
    def _longest_clear_run(
        start: float, end: float, problems: list[TimeRange]
    ) -> TimeRange | None:
        gaps: list[TimeRange] = []
        cursor = start

        for problem in problems:
            if problem.start_s > cursor:
                gaps.append(TimeRange(start_s=cursor, end_s=min(problem.start_s, end)))
            cursor = max(cursor, problem.end_s)

        if cursor < end:
            gaps.append(TimeRange(start_s=cursor, end_s=end))

        usable = [g for g in gaps if g.end_s > g.start_s]
        return max(usable, key=lambda g: g.end_s - g.start_s) if usable else None

    def _needs_review(
        self,
        analysis: AnalysisResult,
        selection: Selection,
        group_id: int,
        inferred: set[int],
    ) -> ReviewItem | None:
        """Whether a person should look at this shot.

        Order matters: a blocking finding on the winner is a worse problem than
        a narrow margin, and an editor scanning the queue should see the reason
        that actually needs them.
        """
        candidates = [
            v.clip_id
            for v in sorted(analysis.verdicts, key=lambda v: v.score, reverse=True)[:3]
        ]

        blocking = [f for f in selection.findings if f.severity is Severity.BLOCKING]
        if blocking:
            return ReviewItem(
                group_id=group_id,
                subgroup_id=analysis.subgroup_id,
                reason=ReviewReason.BLOCKING_FINDING,
                detail=f"Best take still has a problem: {blocking[0].detail}",
                margin=analysis.margin,
                candidates=candidates,
            )

        if analysis.subgroup_id in inferred:
            return ReviewItem(
                group_id=group_id,
                subgroup_id=analysis.subgroup_id,
                reason=ReviewReason.INFERRED_GROUPING,
                detail="Grouping was inferred rather than read from a slate.",
                margin=analysis.margin,
                candidates=candidates,
            )

        if analysis.margin < settings.review_margin:
            return ReviewItem(
                group_id=group_id,
                subgroup_id=analysis.subgroup_id,
                reason=ReviewReason.NARROW_MARGIN,
                detail=(
                    f"Top two takes are within {analysis.margin:.0%}; "
                    "the decision is an editorial one."
                ),
                margin=analysis.margin,
                candidates=candidates,
            )

        return None
