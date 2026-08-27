"""Contracts for the Analyst panel.

The panel is structured like a real edit room: three specialists report on what
they can each actually know, and a chief weighs those reports against Murch's
priority order. A single prompt asked to judge technical quality, continuity and
performance at once does all three badly.

The specialists never rank. Ranking is the chief's job, and the chief is allowed
to decline.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import Field, model_validator

from .base import ClipRef, Confidence, Finding, Provenance, Strict


class Measurements(Strict):
    """Computed by ffmpeg, not inferred by a model.

    Every value is normalised against the other takes of the same shot. An
    absolute threshold would reject a deliberately handheld scene wholesale; a
    group-relative one asks the only question that matters - is this take unlike
    its siblings?

    1.0 means "at the group median". Higher means more of the thing named.
    """

    exposure_rel: float = Field(description="Deviation from group median exposure")
    clipping_pct: float = Field(ge=0, le=100, description="Blown or crushed pixels")
    sharpness_rel: float = Field(description="Focus, relative to the group")
    motion_rel: float = Field(description="Camera movement, relative to the group")
    audio_lufs: float = Field(description="Integrated loudness, EBU R128")
    noise_floor_db: float
    duration_s: float = Field(gt=0)
    dropped_frames: int = Field(ge=0)


class SpecialistReport(Strict):
    """One specialist's view of one clip. Observations only."""

    clip_id: UUID
    findings: list[Finding]
    confidence: Confidence
    summary: str = Field(
        max_length=200,
        description="One sentence an editor would recognise as their own language.",
    )


class TakeVerdict(Strict):
    """The chief's position on a single take."""

    clip_id: UUID
    score: float = Field(
        ge=0,
        le=1,
        description=(
            "Technical cleanliness and completeness only. This is explicitly not "
            "a judgement of performance."
        ),
    )
    reason: str = Field(max_length=200)
    reason_code: str
    findings: list[Finding]


class AnalysisRequest(Strict):
    """All takes of one shot, compared against each other in one context.

    Gemini accepts at most ten videos per request while shots can run to twenty
    takes, so larger groups arrive here already bracketed - compared in rounds,
    winners advancing. `bracket_round` records which pass produced this result so
    the archive can reconstruct how a winner was reached.
    """

    clips: list[ClipRef] = Field(min_length=1, max_length=8)
    measurements: dict[UUID, Measurements]
    bracket_round: int = Field(default=0, ge=0)
    look_profile: str | None = Field(
        default=None,
        description=(
            "Declared intent for the scene, e.g. 'handheld documentary'. Shifts "
            "how findings are worded; never overrides what was measured."
        ),
    )


class AnalysisResult(Strict):
    """The chief's verdict, with the reasoning it rests on."""

    subgroup_id: int
    verdicts: list[TakeVerdict]
    winner_id: UUID | None = Field(
        description=(
            "None when no take is good enough. Forcing a winner out of a bad "
            "group is worse than reporting that the shot needs attention."
        )
    )
    margin: float = Field(
        ge=0,
        le=1,
        description=(
            "Gap between first and second place. Below the review threshold the "
            "shot goes to a person - at that point the decision has become an "
            "emotional one, and that is not ours to make."
        ),
    )
    rationale: str = Field(
        max_length=400,
        description="How the specialist reports were weighed, in Murch's terms.",
    )
    specialist_reports: list[SpecialistReport]
    confidence: Confidence
    provenance: Provenance

    @model_validator(mode="after")
    def _winner_must_be_a_candidate(self) -> AnalysisResult:
        if self.winner_id is None:
            return self
        if self.winner_id not in {v.clip_id for v in self.verdicts}:
            raise ValueError("winner_id must refer to a clip that was judged")
        return self
