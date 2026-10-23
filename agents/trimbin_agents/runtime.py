"""Token Factory runtime for the retained editorial agents.

The small content types preserve the agents' contracts without a cloud SDK.
Videos are decoded on the host; frames carry timestamps and speech is transcribed
by a CPU ASR model. No model call is represented as local or offline inference.
"""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

import aiohttp
from pydantic import TypeAdapter

from .config import settings

_speech = None
PARTIAL_BATCH = (
    "This is a partial visual batch. Report only evidence visible here; "
    "other times are unobserved in this batch."
)
MERGE_BATCHES = (
    "Combine visual-batch observations into the requested final schema. "
    "They refer to the same original input windows. Preserve source IDs and "
    "source-relative timestamps, resolve overlaps, retain uncertainty and "
    "disagreements, and never invent missing evidence. All observations: "
)


def transcribe(path: Path) -> dict[str, Any]:
    global _speech
    if not settings.asr_model:
        return {"status": "unavailable", "segments": []}
    from faster_whisper import WhisperModel  # type: ignore[import-untyped]

    if _speech is None:
        _speech = WhisperModel(
            settings.asr_model,
            device="cpu",
            compute_type="int8",
            cpu_threads=settings.media_threads,
            download_root=settings.model_cache_root,
        )
    import numpy as np

    # FFmpeg decodes the bounded window into the model's 16 kHz float input.
    # Passing the waveform avoids PyAV container API changes and preserves ASR input quality.
    result = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "f32le",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
        timeout=settings.media_timeout_seconds,
    )
    audio = np.frombuffer(result.stdout, dtype=np.float32)
    segments, info = _speech.transcribe(audio, beam_size=5, vad_filter=True)
    return {
        "status": "completed",
        "model": settings.asr_model,
        "precision": "int8",
        "language": info.language,
        "segments": [{"start": s.start, "end": s.end, "text": s.text} for s in segments],
    }


def video_content(
    data: bytes | Path, start_s: float = 0, window_s: float | None = None
) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="trimbin-vision-") as directory:
        root = Path(directory)
        if isinstance(data, Path):
            source = data
        else:
            source = root / "input.mp4"
            source.write_bytes(data)
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source)],
            check=True,
            capture_output=True,
            timeout=60,
        )
        metadata = json.loads(probe.stdout)
        duration = (
            window_s if window_s is not None else float(metadata["format"].get("duration", 0))
        )
        if start_s < 0 or duration <= 0:
            raise ValueError("Invalid original source window")
        if duration * settings.vision_sample_fps > 128:
            raise ValueError("Video exceeds bounded vision window; split into overlapping windows")
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-threads",
                str(settings.media_threads),
                "-ss",
                str(start_s),
                "-i",
                str(source),
                "-t",
                str(duration),
                "-vf",
                f"fps={settings.vision_sample_fps}",
                "-frames:v",
                "128",
                "-q:v",
                "2",
                str(root / "%05d.jpg"),
            ],
            check=True,
            capture_output=True,
            timeout=settings.media_timeout_seconds,
        )
        content = [
            {
                "type": "text",
                "text": (
                    f"Video duration {duration:.3f}s. Sampling: {settings.vision_sample_fps} fps. "
                    "Events between samples may be missed. Do not invent unseen motion."
                ),
            }
        ]
        for index, frame in enumerate(sorted(root.glob("*.jpg"))):
            content.extend(
                [
                    {
                        "type": "text",
                        "text": (f"Source-relative time {index / settings.vision_sample_fps:.3f}s"),
                    },
                    image_content(frame.read_bytes(), "image/jpeg"),
                ]
            )
        if any(s.get("codec_type") == "audio" for s in metadata["streams"]):
            audio = root / "speech.wav"
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-ss",
                    str(start_s),
                    "-i",
                    str(source),
                    "-t",
                    str(duration),
                    "-map",
                    "0:a:0",
                    "-vn",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(audio),
                ],
                check=True,
                capture_output=True,
                timeout=settings.media_timeout_seconds,
            )
            speech = transcribe(audio)
            content.append(
                {
                    "type": "text",
                    "text": "Timestamped ASR evidence (may contain recognition errors): "
                    + json.dumps(speech, ensure_ascii=False),
                }
            )
        return content


def image_content(data: bytes, mime: str) -> dict[str, Any]:
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode()}"},
    }


