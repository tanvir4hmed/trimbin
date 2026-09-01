"""The full-take phase is a public contract, not only internal functions."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import analysis


class TestOpenAPI:
    def test_take_analysis_has_a_real_response_model(self) -> None:
        operation = app.openapi()["paths"]["/analysis/{project_id}/{clip_id}"]["get"]
        schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert schema["$ref"].endswith("/TakeAnalysis")

    def test_a_finding_command_requires_revision_and_idempotency(self) -> None:
        operation = app.openapi()["paths"][
            "/analysis/{project_id}/{clip_id}/findings/{finding_id}"
        ]["post"]
        body_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        model_name = body_ref.rsplit("/", 1)[-1]
        command = app.openapi()["components"]["schemas"][model_name]
        assert {"rev", "action"} <= set(command["required"])
        header = next(p for p in operation["parameters"] if p["name"] == "Idempotency-Key")
        assert header["required"] is True

    def test_exact_seek_and_evidence_fields_are_in_the_contract(self) -> None:
        finding = app.openapi()["components"]["schemas"]["FindingEvent"]
        required = set(finding["required"])
        assert {"clip_id", "start_s", "end_s", "evidence_segment_ids", "revision"} <= required
        take = app.openapi()["components"]["schemas"]["TakeAnalysis"]
        assert {"clip", "findings", "history", "safe_ranges"} <= set(take["required"])


class TestLiveResponseValidation:
    def test_a_complete_take_returns_exact_playable_ranges(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clip_id, run_id, segment_id, finding_id, event_id = [uuid4() for _ in range(5)]
        now = datetime.now(UTC)
        finding = {
            "clip_id": clip_id,
            "finding_id": finding_id,
            "event_id": event_id,
            "run_id": run_id,
            "revision": 0,
            "action": "machine_open",
            "code": "focus.lost",
            "detail": "Focus drifts off the eyes.",
            "severity": "attention",
            "start_s": 58.0,
            "end_s": 61.0,
            "evidence_segment_ids": [segment_id],
            "sources": ["observed"],
            "supersedes_event_id": None,
            "actor_id": "segment-agent",
            "actor_role": "agent",
            "occurred_at": now,
        }

        async def archived(project_id: int, requested_clip_id):
            return {
                "clip": {
                    "group_id": 12,
                    "subgroup_id": 2,
                    "take_no": 4,
                    "duration_s": 70.0,
                    "proxy_uri": "/media/proxy.m3u8",
                    "sprite_uri": "/media/sprite.jpg",
                    "fps": 24.0,
                    "scene_code": "12",
                    "shot_code": "12B",
                },
                "run": {
                    "run_id": run_id,
                    "run_key": "run-key",
                    "state": "completed",
                    "duration_s": 70.0,
                    "covered_until_s": 70.0,
                    "window_count": 2,
                    "segment_count": 2,
                    "finding_count": 1,
                    "model_id": "gemini-test",
                    "prompt_version": "segment/v1",
                    "error": "",
                    "occurred_at": now,
                },
                "segments": [
                    {
                        "segment_id": segment_id,
                        "run_id": run_id,
                        "start_s": 52.0,
                        "end_s": 70.0,
                        "description": "A close-up continues through the line.",
                        "transcript": "The final line.",
                        "actions": ["delivers final line"],
                        "objects": [],
                        "speakers": ["actor"],
                        "shot_size": "close-up",
                        "camera_motion": "locked off",
                        "has_embedding": True,
                    }
                ],
                "findings": [finding],
                "history": [finding],
            }

        async def no_operational_state(project_id: int, requested_clip_id):
            return []

        monkeypatch.setattr(analysis.analysis_store, "read", archived)
        monkeypatch.setattr(analysis.finding_actions, "states_for_clip", no_operational_state)
        response = TestClient(app).get(f"/analysis/1/{clip_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["coverage_complete"] is True
        assert body["findings"][0]["start_s"] == 58.0
        assert body["findings"][0]["clip_id"] == str(clip_id)
        assert body["clip"]["proxy_uri"] == "/media/proxy.m3u8"


class TestMigrationShape:
    def test_the_three_phase_tables_and_current_views_are_declared(self) -> None:
        sql = Path("clickhouse/migrations/021_full_take_intelligence.sql").read_text()
        for name in (
            "analysis_runs",
            "clip_segments",
            "finding_events",
            "current_analysis_runs",
            "current_clip_segments",
            "current_findings",
        ):
            assert name in sql

    def test_interactive_analysis_uses_no_clickhouse_mutation(self) -> None:
        sql = Path("clickhouse/migrations/021_full_take_intelligence.sql").read_text().upper()
        assert "ALTER TABLE CLIPS UPDATE" not in sql
        assert "ALTER TABLE FINDING_EVENTS UPDATE" not in sql

    def test_old_run_findings_cannot_leak_into_the_current_view(self) -> None:
        sql = Path("clickhouse/migrations/021_full_take_intelligence.sql").read_text()
        current = sql.split("CREATE VIEW IF NOT EXISTS current_findings AS", 1)[1]
        assert "r.run_id = f.run_id" in current
        assert "human_dismissed" in current
