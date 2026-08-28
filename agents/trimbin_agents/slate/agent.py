"""The Slate Agent: read the board, group the take, notice the stray.

Cheapest call in the system by design. It runs on every clip ever uploaded, so a
setting that costs a fraction of a cent more per call costs real money across an
archive — hence low thinking, low media resolution, and only the opening seconds
of the clip sent at all.

Nothing here judges quality. Exposure, focus and performance belong to the
Analyst, and an agent that can express an opinion will eventually be asked for
one.
"""

from __future__ import annotations

import logging
from pathlib import Path

from google import genai
from google.genai import types

from ..common.errors import AgentFailure, Unreadable
from ..config import settings
from ..contracts.base import ClipRef, Confidence
from ..contracts.slate import (
    GroupingSource,
    MisplacementProposal,
    SlateReading,
    SlateRequest,
    SlateResult,
)

log = logging.getLogger(__name__)

PROMPT_VERSION = "slate/v1"
_PROMPT = (Path(__file__).parent / "prompt_v1.md").read_text(encoding="utf-8")

# A board is held up, clapped, and pulled away. Everything after that is the take
# itself, and sending it would multiply the cost of the cheapest agent by the
# length of the footage for no gain.
SLATE_WINDOW_S = 6.0

# How far below a group's own members a clip has to score before we say anything.
#
# Relative, not absolute, and the difference is not academic. This was an
# absolute cosine of 0.62, described in a comment as tuned on an eval set that
# did not exist. On real footage every clip — correctly filed or deliberately
# misfiled — scores between 0.91 and 0.98 against any group in the same
# production, because two angles on one scene share a room, a light and two
# actors. Nothing ever fell below 0.62, so the check never fired once.
#
# What does separate them is how a clip scores compared to how that group's own
# members score. A take that belongs sits at its group's typical similarity; an
# intruder sits measurably below it, though both are in the nineties.
#
# Measured on 12 takes across 4 setups (eval/run_misplacement_eval.py): at this
# value no correctly filed take was flagged, 6 of 12 deliberately misfiled ones
# were caught within a scene, and 27 of 36 overall. Missing half of the hard
# case is the price of never crying wolf, and it is the right trade for a
# proposal an editor has to read.
#
# Twelve takes is a thin calibration and this number will move. It sits below
# the lowest genuine member observed rather than at it, so the margin is
# deliberate rather than fitted.
MISPLACEMENT_RATIO = 0.975

# A group needs this many members before its typical score means anything. Two
# members give a median of two numbers, which one unusual take dominates.
MIN_GROUP_FOR_COMPARISON = 3


