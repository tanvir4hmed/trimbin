"""Configuration must import and explain missing capabilities without cloud credentials."""

import pytest
from pydantic import ValidationError
from trimbin_agents.config import Settings as AgentSettings

from app.config import Settings
from app.foundation.repository import fingerprint


def test_single_registry_and_self_hosted_defaults():
    assert Settings is AgentSettings
    settings = Settings(_env_file=None)
    assert settings.profile == "development"
    assert settings.clickhouse_secure is False
    assert settings.clickhouse_port == 8123


def test_portable_settings_have_no_secret_fallback():
    settings = Settings(
        _env_file=None,
        profile="development",
        clickhouse_secure=False,
        clickhouse_port=8123,
        embedding_model="",
    )
    report = settings.capabilities()
    assert report["operational_store"]["status"] == "unavailable"
    assert report["sessions"]["status"] == "unavailable"
    assert report["vision"]["status"] == "fixture_only"
    assert report["semantic_search"]["status"] == "unavailable"


def test_secrets_never_in_repr_dump_or_capability_report():
    secret = "sensitive-value-do-not-print"
    settings = Settings(
        _env_file=None,
        nebius_api_key=secret,
        session_secret=secret,
        database_url=f"postgresql://user:{secret}@localhost/db",
        clickhouse_password=secret,
        clickhouse_reader_password=secret,
    )
    assert secret not in repr(settings)
    assert secret not in str(settings.model_dump())
    assert secret not in str(settings.capabilities())


@pytest.mark.parametrize(
    "values",
    [
        {"profile": "cloud-poc", "inference_mode": "fixture"},
        {"nebius_base_url": "http://insecure.example"},
        {"nebius_base_url": "https://user:password@example.com"},
        {"database_url": "sqlite:///state.db"},
        {"clickhouse_port": 0},
        {"job_lease_seconds": 0},
    ],
)
def test_invalid_configuration_fails_early(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_key_without_model_never_claims_live_capability():
    settings = Settings(
        _env_file=None,
        profile="cloud-poc",
        inference_mode="nebius",
        nebius_base_url="https://example.com/v1",
        nebius_api_key="test",
    )
    assert settings.capabilities()["vision"]["status"] == "unavailable"


def test_fingerprint_is_order_independent_and_rejects_nan():
    assert fingerprint({"b": 2, "a": 1}) == fingerprint({"a": 1, "b": 2})
    with pytest.raises(ValueError):
        fingerprint({"time": float("nan")})
