"""Where the worker asks a model who a clip is.

Kept apart from the worker for one reason: everything here can fail, and none of
it failing should cost a clip. Measurement is arithmetic and either works or the
file is broken; this is a network call to a paid service that can be slow,
rate-limited, or simply wrong. A clip with measurements and no slate reading is
a clip an editor can still use. A clip lost because a model call timed out is
not.

So every function here returns something usable when it cannot do its job, and
says so in the log rather than raising.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from ..config import settings
from .ffmpeg_ops import extract_frames, extract_head
from .measure import EMBED_FRAME_COUNT

log = logging.getLogger(__name__)

# How much of the clip the Slate Agent sees. A board is held up, clapped and
# pulled away inside this window; the rest is the take.
SLATE_WINDOW_S = 6.0

_EMBEDDING_DIMENSIONS = 768


@dataclass(slots=True)
class Identity:
    """What we were able to learn about where a clip belongs.

    All-zero defaults are the honest answer for a clip we could not read: group
    zero is shown as ungrouped rather than as scene zero, and an editor files it
    themselves. Guessing would be worse than saying nothing, because a wrong
    grouping is silently inherited by every comparison downstream.
    """

    group_id: int = 0
    subgroup_id: int = 0
    take_no: int = 0
    slate_confident: int = 0
    slate_raw: str = ""
    # Which body shot it, when the board says so. Empty is the ordinary answer
    # on a single-camera production and is not a gap.
    camera: str = ""
    embedding: list[float] = field(default_factory=list)

    @property
    def read_a_board(self) -> bool:
        return bool(self.slate_raw.strip())


def _client():
    """Built per call site rather than held.

    The worker processes one clip per instance and then idles until Cloud Run
    stops it, so there is nothing to amortise, and a cached client would keep a
    connection open across the gap.
    """
    from google import genai

    return genai.Client(
        vertexai=True,
        project=settings.project_id,
        # The current Gemini family is published to the global endpoint only.
        # Asking us-central1 returns a 404 that reads as if the model does not
        # exist, when it exists and is served elsewhere.
        location=settings.model_location,
    )


async def read_slate(source: Path, work: Path, clip_id: UUID, project_id: int) -> Identity:
    """Ask the Slate Agent what board, if any, is on the front of this clip."""
    identity = Identity()

    head = await extract_head(source, work / "head.mp4", SLATE_WINDOW_S)
    if head is None:
        return identity

    try:
        from trimbin_agents.contracts.slate import SlateRequest
        from trimbin_agents.slate.agent import SlateAgent

        agent = SlateAgent(client=_client())
        result = await agent.run(
            SlateRequest(
                clip_id=clip_id,
                project_id=project_id,
                storage_uri="",
                captured_at_epoch=0,
                duration_s=SLATE_WINDOW_S,
                # No neighbours yet. Inference from what was shot around a clip
                # needs the rest of the batch, which the worker does not have —
                # it processes one clip per message on purpose. Grouping by
                # adjacency is the review queue's job, once the batch is in.
                neighbours=[],
            ),
            head.read_bytes(),
        )
    except Exception:
        log.exception("slate read failed for clip %s; continuing without one", clip_id)
        return identity

    identity.slate_raw = result.reading.raw
    if not identity.read_a_board:
        log.info("clip %s: no board on the front of it", clip_id)
        return identity

    identity.group_id = result.group_id
    identity.subgroup_id = result.subgroup_id
    identity.take_no = result.take_no
    identity.slate_confident = 1 if result.confidence.value == "confident" else 0
    identity.camera = camera_from_slate(result.reading.raw)
    log.info(
        "clip %s: board reads %r -> scene %d, shot %d, take %d",
        clip_id, result.reading.raw.replace("\n", " / "),
        result.group_id, result.subgroup_id, result.take_no,
    )
    return identity


# Only an explicit camera marking counts.
#
# The tempting shortcut is to read the letter in "12A" as the camera. It is not:
# that letter is the setup — 12A the wide, 12B her close-up — and treating it as
# a camera would put every shot of a single-camera day on a different one. On a
# multi-camera shoot the board says so in as many words, and if it does not, the
# honest answer is that we do not know.
_CAMERA = re.compile(
    r"\b(?:CAM(?:ERA)?\.?\s*([A-D])\b|([A-D])\s*CAM(?:ERA)?\b)",
    re.IGNORECASE,
)


def camera_from_slate(raw: str) -> str:
    """The camera letter the board declares, or an empty string.

    A pure function so it can be tested without a model, and so the rule that
    decides it is one readable line rather than a branch inside the worker.
    """
    match = _CAMERA.search(raw or "")
    if not match:
        return ""
    return (match.group(1) or match.group(2) or "").upper()


async def embed(source: Path, work: Path, clip_id: UUID, duration_s: float) -> list[float]:
    """A vector describing how the clip looks, averaged over several frames.

    Returns an empty list when it cannot be produced. The caller writes zeros in
    that case, which is distinguishable from a real embedding — nothing else has
    zero magnitude — so a later pass can find the gaps and fill them.
    """
    frames = await extract_frames(source, work / "frames", EMBED_FRAME_COUNT, duration_s)
    if not frames:
        return []

    try:
        from google.genai import types

        client = _client()
        vectors = []
        for frame in frames:
            response = await client.aio.models.embed_content(
                model=settings.embedding_model,
                contents=[
                    types.Part.from_bytes(data=frame.read_bytes(), mime_type="image/jpeg")
                ],
                config=types.EmbedContentConfig(
                    output_dimensionality=_EMBEDDING_DIMENSIONS
                ),
            )
            vectors.append(response.embeddings[0].values)
    except Exception:
        log.exception("embedding failed for clip %s; writing zeros", clip_id)
        return []

    if not vectors:
        return []

    n = len(vectors)
    return [sum(v[i] for v in vectors) / n for i in range(len(vectors[0]))]