class SlateAgent:
    def __init__(self, client: genai.Client | None = None) -> None:
        self._client = client or genai.Client(
            vertexai=True,
            project=settings.project_id,
            location=settings.model_location,
        )

    async def run(self, request: SlateRequest, clip_head: bytes) -> SlateResult:
        """Read the board, or say honestly that there was none to read."""
        try:
            reading, source, confidence = await self._read_board(clip_head)
        except Unreadable:
            reading, source, confidence = SlateReading(), GroupingSource.TIMECODE, Confidence.UNCERTAIN

        if source is GroupingSource.SLATE:
            group_id, subgroup_id, take_no = _parse_reading(reading)
        else:
            group_id, subgroup_id, take_no = _infer_from_neighbours(request)

        return SlateResult(
            clip_id=request.clip_id,
            reading=reading,
            group_id=group_id,
            subgroup_id=subgroup_id,
            take_no=take_no,
            source=source,
            confidence=confidence,
            misplacement=None,  # filled by check_placement once embeddings exist
            model_id=settings.slate_model,
            prompt_version=PROMPT_VERSION,
        )

    async def _read_board(self, clip_head: bytes) -> tuple[SlateReading, GroupingSource, Confidence]:
        try:
            response = await self._client.aio.models.generate_content(
                model=settings.slate_model,
                contents=[
                    types.Part.from_bytes(data=clip_head, mime_type="video/mp4"),
                    _PROMPT,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SlateReading,
                    # Reading characters off a board needs no deliberation, and
                    # thinking budget is charged whether it helped or not.
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                    # Low resolution is enough for large hand-written figures and
                    # costs a fraction of the tokens per frame.
                    media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
                    temperature=0.0,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — the caller decides whether to retry
            raise AgentFailure(f"slate read failed: {exc}") from exc

        reading = SlateReading.model_validate_json(response.text)

        # An empty board is not a failure of the model, it is the absence of a
        # board — and saying so is the whole point of the distinction.
        if not reading.raw.strip():
            raise Unreadable("no slate visible")

        confident = bool(reading.scene and reading.take)
        return (
            reading,
            GroupingSource.SLATE,
            Confidence.CONFIDENT if confident else Confidence.UNCERTAIN,
        )

    async def check_placement(
        self,
        clip: ClipRef,
        embedding: list[float],
        group_members: dict[tuple[int, int], list[list[float]]],
    ) -> MisplacementProposal | None:
        """Does this clip look like it belongs where it was filed?

        Takes each group's member embeddings rather than a precomputed centroid,
        because the question is not how similar this clip is but how similar it
        is compared to the clips already there — and only the members answer
        that. Two angles on one scene share a room, a light and two actors, so
        the absolute number is high for everything and distinguishes nothing.

        Returns a proposal, never an action. Similarity is right often enough to
        be trusted and wrong often enough to ruin a shoot day, and moving footage
        on that basis would be the most destructive thing this system could do.
        """
        own_key = (clip.group_id, clip.subgroup_id)
        own_members = group_members.get(own_key)

        if not own_members or len(group_members) < 2:
            return None

        # The clip is excluded from its own group's statistics. A clip compared
        # against a centroid containing itself always matches, and the more
        # unusual it is the harder it pulls that centroid towards itself.
        others = [m for m in own_members if m != embedding]
        if len(others) < MIN_GROUP_FOR_COMPARISON - 1:
            return None

        typical = _typical_similarity(others)
        if typical <= 0:
            return None

        own_similarity = _cosine(embedding, _centroid(others))
        own_ratio = own_similarity / typical
        if own_ratio >= MISPLACEMENT_RATIO:
            return None

        best_key, best_ratio, best_similarity = own_key, own_ratio, own_similarity
        for key, members in group_members.items():
            if key == own_key or len(members) < MIN_GROUP_FOR_COMPARISON:
                continue
            elsewhere = _typical_similarity(members)
            if elsewhere <= 0:
                continue
            similarity = _cosine(embedding, _centroid(members))
            if similarity / elsewhere > best_ratio:
                best_key = key
                best_ratio = similarity / elsewhere
                best_similarity = similarity

        if best_key == own_key:
            return MisplacementProposal(
                better_group_id=None,
                better_subgroup_id=None,
                similarity=own_similarity,
                detail="Does not resemble any group in this project",
            )

        return MisplacementProposal(
            better_group_id=best_key[0],
            better_subgroup_id=best_key[1],
            similarity=best_similarity,
            detail=(
                f"Sits {1 - own_ratio:.0%} below the other takes in scene "
                f"{clip.group_id}, shot {clip.subgroup_id}, and matches scene "
                f"{best_key[0]}, shot {best_key[1]} better"
            ),
        )


def _parse_reading(reading: SlateReading) -> tuple[int, int, int]:
    """Turn what the board said into numbers.

    Slates carry letters — scene 12A, shot B — so the alphabetic part is folded
    into the number rather than discarded. Losing it would merge 12 and 12A into
    one scene, which are different setups that a production deliberately named
    apart.
    """
    return (
        _to_ordinal(reading.scene),
        _to_ordinal(reading.shot),
        reading.take,
    )


def _to_ordinal(value: str) -> int:
    """`12A` becomes 1201, `12` becomes 1200, so ordering survives the letter."""
    digits = "".join(c for c in value if c.isdigit())
    letters = "".join(c for c in value if c.isalpha()).upper()
    base = int(digits) * 100 if digits else 0
    suffix = (ord(letters[0]) - ord("A") + 1) if letters else 0
    return base + suffix


def _infer_from_neighbours(request: SlateRequest) -> tuple[int, int, int]:
    """Group by what was shot around it.

    A crew works through a setup before moving on, so adjacency in time is the
    strongest signal available once the board is gone. The result is marked
    uncertain by the caller and confirmed by an editor — this only has to be
    close enough to make confirming quick.
    """
    if not request.neighbours:
        return 0, 0, 1

    nearest = request.neighbours[0]
    take_no = max((n.take_no for n in request.neighbours), default=0) + 1
    return nearest.group_id, nearest.subgroup_id, take_no


def _centroid(vectors: list[list[float]]) -> list[float]:
    n = len(vectors)
    return [sum(v[i] for v in vectors) / n for i in range(len(vectors[0]))]


def _typical_similarity(members: list[list[float]]) -> float:
    """How well this group's own members match the group, each left out in turn.

    Leave-one-out because a member scored against a centroid built including
    itself is partly scored against itself, and the smaller the group the more
    that flatters it. This is the yardstick a candidate gets measured against.
    """
    if len(members) < 2:
        return 0.0

    scores = sorted(
        _cosine(member, _centroid(members[:i] + members[i + 1:]))
        for i, member in enumerate(members)
    )
    mid = len(scores) // 2
    return scores[mid] if len(scores) % 2 else (scores[mid - 1] + scores[mid]) / 2


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
