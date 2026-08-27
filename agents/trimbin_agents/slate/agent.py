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

# Below this, two clips are not the same setup. Tuned on the eval set rather than
# guessed; the value lives here so it can be changed in one place when the eval
# says it should be.
MISPLACEMENT_THRESHOLD = 0.62


class SlateAgent:
    def __init__(self, client: genai.Client | None = None) -> None:
        self._client = client or genai.Client(
            vertexai=True,
            project=settings.project_id,
            location=settings.region,
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
        group_centroids: dict[tuple[int, int], list[float]],
    ) -> MisplacementProposal | None:
        """Does this clip look like it belongs where it was filed?

        Compares the clip against its own group and every other group in the
        project. Returns a proposal, never an action: similarity is right often
        enough to be trusted and wrong often enough to ruin a shoot day, and
        moving footage on that basis would be the most destructive thing this
        system could do.
        """
        own_key = (clip.group_id, clip.subgroup_id)
        own = group_centroids.get(own_key)

        # A group of one has no centroid worth comparing against — the clip would
        # simply be measured against itself.
        if own is None or len(group_centroids) < 2:
            return None

        own_similarity = _cosine(embedding, own)
        if own_similarity >= MISPLACEMENT_THRESHOLD:
            return None

        best_key, best_similarity = own_key, own_similarity
        for key, centroid in group_centroids.items():
            if key == own_key:
                continue
            similarity = _cosine(embedding, centroid)
            if similarity > best_similarity:
                best_key, best_similarity = key, similarity

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
                f"Looks like scene {best_key[0]}, shot {best_key[1]} "
                f"({best_similarity:.0%} match) rather than where it was filed "
                f"({own_similarity:.0%})"
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


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
