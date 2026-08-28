"""Settings, in one place.

Model ids in particular live here rather than at call sites. Choosing a model is
a decision that gets revisited — the eval harness exists to revisit it with
numbers instead of opinions — and a decision worth revisiting should not be
scattered across four files.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRIMBIN_", env_file=".env", extra="ignore")

    project_id: str = "trimbin"
    region: str = "us-central1"

    # Where the models are served, which is not where the service runs.
    #
    # The current Gemini family is only published to the global endpoint:
    # asking us-central1 for gemini-3.6-flash returns a 404 that reads like the
    # model does not exist, when it exists and is served elsewhere. Cloud Run
    # stays in us-central1 next to the buckets and the database; only the model
    # calls leave.
    model_location: str = "global"

    # ---- models -----------------------------------------------------------
    # One family, different settings per agent. The routing is the cost control:
    # reading six characters off a board and comparing seven takes are not the
    # same problem and should not cost the same.

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
    embedding_model: str = Field(
        default="gemini-embedding-2",
        description="Natively multimodal, so clips are compared on how they look rather than on prose about them.",
    )
    embedding_dimensions: int = 768

    # ---- thresholds -------------------------------------------------------
    # Chosen, not yet measured, and said plainly because the misplacement
    # threshold carried a comment claiming it had been tuned on an eval set that
    # did not exist — and it turned out to be so far off that the check it
    # governed had never once fired.
    #
    # These two decide when a shot goes to a person and when the panel sits.
    # Validating them needs shots where an editor disagreed with us, which is
    # data this system has not collected yet: it arrives the first time a real
    # editor overrides a verdict. Until then 0.15 is a starting point, and the
    # honest reading of any number derived from it is "at this setting".

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

    # ---- limits -----------------------------------------------------------
    max_retries: int = Field(
        default=2,
        description="Then flag and move on. An agent that loops burns credit in silence.",
    )
    request_timeout_s: int = 300

    # ---- storage ----------------------------------------------------------
    originals_bucket: str = "trimbin-originals"
    proxies_bucket: str = "trimbin-proxies"
    artifacts_bucket: str = "trimbin-artifacts"

    # ---- clickhouse -------------------------------------------------------
    clickhouse_url: str = ""
    clickhouse_user: str = "default"
    clickhouse_password: str = ""


@lru_cache
def _load() -> Settings:
    return Settings()


settings = _load()
