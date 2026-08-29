"""Tests for Assembly.

This is the boundary between AI judgement and what an editor sees, so the things
worth testing are the ones that decide whether a person is told about a problem:
whether a shot with nothing usable still reaches the queue, whether a take with a
jolt in the middle is salvaged rather than discarded, and whether the reason
given is the one that actually needs them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from trimbin_agents.assembly.agent import MIN_USABLE_S, AssemblyAgent
from trimbin_agents.contracts.analysis import AnalysisResult, TakeVerdict
from trimbin_agents.contracts.assembly import AssemblyResult, ReviewItem, ReviewReason, Selection
from trimbin_agents.contracts.base import (
    Confidence,
    Finding,
    Provenance,
    ReasonCode,
    Severity,
    TimeRange,
)


def _provenance() -> Provenance:
    return Provenance(
        model_id="gemini-3.6-flash",
        prompt_version="analyst/v1",
        produced_at=datetime.now(UTC),
        run_hash="abc123",
    )


def _analysis(
    subgroup_id: int = 3,
    winner: UUID | None = None,
    margin: float = 0.4,
    findings: list[Finding] | None = None,
    losers: int = 2,
) -> AnalysisResult:
    winner = winner or uuid4()
    verdicts = [
        TakeVerdict(
            clip_id=winner,
            score=0.9,
            reason="cleanest complete take",
            reason_code=ReasonCode.CLEAN,
            findings=findings or [],
        )
    ]
    verdicts += [
        TakeVerdict(
            clip_id=uuid4(),
            score=0.9 - margin - (i * 0.05),
            reason="behind on measurements",
            reason_code=ReasonCode.BEHIND_ON_MEASUREMENT,
            findings=[],
        )
        for i in range(losers)
    ]
    return AnalysisResult(
        subgroup_id=subgroup_id,
        verdicts=verdicts,
        winner_id=winner,
        margin=margin,
        rationale="…",
        specialist_reports=[],
        confidence=Confidence.CONFIDENT,
        provenance=_provenance(),
    )


class TestUnusableShots:
    def test_a_shot_with_no_usable_take_still_reaches_the_queue(self) -> None:
        """The failure this guards against is silence. A shot where nothing
        worked has no selection to show, and the tempting fix — drop it, since
        it does not fit the cut — is how it surfaces weeks later in the edit."""
        analysis = _analysis()
        analysis = analysis.model_copy(update={"winner_id": None})

        result = AssemblyAgent().assemble(
            project_id=1, group_id=12, analyses=[analysis],
            durations={}, take_numbers={},
        )

        assert not result.selections
        assert len(result.review) == 1
        assert result.review[0].reason is ReviewReason.NO_WINNER

    def test_an_unusable_shot_still_names_what_was_rejected(self) -> None:
        """Without candidates the editor has nothing to open, and the item is a
        notification rather than something they can act on."""
        analysis = _analysis().model_copy(update={"winner_id": None})
        result = AssemblyAgent().assemble(
            project_id=1, group_id=12, analyses=[analysis],
            durations={}, take_numbers={},
        )
        assert result.review[0].candidates

    def test_the_contract_rejects_an_unusable_shot_with_nothing_to_open(self) -> None:
        with pytest.raises(ValidationError, match="no candidates"):
            AssemblyResult(
                project_id=1, group_id=12, selections=[],
                review=[
                    ReviewItem(
                        group_id=12, subgroup_id=3,
                        reason=ReviewReason.NO_WINNER,
                        detail="nothing usable", margin=0.0, candidates=[],
                    )
                ],
                provenance=_provenance(),
            )


class TestSpans:
    def test_head_and_tail_are_trimmed(self) -> None:
        """The slate being pulled and the beat before someone calls cut. Left
        in, a clapperboard appears in the middle of the assembled film."""
        winner = uuid4()
        result = AssemblyAgent().assemble(
            project_id=1, group_id=12,
            analyses=[_analysis(winner=winner)],
            durations={winner: 30.0}, take_numbers={winner: 4},
        )
        span = result.selections[0].span
        assert span.start_s > 0
        assert span.end_s < 30.0

    def test_a_jolt_in_the_middle_leaves_a_usable_half(self) -> None:
        """The finding that makes timecodes worth having. A take with a problem
        from 4.2s to 7.8s is not a discarded take — it is twenty usable seconds
        on the far side of it."""
        winner = uuid4()
        analysis = _analysis(
            winner=winner,
            findings=[
                Finding(
                    code="stability.outlier",
                    detail="2.3x the group median",
                    severity=Severity.ATTENTION,
                    where=TimeRange(start_s=4.2, end_s=7.8),
                )
            ],
        )
        result = AssemblyAgent().assemble(
            project_id=1, group_id=12, analyses=[analysis],
            durations={winner: 30.0}, take_numbers={winner: 4},
        )
        span = result.selections[0].span
        # The longer side of the problem, not the shorter.
        assert span.start_s >= 7.8
        assert span.end_s - span.start_s > 15

    def test_a_note_does_not_move_the_span(self) -> None:
        """Notes are worth knowing and change nothing. Trimming around every
        observation would shave takes down to nothing."""
        winner = uuid4()
        analysis = _analysis(
            winner=winner,
            findings=[
                Finding(
                    code="exposure.under",
                    detail="darkest in the group",
                    severity=Severity.NOTE,
                    where=TimeRange(start_s=4.0, end_s=8.0),
                )
            ],
        )
        result = AssemblyAgent().assemble(
            project_id=1, group_id=12, analyses=[analysis],
            durations={winner: 30.0}, take_numbers={winner: 4},
        )
        assert result.selections[0].span.start_s < 4.0

    def test_a_very_short_take_is_handed_over_whole(self) -> None:
        """Trimming a two second take leaves a fragment. Better to hand the
        whole thing to a person than to emit something unusable."""
        winner = uuid4()
        result = AssemblyAgent().assemble(
            project_id=1, group_id=12,
            analyses=[_analysis(winner=winner)],
            durations={winner: 2.0}, take_numbers={winner: 1},
        )
        span = result.selections[0].span
        assert span.end_s - span.start_s >= MIN_USABLE_S or span.start_s == 0.0

    def test_a_zero_length_span_says_so(self) -> None:
        """Accepted, not refused, and it means "throughout".

        Refusing it was the second attempt and it broke the call outright:
        `gt=0` becomes exclusiveMinimum in the response schema, which Vertex
        does not accept, so the specialist failed with an error about the schema
        rather than about the answer.

        The model cannot do better than this on its own — it never sees the
        clip's duration. So the shape stays permissive and the meaning is
        restored by the caller, which knows."""
        assert TimeRange(start_s=5.0, end_s=5.0).is_empty()

    def test_a_real_span_is_not_empty(self) -> None:
        assert not TimeRange(start_s=4.2, end_s=7.8).is_empty()

    def test_a_whole_take_is_a_real_span(self) -> None:
        """Zero to the clip's length is the answer for something that runs
        throughout — an answer, not the absence of one."""
        whole = TimeRange(start_s=0.0, end_s=70.0)
        assert not whole.is_empty()
        assert whole.duration_s() == 70.0


class TestReviewReasons:
    def test_a_narrow_margin_asks_for_a_person(self) -> None:
        winner = uuid4()
        result = AssemblyAgent().assemble(
            project_id=1, group_id=12,
            analyses=[_analysis(winner=winner, margin=0.03)],
            durations={winner: 30.0}, take_numbers={winner: 4},
        )
        assert result.review[0].reason is ReviewReason.NARROW_MARGIN

    def test_a_clear_winner_asks_for_nobody(self) -> None:
        """The product's central claim: most shots need no attention at all."""
        winner = uuid4()
        result = AssemblyAgent().assemble(
            project_id=1, group_id=12,
            analyses=[_analysis(winner=winner, margin=0.5)],
            durations={winner: 30.0}, take_numbers={winner: 4},
        )
        assert not result.review
        assert result.auto_decided == 1

    def test_a_blocking_finding_outranks_a_narrow_margin(self) -> None:
        """Both are true at once here. The editor scanning a queue needs the
        reason that actually needs them, not the first one checked."""
        winner = uuid4()
        analysis = _analysis(
            winner=winner,
            margin=0.02,
            findings=[
                Finding(
                    code="frames.dropped",
                    detail="3 dropped frames",
                    severity=Severity.BLOCKING,
                    where=TimeRange(start_s=0.0, end_s=10.0),
                )
            ],
        )
        result = AssemblyAgent().assemble(
            project_id=1, group_id=12, analyses=[analysis],
            durations={winner: 30.0}, take_numbers={winner: 4},
        )
        assert result.review[0].reason is ReviewReason.BLOCKING_FINDING

    def test_an_inferred_grouping_is_worth_confirming(self) -> None:
        """A confident verdict about takes that may not belong together is a
        confident answer to the wrong question."""
        winner = uuid4()
        result = AssemblyAgent().assemble(
            project_id=1, group_id=12,
            analyses=[_analysis(subgroup_id=7, winner=winner, margin=0.6)],
            durations={winner: 30.0}, take_numbers={winner: 4},
            inferred_groupings={7},
        )
        assert result.review[0].reason is ReviewReason.INFERRED_GROUPING

    def test_the_queue_is_ordered_by_how_close_the_call_was(self) -> None:
        """Closest first: those are the shots where the system is least sure and
        a person adds the most."""
        winners = [uuid4() for _ in range(3)]
        analyses = [
            _analysis(subgroup_id=1, winner=winners[0], margin=0.10),
            _analysis(subgroup_id=2, winner=winners[1], margin=0.02),
            _analysis(subgroup_id=3, winner=winners[2], margin=0.07),
        ]
        result = AssemblyAgent().assemble(
            project_id=1, group_id=12, analyses=analyses,
            durations={w: 30.0 for w in winners},
            take_numbers={w: 1 for w in winners},
        )
        margins = [r.margin for r in result.review]
        assert margins == sorted(margins)
