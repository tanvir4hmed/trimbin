"""Provider image limits must preserve every input frame and fail incomplete batches."""

import json

import pytest
from pydantic import BaseModel

from trimbin_agents import content, runtime


class Observation(BaseModel):
    text: str


@pytest.mark.asyncio
async def test_twelve_frames_become_eight_plus_four_then_grounded_reasoning(monkeypatch):
    monkeypatch.setattr(runtime.settings, "vision_max_frames", 8)
    monkeypatch.setattr(runtime.settings, "vision_model", "vision")
    monkeypatch.setattr(runtime.settings, "reasoning_model", "reasoning")
    requests = []

    async def request(operation, payload):
        requests.append(payload.copy())
        return {
            "choices": [
                {"finish_reason": "stop", "message": {"content": json.dumps({"text": "observed"})}}
            ]
        }

    client = runtime.Client()
    monkeypatch.setattr(client, "request", request)
    await client.generate_content(
        model="vision",
        contents=[
            content.Part.from_bytes(data=bytes([n]), mime_type="image/jpeg") for n in range(12)
        ],
        config=content.GenerateContentConfig(response_schema=Observation),
    )
    counts = [sum(p["type"] == "image_url" for p in r["messages"][0]["content"]) for r in requests]
    assert counts == [8, 4, 0]
    assert requests[-1]["model"] == "reasoning"
    assert (
        len(
            json.loads(
                requests[-1]["messages"][0]["content"][-1]["text"].split("All observations: ")[1]
            )
        )
        == 2
    )


@pytest.mark.asyncio
async def test_incomplete_batch_cannot_be_presented_as_complete(monkeypatch):
    monkeypatch.setattr(runtime.settings, "vision_max_frames", 8)

    async def request(*args):
        return {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}

    client = runtime.Client()
    monkeypatch.setattr(client, "request", request)
    with pytest.raises(RuntimeError, match="incomplete"):
        await client.generate_content(
            model="vision",
            contents=[
                content.Part.from_bytes(data=b"frame", mime_type="image/jpeg") for _ in range(9)
            ],
        )
