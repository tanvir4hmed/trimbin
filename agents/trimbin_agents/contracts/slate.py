"""Contracts for the Slate Agent.

Reading a clapperboard is closer to OCR than to judgement, and the shape of these
types keeps it that way. There is nowhere here to record an opinion about quality,
because that belongs to the Analyst and an agent that can express something will
eventually be asked to.

The distinction that matters most is between a slate that was *read* and a
grouping that was *inferred*. Documentary and music video shoots rarely slate at
all, so inference is a normal path rather than an exceptional one — but an
inference that presents itself as a reading is a lie the editor cannot see
through, and every downstream decision inherits it.
"""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import Field, model_validator

from .base import ClipRef, Confidence, Strict


class GroupingSource(str, Enum):
    """How the take's place in the shoot was established."""

    SLATE = "slate"          # read off the board
    TIMECODE = "timecode"    # inferred from capture time and framing
    FILENAME = "filename"    # inferred from a naming convention
    MANUAL = "manual"        # a person said so, and a person outranks all of these


class SlateRequest(Strict):
    clip_id: UUID
    project_id: int
    storage_uri: str
    captured_at_epoch: float
    duration_s: float

    # Neighbours by capture time, for the fallback path. A take belongs with what
    # was shot around it far more reliably than with anything else available when
    # there is no board to read.
    neighbours: list[ClipRef] = Field(default_factory=list, max_length=20)


class SlateReading(Strict):
    """What was on the board, and what it was taken to mean.

    `raw` is kept separately from the parsed fields because slates are written by
    hand in marker, under time pressure, in bad light. When a parse turns out to
    be wrong months later, the only way to tell whether the board or the reader
    was at fault is to have kept what the board actually said.
    """

    raw: str = Field(default="", max_length=120)
    scene: str = Field(default="")
    shot: str = Field(default="")
    take: int = Field(default=0, ge=0)


class MisplacementProposal(Strict):
    """A clip that looks like it belongs somewhere else.

    A proposal, never an action. Silently moving footage — or worse, discarding
    it — on a similarity score is the single most destructive thing this system
    could do, and similarity is exactly the kind of signal that is right often
    enough to be trusted and wrong often enough to ruin a shoot day.
    """

    better_group_id: int | None = Field(
        default=None,
        description="None when the clip matches nothing in the project at all.",
    )
    better_subgroup_id: int | None = None
    similarity: float = Field(ge=0, le=1)
    detail: str = Field(max_length=200)


class SlateResult(Strict):
    clip_id: UUID
    reading: SlateReading

    # Where this take is proposed to sit.
    group_id: int
    subgroup_id: int
    take_no: int

    source: GroupingSource
    confidence: Confidence

    misplacement: MisplacementProposal | None = None

    model_id: str
    prompt_version: str

    @property
    def slate_confident(self) -> bool:
        """Whether the grouping was read rather than guessed.

        Written to the clip row and surfaced in the upload screen: the editor is
        asked to confirm only the groupings that were inferred, never the whole
        shoot day.
        """
        return self.source in (GroupingSource.SLATE, GroupingSource.MANUAL)

    @model_validator(mode="after")
    def _reading_must_support_its_source(self) -> SlateResult:
        """A result claiming it read a slate has to have read something.

        Without this, a model that finds no board can still return
        source=SLATE with empty fields, and the grouping is then trusted
        downstream as if a human had chalked it.
        """
        if self.source is GroupingSource.SLATE and not self.reading.raw.strip():
            raise ValueError("source=slate requires the raw board text that was read")
        return self
