"""Boundary and provenance invariants, independent of model judgement."""

from uuid import uuid4

import pytest
from pydantic import ValidationError
from trimbin_agents.contracts.base import TimeRange
from trimbin_agents.contracts.segments import PerformanceAttempt, SegmentObservation

from app.services.attempt_detection import absolute_attempts, consolidate_attempts
from app.services.attempts import AttemptItem, AttemptSave, _dedupe_clean_items
from app.services.full_take import Window


def proposal(start: float, end: float, before=False, after=False):
    return PerformanceAttempt(
        where=TimeRange(start_s=start, end_s=end),
        action="Open door",
        observation="Door opens",
        interpretation="Possible completed pass",
        recommendation="Review ending",
        confidence=0.7,
        intent="unknown",
        starts_before_window=before,
        ends_after_window=after,
    )


def test_same_window_repetitions_keep_distinct_identity():
    window = Window(0, 0, 60)
    observed = SegmentObservation(
        description="Three passes", attempts=[proposal(2, 10), proposal(18, 29), proposal(40, 53)]
    )
    result = consolidate_attempts(absolute_attempts(observed, window, uuid4()), uuid4())
    assert len(result) == 3
    assert len({r["attempt_id"] for r in result}) == 3


def test_continuation_across_window_edges_preserves_full_source_range():
    first = absolute_attempts(
        SegmentObservation(description="Start", attempts=[proposal(2, 60, after=True)]),
        Window(0, 0, 60),
        uuid4(),
    )
    second = absolute_attempts(
        SegmentObservation(description="End", attempts=[proposal(0, 50, before=True)]),
        Window(1, 52, 112),
        uuid4(),
    )
    result = consolidate_attempts(first + second, uuid4())
    assert [(r["start_s"], r["end_s"]) for r in result] == [(2, 102)]
    assert len(result[0]["evidence_segment_ids"]) == 2
    assert not result[0]["ends_after_window"]


def test_boundary_commands_reject_nan_and_duplicate_ids():
    with pytest.raises(ValidationError):
        AttemptItem(id=uuid4(), label="Pass", start_s=0, end_s=float("nan"))
    item = AttemptItem(id=uuid4(), label="Pass", start_s=0, end_s=3)
    with pytest.raises(ValidationError):
        AttemptSave(rev=0, command_id=uuid4(), items=[item, item])


def test_identical_reviewed_clean_ranges_are_one_record():
    first = AttemptItem(id=uuid4(), label="Clean", start_s=18, end_s=46, state="clean")
    duplicate = AttemptItem(id=uuid4(), label="Clean again", start_s=18, end_s=46, state="clean")
    separate = AttemptItem(id=uuid4(), label="Pass", start_s=0, end_s=10, state="reviewed")

    kept = _dedupe_clean_items([first, duplicate, separate])

    assert [item.id for item in kept] == [first.id, separate.id]
