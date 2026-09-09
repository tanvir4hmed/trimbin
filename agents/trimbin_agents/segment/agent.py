"""Observe one window independently of shot comparison or take count."""

from __future__ import annotations

from pathlib import Path

from google import genai
from google.genai import types
from pydantic import BaseModel

from ..common.errors import AgentFailure, text_of
from ..config import settings
from ..contracts.base import Finding, TimeRange
from ..contracts.segments import Moment, SegmentObservation

PROMPT_VERSION = "segment/v4"
PROMPT = (Path(__file__).parent / "prompt_v4.md").read_text(encoding="utf-8")
RUBRIC = (Path(__file__).parent.parent / "common" / "editorial_rubric.md").read_text(
    encoding="utf-8"
)


class AttemptModelResponse(BaseModel):
    """Provider schema stays constraint-light; the durable contract validates it."""

    where: TimeRange
    action: str
    observation: str
    interpretation: str
    recommendation: str
    confidence: float
    intent: str
    starts_before_window: bool
    ends_after_window: bool


class SegmentModelResponse(BaseModel):
    """Constraint-light wire schema accepted by Vertex structured output.

    ``SegmentObservation`` remains the durable contract and validates the
    answer below. Passing that model directly asks Vertex to compile Pydantic's
    defaults plus every ``maxLength``/``maxItems`` constraint; the current
    Gemini endpoint rejects that otherwise-valid schema with a bare 400.  Keep
    the provider-facing schema required and simple, then enforce the stricter
    archive contract after generation.
    """

    description: str
    transcript: str
    actions: list[str]
    objects: list[str]
    speakers: list[str]
    shot_size: str
    camera_motion: str
    moments: list[Moment]
    findings: list[Finding]
    attempts: list[AttemptModelResponse]


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
            RUBRIC,
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
                    response_schema=SegmentModelResponse,
                    temperature=0.1,
                ),
            )
            return SegmentObservation.model_validate_json(text_of(response, "segment observer"))
        except Exception as exc:
            raise AgentFailure(f"segment observation failed: {exc}") from exc
