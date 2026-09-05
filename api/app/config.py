"""API settings.

Secrets arrive from Secret Manager at runtime and are never read from a file in
the image. The defaults here are for local development against a scratch
project; nothing in this file is a credential.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRIMBIN_", env_file=".env", extra="ignore")

    project_id: str = "trimbin"
    region: str = "us-central1"

    # ---- clickhouse -------------------------------------------------------
    clickhouse_host: str = ""
    clickhouse_port: int = 8443
    clickhouse_user: str = "default"

    # What MCP connects as. A separate user with SELECT and nothing else, so a
    # statement a model wrote cannot do anything a reader could not — enforced
    # at the server, not by a pattern match on the way in.
    clickhouse_reader_user: str = ""
    clickhouse_reader_password: str = ""
    clickhouse_password: str = ""

    # ---- storage ----------------------------------------------------------
    originals_bucket: str = "trimbin-originals"
    proxies_bucket: str = "trimbin-proxies"
    artifacts_bucket: str = "trimbin-artifacts"
    cdn_base_url: str = ""

    # ---- messaging --------------------------------------------------------
    ingest_topic: str = "trimbin-ingest"

    # ---- models -----------------------------------------------------------
    # Where the models are served, which is not where this service runs. The
    # current Gemini family is published to the global endpoint only, and asking
    # us-central1 for one returns a 404 that reads as if the model does not
    # exist. Cloud Run stays next to the buckets and the database; only the
    # model calls leave.
    #
    # The model ids themselves live in the agents package beside the prompts
    # they were chosen for. Only the embedding model is named here, because it
    # is called from the worker directly rather than through an agent.
    model_location: str = "global"
    embedding_model: str = "gemini-embedding-2"

    # ---- scheduled maintenance --------------------------------------------
    # Who may call /maintenance/*.
    #
    # This service is public — the demo pages need it to be — so Cloud Run lets
    # everybody reach those paths and enforces nothing there. The application is
    # the only thing that can tell the scheduler from a stranger, which is why
    # the token is verified rather than merely required.
    scheduler_service_account: str = ""
    scheduler_audience: str = ""

    # ---- identity ---------------------------------------------------------
    # Google verifies the token's signature and issuer regardless; naming the
    # audience is what stops a token minted for a different application from
    # being accepted here.
    oauth_client_id: str = ""

    # The second way in, because the first one needs a console.
    #
    # An OAuth client cannot be created by any API, so a deployment without that
    # one manual step had every screen behind a door nobody could open. A pass
    # is a code somebody types; the API signs a session token of its own with the
    # secret below and verifies it on the way back in.
    #
    # No default, and nothing is minted or trusted without it. A signing secret
    # with a fallback value is a signing secret everybody has.
    session_secret: str = ""

    # One code, shared deliberately - with a judge, in a submission. It grants
    # the guest role and nothing more, which is safe because of what a guest can
    # do rather than because of who holds the code: every guest action is
    # additive, attributed and reversible.
    guest_pass: str = ""

    # `email:code` pairs, one per editor, so the archive records who actually
    # decided something. One shared code would have been less work and would
    # have made every override say "one of the three of us".
    team_passes: str = ""

    # ---- access -----------------------------------------------------------
    # Membership by email, which is all a small team needs. A permissions matrix
    # is real work for a real product and would earn nothing here.
    # The complete real-footage example used by the public workspace and demo.
    # Keep this aligned with README/documentation and the seeded production
    # project; UI protections and links key off the same value.
    demo_project_id: int = 9

    # ---- guest workspaces -------------------------------------------------
    # The numbers themselves live in services/members.py, beside the roster and
    # the capability table, because a limit and the role it applies to are one
    # decision and splitting them across two files is how they drift.
    #
    # What used to be here was a block of sandbox_* settings for a separate
    # project with separate rules. The sandbox is gone: everyone gets the same
    # application, and the limits sit on a project a guest actually owns.

    # ---- limits -----------------------------------------------------------
    max_upload_bytes: int = Field(default=8 * 1024**3, description="8 GiB")
    signed_url_ttl_hours: int = 6

    # review_margin used to live here as well, with a note saying it had to match
    # the agents' value or the queue and the archive would disagree. Two
    # constants that must match, in two files, is not a rule — it is a bug with a
    # comment on it. The API now reads the agents' threshold directly.


@lru_cache
def _load() -> Settings:
    return Settings()


settings = _load()
