"""Deferred Phase 4 checks. Fixtures exercise contracts, not editorial model quality."""

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.inference.contracts import ModelProfile, TaskOutput, TaskRequest, fingerprint
from app.inference.evaluation import EvaluationManifest, Scores, paired_report, word_error_rate
from app.inference.provider import InferenceError, TokenFactory, live_preflight
from app.inference.runner import run_task

SOURCE = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def task_request():
    return TaskRequest.model_validate(
        {
            "project_id": 7,
            "task": "comparison",
            "sources": [{"id": SOURCE, "sha256": "a" * 64, "duration_us": 1000000}],
            "windows": [{"id": "w1", "source_id": SOURCE, "start_us": 0, "end_us": 1000000}],
            "evidence": [
                {
                    "id": "e1",
                    "source_id": SOURCE,
                    "start_us": 0,
                    "end_us": 500000,
                    "modality": "editor",
                    "text": "Fixture annotation",
                }
            ],
            "candidates": [{"id": "c1", "source_id": SOURCE, "start_us": 0, "end_us": 500000}],
            "brief_revision": "b1",
            "evidence_revision": "e1",
            "recipe": "synthetic-contract-only",
        }
    )


def answer():
    return {
        "status": "ok",
        "reason": "",
        "ranking": [
            {"candidate_id": "c1", "reason": "Fixture", "citations": ["e1"]},
        ],
    }


def test_output_rejects_fabricated_candidate_and_citation(task_request):
    for field, value in (("candidate_id", "invented"), ("citations", ["invented"])):
        raw = answer()
        raw["ranking"][0][field] = value
        with pytest.raises(ValueError):
            TaskOutput.model_validate(raw).validate_for(task_request)


def test_choice_requires_evidence_overlapping_selected_range(task_request):
    raw = task_request.model_dump(mode="json")
    raw["candidates"][0].update(start_us=700000, end_us=900000)
    with pytest.raises(ValueError, match="source evidence"):
        TaskOutput.model_validate(answer()).validate_for(TaskRequest.model_validate(raw))


def test_request_rejects_out_of_bounds_and_cross_source(task_request):
    raw = task_request.model_dump(mode="json")
    raw["windows"][0]["end_us"] = 2000000
    with pytest.raises(ValidationError):
        TaskRequest.model_validate(raw)


def test_dummy_key_never_enables_live_transport():
    config = Settings(
        _env_file=None,
        profile="development",
        inference_mode="nebius",
        inference_live_enabled=True,
        nebius_api_key="DUMMY_REPLACE_ME",
        nebius_base_url="https://api.tokenfactory.nebius.com/v1",
    )
    with pytest.raises(InferenceError, match="placeholder"):
        live_preflight(config)
    assert config.capabilities()["reasoning"]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_fixture_is_explicit_input_bound_and_never_live(task_request):
    config = Settings(_env_file=None, profile="development")
    bundle = {
        "input_fingerprint": fingerprint(task_request.model_dump(mode="json")),
        "output": answer(),
    }
    record = await run_task(task_request, {}, config, {}, fixture=bundle)
    assert record["status"] == "fixture"
    assert record["attempts"] == [] and record["provider"] is None
    changed = task_request.model_copy(update={"project_id": 8})
    assert (await run_task(changed, {}, config, {}, fixture=bundle))["status"] == "unavailable"


@pytest.mark.asyncio
async def test_provider_failure_never_falls_back_to_fixture(task_request, monkeypatch):
    config = Settings(
        _env_file=None,
        profile="development",
        inference_mode="nebius",
        inference_live_enabled=True,
        nebius_api_key="unit-test-only-not-a-key",
        nebius_base_url="https://api.tokenfactory.nebius.com/v1",
        reasoning_model="test/model",
        inference_max_retries=0,
    )
    profile = ModelProfile(
        model_id="test/model",
        revision="r1",
        precision="unknown",
        modalities=["text"],
        max_input_bytes=1000000,
        max_frames=0,
        deployment_generation="g1",
    )

    async def unavailable(*args, **kwargs):
        raise InferenceError("provider_authentication_failed")

    monkeypatch.setattr(TokenFactory, "request", unavailable)
    record = await run_task(task_request, {}, config, {profile.model_id: profile})
    assert record["status"] == "failed" and record["output"] is None
    assert len(record["attempts"]) == 1
    assert record["attempts"][0]["usage"] is None


def test_evaluation_cannot_hide_critical_regression():
    manifest = EvaluationManifest.model_validate(
        {
            "frozen_at": "2026-10-21T00:00:00Z",
            "minimum_independent_groups": 2,
            "baseline_provenance_reference": "fixture",
            "candidate_identity_reference": "fixture",
            "cases": [
                {
                    "id": str(i),
                    "group": str(i),
                    "source_sha256": str(i) * 64,
                    "split": "held_out",
                    "rights_reference": "synthetic",
                    "annotation_reference": "fixture",
                }
                for i in range(2)
            ],
            "metrics": [
                {
                    "id": "coverage",
                    "direction": "higher",
                    "critical": True,
                    "primary": True,
                    "meaningful_improvement": 0.05,
                }
            ],
        }
    )
    scores = Scores.model_validate(
        {
            "manifest_sha256": fingerprint(manifest.model_dump(mode="json")),
            "rows": [
                {
                    "case_id": str(i),
                    "metric_id": "coverage",
                    "baseline": 0.5,
                    "candidate": [0.4, 1.0][i],
                    "baseline_run": "fixture-b",
                    "candidate_run": "fixture-c",
                    "live_provenance_verified": False,
                    "contract_valid": True,
                }
                for i in range(2)
            ],
        }
    )
    report = paired_report(manifest, scores, "held_out")
    assert report["status"] == "failed" and not report["release_approved"]
    assert report["metrics"]["coverage"]["oriented_mean_delta"] > 0


def test_word_errors_include_insertions_and_silence():
    assert word_error_rate("one two", "one three") == 0.5
    assert word_error_rate("", "invented words") == 2.0
