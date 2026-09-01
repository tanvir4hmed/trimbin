"""Contracts for the Assembly Agent.

Assembly turns a verdict into something an editor can use: a span of a take, an
EDL their NLE will open, and a playlist that streams. It is deliberately the
least clever part of the system — the boundary between AI judgement and what a
person sees should be somewhere you can read the arithmetic.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from .base import Finding, Provenance, Strict, TimeRange


class ReviewReason(StrEnum):
    """Why a shot is being handed to a person.

    Named rather than a boolean, because the interface says something different
    for each and an editor deciding what to open first needs to know which kind
    of problem is waiting.
    """

    NARROW_MARGIN = "narrow_margin"  # takes are technically equivalent
    NO_WINNER = "no_winner"  # nothing was good enough
    BLOCKING_FINDING = "blocking"  # the best take still has a problem
    INFERRED_GROUPING = "inferred_grouping"  # the grouping itself may be wrong


class Selection(Strict):
    """One shot's chosen take, and the part of it that will be used."""

    group_id: int
    subgroup_id: int
    clip_id: UUID
    take_no: int

    span: TimeRange = Field(
        description=(
            "The usable portion. Editors choose moments inside takes, so a "
            "selection without a span is not finished work."
        )
    )

    reason: str = Field(max_length=200)
    score: float = Field(ge=0, le=1)
    margin: float = Field(ge=0, le=1)

    findings: list[Finding] = Field(default_factory=list)

    @model_validator(mode="after")
    def _span_must_be_usable(self) -> Selection:
        # A zero or negative span would silently produce an empty segment in the
        # playlist, and the failure would surface as a stall during playback
        # rather than here where it can be explained.
        if self.span.end_s <= self.span.start_s:
            raise ValueError("selection span must have positive duration")
        return self


class ReviewItem(Strict):
    """A shot the system is not willing to decide alone."""

    group_id: int
    subgroup_id: int
    reason: ReviewReason
    detail: str = Field(max_length=200)
    margin: float = Field(ge=0, le=1)
    candidates: list[UUID] = Field(
        description="The takes worth opening, best first. Rarely more than three."
    )


class AssemblyRequest(Strict):
    project_id: int
    group_id: int
    analysis_ids: list[UUID] = Field(
        description="Analysis results to assemble, one per shot in the scene."
    )


class AssemblyResult(Strict):
    project_id: int
    group_id: int

    selections: list[Selection]
    review: list[ReviewItem]

    edl_uri: str = Field(default="", description="EDL written to storage, for the NLE.")
    playlist_uri: str = Field(
        default="",
        description="HLS manifest stitching the selected spans into one stream.",
    )

    provenance: Provenance

    @property
    def auto_decided(self) -> int:
        return len(self.selections) - len(self.review)

    @model_validator(mode="after")
    def _review_items_must_point_somewhere(self) -> AssemblyResult:
        """Every review item has to be actionable.

        Most refer to a shot that was assembled: the editor opens it, sees the
        alternatives, and decides. NO_WINNER is the exception and deliberately
        so — it means nothing in that shot was usable, so there is no selection
        to point at, and that is precisely the case an editor most needs to hear
        about. Requiring a selection would have made the only way to satisfy the
        rule dropping the item, which is how an unusable shot disappears
        silently and turns up in the edit weeks later.
        """
        selected = {(s.group_id, s.subgroup_id) for s in self.selections}
        orphans = [
            (r.group_id, r.subgroup_id)
            for r in self.review
            if r.reason is not ReviewReason.NO_WINNER
            and (r.group_id, r.subgroup_id) not in selected
        ]
        if orphans:
            raise ValueError(f"review items with no selection: {orphans}")

        # A NO_WINNER item still has to name what was rejected, or the editor has
        # nothing to open.
        empty = [
            (r.group_id, r.subgroup_id)
            for r in self.review
            if r.reason is ReviewReason.NO_WINNER and not r.candidates
        ]
        if empty:
            raise ValueError(f"unusable shots with no candidates listed: {empty}")
        return self
