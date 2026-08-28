"""Tests for the Slate Agent's non-model logic.

The parts worth testing here are the ones that decide whether a grouping is
trusted downstream: whether a slate was genuinely read, how scene letters survive
being turned into numbers, and whether a misplacement is reported as a proposal
rather than acted on. None of these need a model, and all of them are places
where a quiet mistake propagates into every later decision.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from trimbin_agents.contracts.base import ClipRef, Confidence
from trimbin_agents.contracts.slate import (
    GroupingSource,
    SlateReading,
    SlateRequest,
    SlateResult,
)
from trimbin_agents.slate.agent import (
    MISPLACEMENT_RATIO,
    SlateAgent,
    _cosine,
    _infer_from_neighbours,
    _to_ordinal,
    _typical_similarity,
)


def _result(source: GroupingSource, raw: str = "") -> SlateResult:
    return SlateResult(
        clip_id=uuid4(),
        reading=SlateReading(raw=raw, scene="12", shot="3", take=4),
        group_id=1200,
        subgroup_id=300,
        take_no=4,
        source=source,
        confidence=Confidence.CONFIDENT,
        model_id="gemini-3.6-flash",
        prompt_version="slate/v1",
    )


class TestReadingHonesty:
    def test_claiming_to_read_a_slate_requires_having_read_one(self) -> None:
        """Without this, a model that found no board can still return
        source=slate with empty text, and the grouping is trusted downstream as
        though someone had chalked it."""
        with pytest.raises(ValidationError, match="raw board text"):
            _result(GroupingSource.SLATE, raw="")

    def test_inference_needs_no_board(self) -> None:
        result = _result(GroupingSource.TIMECODE, raw="")
        assert result.slate_confident is False

    def test_only_read_or_manual_groupings_are_confident(self) -> None:
        """The upload screen asks an editor to confirm inferred groupings and
        leaves read ones alone, so this flag decides how much of a shoot day a
        person has to look at."""
        assert _result(GroupingSource.SLATE, raw="12/3/4").slate_confident is True
        assert _result(GroupingSource.MANUAL, raw="").slate_confident is True
        assert _result(GroupingSource.TIMECODE, raw="").slate_confident is False
        assert _result(GroupingSource.FILENAME, raw="").slate_confident is False


class TestSlateNumbering:
    def test_letters_survive(self) -> None:
        """Scene 12 and scene 12A are different setups a production named apart.
        Dropping the letter merges them, and the merge is invisible afterwards."""
        assert _to_ordinal("12") != _to_ordinal("12A")

    def test_ordering_is_preserved(self) -> None:
        assert _to_ordinal("12") < _to_ordinal("12A") < _to_ordinal("12B") < _to_ordinal("13")

    def test_missing_field_does_not_raise(self) -> None:
        """An unreadable board leaves fields empty, and that path must not throw
        — it is the ordinary case on an unslated shoot."""
        assert _to_ordinal("") == 0


class TestNeighbourInference:
    def test_take_number_continues_the_group(self) -> None:
        group = [
            ClipRef(clip_id=uuid4(), project_id=1, group_id=1200, subgroup_id=300, take_no=n)
            for n in (1, 2, 3)
        ]
        request = SlateRequest(
            clip_id=uuid4(), project_id=1, storage_uri="gs://x",
            captured_at_epoch=0.0, duration_s=30.0, neighbours=group,
        )
        assert _infer_from_neighbours(request) == (1200, 300, 4)

    def test_first_clip_of_a_shoot_has_no_neighbours(self) -> None:
        request = SlateRequest(
            clip_id=uuid4(), project_id=1, storage_uri="gs://x",
            captured_at_epoch=0.0, duration_s=30.0, neighbours=[],
        )
        assert _infer_from_neighbours(request) == (0, 0, 1)


class TestMisplacement:
    """Group-relative, because absolute similarity does not separate anything.

    On real footage every clip in a production scores 0.91-0.98 against every
    group in it — same room, same light, same actors. What separates a stray is
    scoring low *for that group*, and these fixtures are built to mirror that:
    tightly clustered members, and an intruder that is still close in absolute
    terms but loose relative to the cluster.
    """

    @staticmethod
    def _clip(group: int = 1, subgroup: int = 1) -> ClipRef:
        return ClipRef(
            clip_id=uuid4(), project_id=1,
            group_id=group, subgroup_id=subgroup, take_no=1,
        )

    # A tight group and a looser one, both in the high nineties against each
    # other, exactly as two setups on one scene behave.
    TIGHT = [
        [1.0, 0.02, 0.0],
        [1.0, 0.00, 0.02],
        [1.0, 0.01, 0.01],
    ]
    OTHER = [
        [1.0, 0.30, 0.0],
        [1.0, 0.32, 0.0],
        [1.0, 0.31, 0.0],
    ]

    async def test_a_clip_that_fits_is_left_alone(self) -> None:
        agent = SlateAgent.__new__(SlateAgent)
        member = [1.0, 0.01, 0.005]
        proposal = await agent.check_placement(
            self._clip(), member, {(1, 1): [*self.TIGHT, member], (2, 1): self.OTHER}
        )
        assert proposal is None

    async def test_a_stray_is_proposed_not_moved(self) -> None:
        """A suggestion with a reason an editor can read. Similarity is right
        often enough to trust and wrong often enough to ruin a shoot day, so
        nothing here moves footage."""
        agent = SlateAgent.__new__(SlateAgent)
        stray = [1.0, 0.31, 0.0]  # belongs with OTHER, filed with TIGHT
        proposal = await agent.check_placement(
            self._clip(group=1), stray, {(1, 1): [*self.TIGHT, stray], (2, 1): self.OTHER}
        )
        assert proposal is not None
        assert proposal.better_group_id == 2
        assert "scene 2" in proposal.detail

    async def test_absolute_similarity_stays_high_even_for_a_stray(self) -> None:
        """The reason the old absolute threshold never fired. A stray still
        matches its wrong group in the nineties; only the ratio gives it away."""
        agent = SlateAgent.__new__(SlateAgent)
        stray = [1.0, 0.31, 0.0]
        proposal = await agent.check_placement(
            self._clip(group=1), stray, {(1, 1): [*self.TIGHT, stray], (2, 1): self.OTHER}
        )
        assert proposal is not None
        assert proposal.similarity > 0.9

    async def test_a_group_too_small_to_have_a_typical_score(self) -> None:
        """Two members give a median of two numbers, which one unusual take
        dominates. Saying nothing beats saying something unfounded."""
        agent = SlateAgent.__new__(SlateAgent)
        stray = [0.0, 0.0, 1.0]
        proposal = await agent.check_placement(
            self._clip(), stray, {(1, 1): [self.TIGHT[0], stray], (2, 1): self.OTHER}
        )
        assert proposal is None

    async def test_a_lone_group_has_nothing_to_compare_against(self) -> None:
        agent = SlateAgent.__new__(SlateAgent)
        proposal = await agent.check_placement(
            self._clip(), [0.0, 0.0, 1.0], {(1, 1): self.TIGHT}
        )
        assert proposal is None

    async def test_the_clip_is_never_compared_against_itself(self) -> None:
        """A clip inside its own group's centroid always matches it, and the
        stranger it is the harder it pulls the centroid its way. Including it
        would make the check quietest exactly when it should speak."""
        agent = SlateAgent.__new__(SlateAgent)
        stray = [1.0, 0.31, 0.0]

        with_itself = await agent.check_placement(
            self._clip(group=1), stray, {(1, 1): [*self.TIGHT, stray], (2, 1): self.OTHER}
        )
        without_itself = await agent.check_placement(
            self._clip(group=1), stray, {(1, 1): self.TIGHT, (2, 1): self.OTHER}
        )
        assert with_itself is not None
        assert without_itself is not None
        assert with_itself.similarity == pytest.approx(without_itself.similarity)


class TestTypicalSimilarity:
    def test_a_tight_group_scores_near_one(self) -> None:
        assert _typical_similarity(TestMisplacement.TIGHT) > 0.99

    def test_a_single_member_has_no_yardstick(self) -> None:
        """One member left out leaves nothing to compare against."""
        assert _typical_similarity([[1.0, 0.0, 0.0]]) == 0.0

    def test_a_scattered_group_scores_lower_than_a_tight_one(self) -> None:
        scattered = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        assert _typical_similarity(scattered) < _typical_similarity(TestMisplacement.TIGHT)

    def test_the_ratio_constant_is_a_ratio_not_a_cosine(self) -> None:
        """Guards the regression this replaced: 0.62 as an absolute cosine
        never fired, because nothing in a real production scores that low."""
        assert 0.9 < MISPLACEMENT_RATIO < 1.0


class TestCosine:
    def test_mismatched_lengths_do_not_raise(self) -> None:
        """An un-embedded clip carries a zero vector of a different shape at
        worst; ingest must not die on it."""
        assert _cosine([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0

    def test_zero_vector_matches_nothing(self) -> None:
        """This is what "not embedded yet" looks like, and it must score zero
        rather than dividing by zero."""
        assert _cosine([0.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == 0.0
