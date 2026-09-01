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

from .base import ClipRef, Confidence, Finding, Provenance, ReasonCode, Strict


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
    reason_code: ReasonCode = Field(description="For counting. The sentence above is for reading.")
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
    observed_findings: dict[UUID, list[Finding]] = Field(
        default_factory=dict,
        description=(
            "Full-duration findings produced independently per clip. These are "
            "observable technical, continuity, and completion evidence; they "
            "never contain a performance preference."
        ),
    )
    bracket_round: int = Field(default=0, ge=0)
    look_profile: str | None = Field(
        default=None,
        description=(
            "Declared intent for the scene, e.g. 'handheld documentary'. Shifts "
            "how findings are worded; never overrides what was measured."
        ),
    )
    briefing: str = Field(
        default="",
        max_length=4000,
        description=(
            "What the shot was meant to be, if the production said: the slug "
            "line, the action, the dialogue, the script supervisor's continuity "
            "notes.\n\n"
            "Optional, and empty is the normal case. Where it exists it changes "
            "what the panel checks rather than what it concludes — completeness "
            "stops being inferred from majority and becomes a comparison against "
            "intent, which matters most on the shot where every take drifted the "
            "same way and the majority is wrong.\n\n"
            "Written by a person, so it is untrusted input reaching a prompt. It "
            "is rendered with its own guardrail by services/shots.py rather than "
            "interpolated raw."
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
        max_length=700,
        description="How the specialist reports were weighed, in Murch's terms.",
    )
    # 700, not 400. The chief overran 400 on a close call between three takes,
    # and losing the whole verdict because the explanation was two sentences too
    # long is the wrong trade — the explanation is the product. Still capped,
    # because an editor reads this beside the take and a page of prose is not
    # read at all.
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
