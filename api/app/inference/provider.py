"""Bounded Token Factory transport. Error bodies and credentials are never logged."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
from trimbin_agents.config import placeholder

from ..config import Settings
from .contracts import ModelProfile


class InferenceError(Exception):
    def __init__(self, code: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


def reject_nonfinite(value: str):
    raise ValueError("Nonfinite JSON number")


def live_preflight(config: Settings) -> None:
    if config.inference_mode != "nebius" or not config.inference_live_enabled:
        raise InferenceError("live_inference_disabled")
    if placeholder(config.nebius_api_key):
        raise InferenceError("provider_key_missing_or_placeholder")
    parsed = urlsplit(config.nebius_base_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.tokenfactory.nebius.com"
        or parsed.port not in {None, 443}
        or parsed.path.rstrip("/") != "/v1"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise InferenceError("unsupported_provider_endpoint")


def load_catalog(path: str) -> dict[str, ModelProfile]:
    if not path:
        raise InferenceError("model_catalog_missing")
    try:
        file = Path(path)
        if file.stat().st_size > 1024**2:
            raise InferenceError("model_catalog_too_large")
        profiles = [ModelProfile.model_validate(p) for p in json.loads(file.read_text("utf-8"))]
        if len({p.model_id for p in profiles}) != len(profiles):
            raise ValueError("duplicate model")
        return {p.model_id: p for p in profiles}
    except (OSError, ValueError, TypeError) as exc:
        raise InferenceError("invalid_model_catalog") from exc


class TokenFactory:
    def __init__(self, config: Settings):
        self.config = config

    async def request(self, method: str, endpoint: str, payload: dict | None = None) -> dict:
        live_preflight(self.config)
        if endpoint not in {"models", "chat/completions", "embeddings"}:
            raise InferenceError("unsupported_provider_operation")
        timeout = aiohttp.ClientTimeout(total=self.config.inference_timeout_seconds)
        try:
            async with (
                aiohttp.ClientSession(timeout=timeout, trust_env=False) as session,
                session.request(
                    method,
                    f"{self.config.nebius_base_url.rstrip('/')}/{endpoint}",
                    headers={"Authorization": f"Bearer {self.config.nebius_api_key}"},
                    json=payload,
                    allow_redirects=False,
                ) as response,
            ):
                if response.status in {401, 403}:
                    raise InferenceError("provider_authentication_failed")
                if response.status == 429:
                    raise InferenceError("provider_rate_or_quota_limit", retryable=True)
                if response.status >= 500:
                    raise InferenceError("provider_unavailable", retryable=True)
                if response.status < 200 or response.status >= 300:
                    raise InferenceError("provider_request_rejected")
                data = bytearray()
                async for block in response.content.iter_chunked(65536):
                    data.extend(block)
                    if len(data) > self.config.inference_response_bytes:
                        raise InferenceError("provider_response_too_large")
                try:
                    result = json.loads(data, parse_constant=reject_nonfinite)
                    if not isinstance(result, dict):
                        raise ValueError("Expected object")
                    return result
                except (ValueError, UnicodeDecodeError) as exc:
                    raise InferenceError("invalid_provider_response") from exc
        except TimeoutError as exc:
            raise InferenceError("provider_timeout", retryable=True) from exc
        except aiohttp.ClientError as exc:
            raise InferenceError("provider_connection_failed", retryable=True) from exc

    async def discover(self) -> list[dict]:
        raw = await self.request("GET", "models")
        rows = raw.get("data")
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise InferenceError("invalid_model_catalog_response")
        # Discovery is not proof of modality support, license approval or model quality.
        return [
            {"id": row["id"], "owned_by": row.get("owned_by"), "created": row.get("created")}
            for row in rows
            if isinstance(row.get("id"), str)
        ]


def response_metadata(raw: dict) -> dict:
    request_id = raw.get("id")
    safe_id = (
        request_id
        if isinstance(request_id, str) and re.fullmatch(r"[a-zA-Z0-9_.:/-]{1,200}", request_id)
        else None
    )
    usage = raw.get("usage")
    counters = None
    if isinstance(usage, dict):
        counters = {
            key: usage[key]
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            if type(usage.get(key)) is int and usage[key] >= 0
        } or None
    model = raw.get("model")
    model = (
        model
        if isinstance(model, str) and re.fullmatch(r"[a-zA-Z0-9_.:/-]{1,200}", model)
        else None
    )
    return {
        "provider_request_id": safe_id,
        "provider_model": model,
        "usage": counters,
        "cost_usd": None,
    }


async def retry_delay(attempt: int) -> None:
    await asyncio.sleep(min(2**attempt, 8))
