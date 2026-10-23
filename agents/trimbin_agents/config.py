"""Shared API/agent configuration for the canonical Trimbin runtime.

Portable profiles are explicit. Capability reporting describes configuration,
not successful connections or verified model quality.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def placeholder(value: object) -> bool:
    """Examples never count as a configured credential or model identity."""
    return isinstance(value, str) and (
        not value.strip()
        or value.strip().lower().startswith(("dummy", "replace_me", "your_", "placeholder"))
        or value.strip().startswith("<")
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRIMBIN_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    project_id: str = "trimbin"

    region: str = "us-east-1"

    slate_model: str = Field(
        default="nvidia/Nemotron-3.5-Super-VL",
        description="Runs on every clip. Source-resolution frames from the opening seconds.",
    )

    analyst_model: str = Field(
        default="nvidia/Nemotron-3.5-Super-VL",
        description=(
            "Timestamped original frames and CPU-ASR evidence; "
            "comparative quality requires evaluation."
        ),
    )

    archivist_model: str = Field(
        default="nvidia/nemotron-3-super-120b-a12b",
        description="Text in, query out. Never sees video.",
    )

    embedding_model: str = ""

    embedding_dimensions: int = 768

    review_margin: float = Field(
        default=0.15,
        description=(
            "Below this gap between first and second place, the shot goes to a "
            "person. The decision has stopped being technical at that point."
        ),
    )

    panel_margin: float = Field(
        default=0.15,
        description="Convene the full panel below this. Deliberation is expensive; ration it.",
    )

    max_takes_per_comparison: int = Field(
        default=8,
        description=(
            "At most eight candidates are compared per panel request with the "
            "prompt and the measurements. Larger groups are bracketed."
        ),
    )

    max_retries: int = Field(
        default=2,
        description="Then flag and move on. An agent that loops burns credit in silence.",
    )

    request_timeout_s: int = 300

    clickhouse_url: str = ""

    clickhouse_host: str = ""

    clickhouse_port: int = 8123

    clickhouse_reader_user: str = ""

    clickhouse_reader_password: str = Field(default="", repr=False, exclude=True)

    clickhouse_user: str = "default"

    clickhouse_password: str = Field(default="", repr=False, exclude=True)

    cdn_base_url: str = ""

    editorial_queue: str = "trimbin-editorial"

    scheduler_audience: str = ""

    oauth_client_id: str = ""

    session_secret: str = Field(default="", repr=False, exclude=True)

    guest_pass: str = Field(default="", repr=False, exclude=True)

    team_passes: str = Field(default="", repr=False, exclude=True)
    lead_editor_email: str = "tanvir4hmed@gmail.com"
    maintenance_token: str = Field(default="", repr=False, exclude=True)

    demo_project_id: int = 9

    max_upload_bytes: int = Field(default=8 * 1024**3, description="8 GiB")

    signed_url_ttl_hours: int = 6

    profile: Literal["development", "cloud-poc"] = "development"
    inference_mode: Literal["fixture", "nebius"] = "fixture"
    nebius_base_url: str = ""
    nebius_api_key: str = Field(default="", repr=False, exclude=True)
    vision_model: str = ""
    reasoning_model: str = ""
    asr_model: str = ""
    embedding_version: str = ""
    inference_live_enabled: bool = False
    vision_sample_fps: float = Field(default=2, ge=0.5, le=8)
    vision_max_frames: int = Field(default=8, ge=1, le=8)
    model_cache_root: str = "/model-cache"
    inference_catalog_path: str = ""
    inference_timeout_seconds: int = Field(default=120, ge=1, le=600)
    inference_max_retries: int = Field(default=1, ge=0, le=2)
    inference_max_output_tokens: int = Field(default=8192, ge=256, le=65536)
    inference_temperature: float = Field(default=0, ge=0, le=2, allow_inf_nan=False)
    inference_response_bytes: int = Field(default=8 * 1024**2, ge=1024, le=32 * 1024**2)
    evidence_embedding_identity_path: str = ""
    media_backend: Literal["filesystem"] = "filesystem"
    originals_root: str = ""
    proxies_root: str = ""
    export_root: str = ""
    allowed_media_roots: list[str] = Field(default_factory=list)
    media_roots: dict[str, str] = Field(default_factory=dict)
    media_root_projects: dict[str, list[int]] = Field(default_factory=dict)
    staging_root: str = ""
    media_threads: int = Field(default=2, ge=1, le=16)
    media_work_bytes: int = Field(default=2 * 1024**3, ge=1024**2)
    media_reserve_bytes: int = Field(default=1024**3, ge=0)
    media_timeout_seconds: int = Field(default=3600, ge=10, le=86400)
    database_url: str = Field(default="", repr=False, exclude=True)
    clickhouse_secure: bool = False
    demo_pass: str = Field(default="", repr=False, exclude=True)
    cors_origins: list[str] = Field(default_factory=list)
    tavily_api_key: str = Field(default="", repr=False, exclude=True)
    job_lease_seconds: int = Field(default=120, ge=10, le=3600)
    job_max_attempts: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def validate_runtime(self) -> Settings:
        if not 1 <= self.clickhouse_port <= 65535:
            raise ValueError("ClickHouse port must be between 1 and 65535")
        if self.nebius_base_url:
            url = urlsplit(self.nebius_base_url)
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("Nebius endpoint must be HTTPS without embedded credentials")
        if self.database_url and not self.database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("Operational database must use PostgreSQL")
        if self.profile == "cloud-poc" and self.inference_mode == "fixture":
            raise ValueError("Cloud PoC cannot silently use fixture inference")
        return self

    def capabilities(self) -> dict[str, dict[str, object]]:
        """Return names of missing settings only; never credentials or endpoints."""
        requirements = {
            "operational_store": ("database_url",),
            "evidence_writer": ("clickhouse_host", "clickhouse_user", "clickhouse_password"),
            "evidence_reader": (
                "clickhouse_host",
                "clickhouse_reader_user",
                "clickhouse_reader_password",
            ),
            "media": ("originals_root", "proxies_root", "staging_root", "allowed_media_roots"),
            "sessions": ("session_secret",),
            "vision": ("nebius_base_url", "nebius_api_key", "vision_model"),
            "reasoning": ("nebius_base_url", "nebius_api_key", "reasoning_model"),
            "speech": ("asr_model", "model_cache_root"),
            "semantic_search": ("embedding_model", "evidence_embedding_identity_path"),
            "web_research": ("tavily_api_key",),
        }
        result: dict[str, dict[str, object]] = {}
        for task, names in requirements.items():
            missing = [
                f"TRIMBIN_{name.upper()}"
                for name in names
                if not getattr(self, name) or placeholder(getattr(self, name))
            ]
            result[task] = {
                "status": "unavailable" if missing else "configured_unverified",
                "missing": missing,
            }
        if self.inference_mode == "fixture":
            for task in ("vision", "reasoning", "speech"):
                result[task] = {"status": "fixture_only", "missing": []}
        if self.clickhouse_user in {"default", self.clickhouse_reader_user}:
            result["evidence_writer"] = {
                "status": "unavailable",
                "reason": "Separate non-admin writer required",
            }
        if len(self.session_secret) < 32:
            result["sessions"] = {
                "status": "unavailable",
                "reason": "Session secret must have 32+ characters",
            }
        return result


@lru_cache
def _load() -> Settings:
    return Settings()


settings = _load()
