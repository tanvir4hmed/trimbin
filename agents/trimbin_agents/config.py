"""Shared API/agent registry; legacy defaults preserve the deployed runtime.

Portable profiles are explicit. Capability reporting describes configuration,
not successful connections or verified model quality.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRIMBIN_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    project_id: str = "trimbin"

    region: str = "us-central1"

    model_location: str = "global"

    slate_model: str = Field(
        default="gemini-3.6-flash",
        description="Runs on every clip. Low thinking, low resolution, opening seconds only.",
    )

    analyst_model: str = Field(
        default="gemini-3.6-flash",
        description="Best on video of the current family, and cheaper than the generation before.",
    )

    archivist_model: str = Field(
        default="gemini-3.6-flash",
        description="Text in, query out. Never sees video.",
    )

    embedding_model: str = "gemini-embedding-2"

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
            "Gemini accepts ten videos per request; eight leaves room for the "
            "prompt and the measurements. Larger groups are bracketed."
        ),
    )

    max_retries: int = Field(
        default=2,
        description="Then flag and move on. An agent that loops burns credit in silence.",
    )

    request_timeout_s: int = 300

    originals_bucket: str = "trimbin-originals"

    proxies_bucket: str = "trimbin-proxies"

    artifacts_bucket: str = "trimbin-artifacts"

    clickhouse_url: str = ""

    clickhouse_host: str = ""

    clickhouse_port: int = 8443

    clickhouse_reader_user: str = ""

    clickhouse_reader_password: str = Field(default="", repr=False, exclude=True)

    clickhouse_user: str = "default"

    clickhouse_password: str = Field(default="", repr=False, exclude=True)

    cdn_base_url: str = ""

    ingest_topic: str = "trimbin-ingest"

    scheduler_service_account: str = ""

    scheduler_audience: str = ""

    oauth_client_id: str = ""

    session_secret: str = Field(default="", repr=False, exclude=True)

    guest_pass: str = Field(default="", repr=False, exclude=True)

    team_passes: str = Field(default="", repr=False, exclude=True)

    demo_project_id: int = 9

    max_upload_bytes: int = Field(default=8 * 1024**3, description="8 GiB")

    signed_url_ttl_hours: int = 6

    profile: Literal["legacy-cloud", "development", "cloud-poc"] = "legacy-cloud"
    inference_mode: Literal["fixture", "nebius"] = "fixture"
    nebius_base_url: str = ""
    nebius_api_key: str = Field(default="", repr=False, exclude=True)
    vision_model: str = ""
    reasoning_model: str = ""
    asr_model: str = ""
    embedding_version: str = ""
    media_backend: Literal["filesystem"] = "filesystem"
    originals_root: str = ""
    proxies_root: str = ""
    export_root: str = ""
    allowed_media_roots: list[str] = Field(default_factory=list)
    database_url: str = Field(default="", repr=False, exclude=True)
    clickhouse_secure: bool = True
    demo_pass: str = Field(default="", repr=False, exclude=True)
    cors_origins: list[str] = Field(default_factory=list)
    tavily_api_key: str = Field(default="", repr=False, exclude=True)
    job_lease_seconds: int = Field(default=120, ge=10, le=3600)
    job_max_attempts: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def validate_portable(self) -> Settings:
        if self.profile != "legacy-cloud" and "embedding_model" not in self.model_fields_set:
            self.embedding_model = ""
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
            "media": ("originals_root", "proxies_root", "export_root", "allowed_media_roots"),
            "sessions": ("session_secret",),
            "vision": ("nebius_base_url", "nebius_api_key", "vision_model"),
            "reasoning": ("nebius_base_url", "nebius_api_key", "reasoning_model"),
            "speech": ("nebius_base_url", "nebius_api_key", "asr_model"),
            "semantic_search": ("embedding_model", "embedding_version"),
            "web_research": ("tavily_api_key",),
        }
        result: dict[str, dict[str, object]] = {}
        for task, names in requirements.items():
            missing = [f"TRIMBIN_{name.upper()}" for name in names if not getattr(self, name)]
            result[task] = {
                "status": "unavailable" if missing else "configured_unverified",
                "missing": missing,
            }
        if self.inference_mode == "fixture":
            for task in ("vision", "reasoning", "speech"):
                result[task] = {"status": "fixture_only", "missing": []}
        if self.profile != "legacy-cloud":
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