class Client:
    def __init__(self, **kwargs: Any) -> None:
        self.aio = self
        self.models = self

    async def request(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not settings.inference_live_enabled or settings.inference_mode != "nebius":
            raise RuntimeError("Live Token Factory inference is disabled")
        if not settings.nebius_api_key:
            raise RuntimeError("Token Factory credential missing")
        endpoint = urlsplit(settings.nebius_base_url)
        if (
            endpoint.scheme != "https"
            or endpoint.hostname != "api.tokenfactory.nebius.com"
            or endpoint.path.rstrip("/") != "/v1"
            or endpoint.username
            or endpoint.password
            or endpoint.query
            or endpoint.fragment
            or endpoint.port not in {None, 443}
            or operation not in {"chat/completions", "embeddings"}
        ):
            raise RuntimeError("Unsupported Token Factory endpoint")
        timeout = aiohttp.ClientTimeout(total=settings.inference_timeout_seconds)
        for attempt in range(settings.inference_max_retries + 1):
            async with (
                aiohttp.ClientSession(timeout=timeout, trust_env=False) as session,
                session.post(
                    settings.nebius_base_url.rstrip("/") + "/" + operation,
                    headers={"Authorization": "Bearer " + settings.nebius_api_key},
                    json=payload,
                    allow_redirects=False,
                ) as response,
            ):
                if (
                    response.status in {429, 500, 502, 503, 504}
                    and attempt < settings.inference_max_retries
                ):
                    await response.read()
                    await asyncio.sleep(2**attempt)
                    continue
                if response.status != 200:
                    raise RuntimeError(f"Token Factory request failed (HTTP {response.status})")
                data = bytearray()
                async for block in response.content.iter_chunked(65536):
                    data.extend(block)
                    if len(data) > settings.inference_response_bytes:
                        raise RuntimeError("Token Factory response exceeds configured limit")
                result = json.loads(data)
                if not isinstance(result, dict):
                    raise RuntimeError("Invalid Token Factory response")
                return result
        raise RuntimeError("Token Factory unavailable")

    async def generate_content(self, *, model: str, contents: Any, config: Any = None) -> Any:
        parts = []
        for input_index, item in enumerate(contents if isinstance(contents, list) else [contents]):
            if isinstance(item, str):
                parts.append({"type": "text", "text": item})
            elif getattr(item, "mime_type", "").startswith("video/"):
                prepared = await asyncio.to_thread(
                    video_content,
                    getattr(item, "source_path", None) or item.data,
                    getattr(item, "start_s", 0),
                    getattr(item, "duration_s", None),
                )
                for entry in prepared:
                    if entry["type"] == "text":
                        entry["text"] = (
                            f"Input {input_index + 1}, source {getattr(item, 'reference', '')}: "
                            + entry["text"]
                        )
                parts.extend(prepared)
            elif getattr(item, "mime_type", "").startswith("image/"):
                parts.append(image_content(item.data, item.mime_type))
            else:
                raise ValueError("Unsupported editorial inference input")
        visual = any(part["type"] == "image_url" for part in parts)
        chosen = settings.vision_model if visual else settings.reasoning_model
        schema = getattr(config, "response_schema", None)
        if schema:
            shape = TypeAdapter(schema).json_schema()
            instruction = (
                "Wrap the array in a JSON object with key items. "
                if shape.get("type") == "array"
                else ""
            )
            parts.append(
                {
                    "type": "text",
                    "text": instruction
                    + "Return only JSON matching this schema: "
                    + json.dumps(shape),
                }
            )
        payload = {
            "model": chosen,
            "messages": [{"role": "user", "content": parts}],
            "temperature": getattr(config, "temperature", 0),
            "max_tokens": settings.inference_max_output_tokens,
            "response_format": {"type": "json_object"},
            "store": False,
        }
        images = sum(p["type"] == "image_url" for p in parts)
        if images > settings.vision_max_frames:
            # The live provider accepts eight images per request. Preserve every
            # sampled frame by analysing bounded batches and reasoning over all
            # validated observations; never lower resolution or silently drop frames.
            all_text = [p for p in parts if p["type"] == "text"]
            batches, current, count = [], [], 0
            for index, part in enumerate(parts):
                if part["type"] != "image_url":
                    continue
                if index and parts[index - 1]["type"] == "text":
                    current.append(parts[index - 1])
                current.append(part)
                count += 1
                if count == settings.vision_max_frames:
                    batches.append(current)
                    current, count = [], 0
            if current:
                batches.append(current)
            semaphore = asyncio.Semaphore(2)

            async def observe(batch: list[dict[str, Any]]) -> Any:
                async with semaphore:
                    response = await self.request(
                        "chat/completions",
                        {
                            **payload,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [
                                        *all_text,
                                        *batch,
                                        {
                                            "type": "text",
                                            "text": PARTIAL_BATCH,
                                        },
                                    ],
                                }
                            ],
                        },
                    )
                    choice = response["choices"][0]
                    if choice.get("finish_reason") != "stop":
                        raise RuntimeError("Partial visual observation incomplete")
                    observed = json.loads(choice["message"]["content"])
                    if schema:
                        if TypeAdapter(schema).json_schema().get("type") == "array" and isinstance(
                            observed, dict
                        ):
                            observed = observed.get("items", observed)
                        TypeAdapter(schema).validate_python(observed)
                    return observed

            observations = await asyncio.gather(*(observe(batch) for batch in batches))
            payload["model"] = settings.reasoning_model
            payload["messages"] = [
                {
                    "role": "user",
                    "content": [
                        *all_text,
                        {
                            "type": "text",
                            "text": MERGE_BATCHES + json.dumps(observations),
                        },
                    ],
                }
            ]
            chosen = settings.vision_model + "+" + settings.reasoning_model
        raw = await self.request("chat/completions", payload)
        choice = raw["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise RuntimeError("Editorial model output incomplete")
        text = choice["message"].get("content")
        if not text:
            raise RuntimeError("Editorial model returned no answer")
        # JSON arrays can be enclosed by providers requiring a JSON-object mode.
        if schema:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "items" in parsed and isinstance(parsed["items"], list):
                text = json.dumps(parsed["items"])
            TypeAdapter(schema).validate_json(text)
        return SimpleNamespace(text=text, model_version=chosen, usage_metadata=raw.get("usage"))

    async def embed_content(self, *, model: str, contents: Any, config: Any = None) -> Any:
        if any(not isinstance(item, str) for item in contents):
            description = await self.generate_content(
                model=settings.vision_model,
                contents=[
                    *contents,
                    "Describe visible actions, subjects and setting for editorial retrieval. "
                    "Return JSON with a description string.",
                ],
            )
            texts = [json.loads(description.text)["description"]]
        else:
            texts = contents
        raw = await self.request(
            "embeddings",
            {
                "model": settings.embedding_model,
                "input": texts,
                "dimensions": getattr(config, "output_dimensionality", 768),
                "encoding_format": "float",
            },
        )
        return SimpleNamespace(
            embeddings=[
                SimpleNamespace(values=r["embedding"])
                for r in sorted(raw["data"], key=lambda r: r["index"])
            ]
        )
