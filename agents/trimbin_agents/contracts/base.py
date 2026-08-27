"""Shared types for every message that crosses an agent boundary.

Nothing passes between agents as free text. Every input and output is validated
against a schema here, because unstructured hand-offs are where multi-agent
systems quietly rot: one agent misreads another, the next acts on it, and the
mistake surfaces hours later with no way to trace it.

Two conventions apply everywhere in this package:

  * Findings carry timecodes. Editors do not choose takes, they choose moments
    inside takes, so "unstable" is useless and "unstable 4.2s-7.8s" is a link
    the interface can act on.

  * Measurements are descriptive, never judgemental. Handheld shake, darkness
    and shallow focus are deliberate choices as often as they are mistakes, so
    nothing here records "bad" - it records what was observed and how it
    compares to the rest of the group.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    """Base for every contract type: unknown fields are an error, not a shrug."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Actor(str, Enum):
    """Who produced a decision. Human choices always outrank agent ones."""

    AGENT = "agent"
    HUMAN = "human"


class Confidence(str, Enum):
    """How much weight a downstream step should give this result.

    UNCERTAIN is a first-class outcome. An agent that cannot answer must say so
    rather than produce something plausible - a wrong reason recorded in the
    archive is worse than no reason at all.
    """

    CONFIDENT = "confident"
    UNCERTAIN = "uncertain"


class Severity(str, Enum):
    NOTE = "note"          # worth knowing, changes nothing
    ATTENTION = "attention"  # a person should look
    BLOCKING = "blocking"  # this take cannot be used as-is


class Provenance(Strict):
    """Stamped onto every row we write.

    Without this, a decision made two years ago is unreadable: you cannot tell
    whether it came from a model you still trust, or which prompt produced it.
    """

    model_id: str = Field(description="e.g. gemini-3.6-flash")
    prompt_version: str = Field(description="e.g. analyst/v3")
    produced_at: datetime
    run_hash: str = Field(
        description=(
            "Hash of (clip set, prompt version, model). Re-running a batch that "
            "failed halfway must not duplicate the work that succeeded."
        )
    )


class TimeRange(Strict):
    """A span within a single clip, in seconds from its start."""

    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)

    def duration_s(self) -> float:
        return self.end_s - self.start_s


class Finding(Strict):
    """One observation about one clip, anchored in time.

    `detail` is written for an editor to read, not for a log file. It states what
    was seen and how it compares to the other takes of the same shot - never a
    verdict. "2.3x the camera movement of the group median" is a fact the editor
    interprets; "too shaky" is an opinion the system has no standing to hold.
    """

    code: str = Field(description="Stable identifier, e.g. 'stability.outlier'")
    detail: str = Field(max_length=200)
    severity: Severity
    where: TimeRange | None = Field(
        default=None,
        description="Omitted when the finding applies to the whole clip.",
    )


class ClipRef(Strict):
    """Agents pass references, never payloads.

    A clip's video may be gigabytes; the message that moves between agents is
    this. Each agent resolves what it needs from storage itself, which keeps
    hand-offs small and every step independently resumable.
    """

    clip_id: UUID
    project_id: int
    group_id: int = Field(description="Scene, in film vocabulary")
    subgroup_id: int = Field(description="Shot, in film vocabulary")
    take_no: int
