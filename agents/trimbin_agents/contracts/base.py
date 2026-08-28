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


class FindingCode(str, Enum):
    """The closed vocabulary every finding must use.

    Closed because it was open, and an open one produced thirty-nine codes
    across twelve takes with no two specialists agreeing. `dialogue.truncated`,
    `completion.dialogue_incomplete` and `dialogue.completion` all appeared,
    all meaning the same thing.

    Two consequences, both bad. Scoring recognised none of them, so the
    per-criterion breakdown silently reported perfect continuity for every take.
    And the archive stopped being queryable — "show me every take with a
    continuity problem" cannot work when the problem has five spellings, and a
    queryable archive is the point of the product.

    Passed to the model as the response schema, so it selects rather than
    invents. Its own wording survives in `detail`, which is where the useful
    specificity was anyway: the code says what kind of thing, the detail says
    what happened.
    """

    # -- measured, by ffmpeg, deterministic --------------------------------
    FOCUS_SOFT = "focus.soft"
    FOCUS_LOST = "focus.lost"
    MOTION_BLUR = "motion.blur"
    # Two different observations, deliberately kept apart. A shake is a lurch at
    # a timecode inside one take, which ffmpeg detects and an editor can cut
    # around. An outlier is a whole take that moves more than its siblings,
    # which only exists relative to the group and cannot be cut around at all.
    STABILITY_SHAKE = "stability.shake"
    STABILITY_OUTLIER = "stability.outlier"
    EXPOSURE_UNDER = "exposure.under"
    EXPOSURE_OVER = "exposure.over"
    EXPOSURE_CLIPPED = "exposure.clipped"
    WHITE_BALANCE_SHIFT = "white_balance.shift"
    NOISE_HIGH = "noise.high"
    FRAMES_DROPPED = "frames.dropped"
    FRAMES_FROZEN = "frames.frozen"
    CLIP_BLACK = "clip.black"
    CLIP_TOO_SHORT = "clip.too_short"
    AUDIO_CLIPPING = "audio.clipping"
    AUDIO_SILENCE = "audio.silence"
    AUDIO_DROPOUT = "audio.dropout"
    AUDIO_NOISE_FLOOR = "audio.noise_floor"

    # -- observed, by a specialist, and checkable by a person ---------------
    SLATE_PRESENT = "slate.present"
    ACTION_PRE_ROLL = "action.pre_roll"
    ACTION_INCOMPLETE = "action.incomplete"
    DIALOGUE_INCOMPLETE = "dialogue.incomplete"
    DIALOGUE_FLUFFED = "dialogue.fluffed"
    CAMERA_MOVE_SHORT = "camera.move_short"
    CAMERA_FOCUS_PULL_LATE = "camera.focus_pull_late"
    CAMERA_UNMOTIVATED_MOVE = "camera.unmotivated_move"
    FRAME_BOOM_VISIBLE = "frame.boom_visible"
    FRAME_CREW_VISIBLE = "frame.crew_visible"
    FRAME_SHADOW = "frame.shadow"
    FRAME_SUBJECT_EXITS = "frame.subject_exits"
    FRAME_OBSTRUCTION = "frame.obstruction"
    CONTINUITY_PROP = "continuity.prop"
    CONTINUITY_WARDROBE = "continuity.wardrobe"
    CONTINUITY_HAIR = "continuity.hair"
    CONTINUITY_EYELINE = "continuity.eyeline"
    CONTINUITY_SCREEN_DIRECTION = "continuity.screen_direction"
    CONTINUITY_BLOCKING = "continuity.blocking"
    CONTINUITY_LIGHTING = "continuity.lighting"
    CONTINUITY_SET_DRESSING = "continuity.set_dressing"

    # -- described, never scored -------------------------------------------
    # Performance is the 74% of Murch's order that belongs to a person. The
    # observation is kept because an editor may want it; it carries no weight in
    # any score, and having one code rather than a family of them makes that
    # impossible to forget.
    PERFORMANCE_NOTE = "performance.note"

    # -- the escape hatch ---------------------------------------------------
    # Something real that none of the above names. Better than forcing a wrong
    # code onto a true observation, and rare enough that a rising count is a
    # signal the taxonomy needs a new entry rather than noise to ignore.
    OTHER = "other"


class ReasonCode(str, Enum):
    """Why a take was placed where it was, in a form that groups.

    Closed for the same reason FindingCode is. Left open, the chief wrote
    `complete_and_clean`, `clean.take`, `clean_take` and `clean_completion` for
    one idea across four setups, which makes "how often do we reject a take for
    incomplete dialogue?" unanswerable — and that question is the accuracy page.

    The prose reason stays free text beside this. The code is for counting; the
    sentence is for reading.
    """

    # selected
    CLEAN = "selected.clean"                    # nothing separates it but it leads
    COMPLETE = "selected.complete"              # it finishes where others do not
    CONTINUITY_MATCH = "selected.continuity"    # it matches the group where others drift

    # not selected
    BEHIND_ON_MEASUREMENT = "behind.measurement"   # the numbers put it second
    INCOMPLETE = "behind.incomplete"               # action or dialogue stops short
    CONTINUITY_DRIFT = "behind.continuity"         # differs from the group
    FRAMING = "behind.framing"                     # obstruction, crop, composition
    TECHNICAL_FAULT = "behind.technical"           # focus, exposure, stability, audio

    # neither
    UNUSABLE = "unusable"                       # fails tier one; cannot be cut
    NO_WINNER = "no_winner"                     # nothing here is good enough


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

    code: FindingCode = Field(
        description="Pick the closest. Put what actually happened in `detail`."
    )
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
