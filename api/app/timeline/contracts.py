"""Exact timeline arithmetic; gapless cuts and source-linked audio only."""

from fractions import Fraction
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from ..inference.contracts import Contract


class Rate(Contract):
    numerator: int = Field(gt=0, le=1000000, strict=True)
    denominator: int = Field(gt=0, le=1000000, strict=True)

    @model_validator(mode="after")
    def reduce(self):
        value = self.fraction()
        self.numerator, self.denominator = value.numerator, value.denominator
        return self

    def fraction(self):
        return Fraction(self.numerator, self.denominator)


class Sequence(Contract):
    name: str = Field(default="Film", min_length=1, max_length=100)
    fps: Rate = Field(default_factory=lambda: Rate(numerator=24, denominator=1))
    width: int = Field(default=1920, ge=16, le=8192)
    height: int = Field(default=1080, ge=16, le=8192)
    color: Literal["rec709-sdr"] = "rec709-sdr"
    audio_rate: Literal[48000] = 48000
    conform: Literal["preserve-speed-drop-duplicate-v1"] = "preserve-speed-drop-duplicate-v1"


class Clip(Contract):
    id: UUID
    source_id: UUID
    selection_id: UUID
    in_frame: int = Field(ge=0, strict=True)
    out_frame: int = Field(gt=0, strict=True)
    muted: bool = False
    gain_db: float = Field(default=0, ge=-60, le=0)
    note: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def ordered(self):
        if self.out_frame <= self.in_frame:
            raise ValueError("Out frame must follow In frame")
        return self


class Save(Contract):
    command_id: UUID
    expected_revision: int = Field(ge=0)
    sequence: Sequence
    clips: list[Clip] = Field(max_length=1000)

    @model_validator(mode="after")
    def unique(self):
        if len({c.id for c in self.clips}) != len(self.clips):
            raise ValueError("Each occurrence needs a unique ID")
        return self


def ratio(value: Fraction) -> dict:
    return {"numerator": value.numerator, "denominator": value.denominator}


def nearest(value: Fraction) -> int:
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def conform(clip: Clip, source: dict, sequence: Sequence, start: int) -> dict:
    fps = Fraction(**source["fps"])
    if clip.out_frame > source["frame_count"]:
        raise ValueError("Source range exceeds verified frame count")
    duration = Fraction(clip.out_frame - clip.in_frame) / fps
    frames = nearest(duration * sequence.fps.fraction())
    if frames < 1:
        raise ValueError("Range rounds to zero sequence frames")
    delta = Fraction(frames) / sequence.fps.fraction() - duration
    return {
        **clip.model_dump(mode="json"),
        "source": source,
        "start_frame": start,
        "duration_frames": frames,
        "quantization_seconds": ratio(delta),
    }


def source_frame(occurrence: dict, sequence: Sequence, frame: int) -> int:
    if not 0 <= frame < occurrence["duration_frames"]:
        raise ValueError("Sequence frame outside occurrence")
    offset = Fraction(frame) * Fraction(**occurrence["source"]["fps"]) / sequence.fps.fraction()
    return min(
        occurrence["out_frame"] - 1, occurrence["in_frame"] + offset.numerator // offset.denominator
    )
