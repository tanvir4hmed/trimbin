"""Observe one window independently of shot comparison or take count."""

from __future__ import annotations

from pathlib import Path

from google import genai
from google.genai import types

from ..common.errors import AgentFailure, text_of
from ..config import settings
from ..contracts.segments import SegmentObservation

PROMPT_VERSION = "segment/v1"
PROMPT = (Path(__file__).parent / "prompt_v1.md").read_text(encoding="utf-8")


class SegmentAgent:
    """A single-window observer, never a take chooser."""

    def __init__(self, client: genai.Client | None = None) -> None:
        self._client = client or genai.Client(
            vertexai=True,
            project=settings.project_id,
            location=settings.model_location,
        )

    async def run(
        self,
        video: bytes,
        *,
        duration_s: float,
        briefing: str = "",
    ) -> SegmentObservation:
        context = (
            f"This supplied window is {duration_s:.2f} seconds long. "
            "All finding timecodes must be local to 00:00 of this window."
        )
        contents: list[object] = [
            types.Part.from_bytes(data=video, mime_type="video/mp4"),
            PROMPT,
            context,
        ]
        if briefing:
            contents.append(briefing)

        try:
            response = await self._client.aio.models.generate_content(
                model=settings.analyst_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SegmentObservation,
                    temperature=0.1,
                ),
            )
        except Exception as exc:
            raise AgentFailure(f"segment observation failed: {exc}") from exc

        return SegmentObservation.model_validate_json(text_of(response, "segment observer"))
