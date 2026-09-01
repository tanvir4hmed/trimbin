"""Structured observation of one bounded window inside a take."""

from __future__ import annotations

from pydantic import Field

from .base import Finding, Strict


class SegmentObservation(Strict):
    """What is visibly or audibly present in one window.

    Finding timecodes are local to the supplied window. The application adds
    the absolute source offset and clamps them before persistence.
    """

    description: str = Field(
        max_length=500,
        description="Concrete visual summary suitable for footage search.",
    )
    transcript: str = Field(default="", max_length=3000)
    actions: list[str] = Field(default_factory=list, max_length=20)
    objects: list[str] = Field(default_factory=list, max_length=30)
    speakers: list[str] = Field(default_factory=list, max_length=12)
    shot_size: str = Field(default="", max_length=40)
    camera_motion: str = Field(default="", max_length=60)
    findings: list[Finding] = Field(default_factory=list, max_length=30)
