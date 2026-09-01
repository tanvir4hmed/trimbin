"""Human finding decisions remain current, attributed, and recoverable."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.routes import analysis
from app.services import finding_actions, revisions


def current_finding() -> dict:
    finding_id, event_id, run_id, segment_id = uuid4(), uuid4(), uuid4(), uuid4()
    return {
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
        "actor_id": "segment-agent",
        "actor_role": "agent",
    }


class TestFindingCommandContract:
    def test_revision_is_required(self) -> None:
        with pytest.raises(ValidationError):
            analysis.FindingCommand(action="dismiss")

    def test_adjust_requires_both_ends(self) -> None:
        with pytest.raises(ValidationError):
            analysis.FindingCommand(rev=0, action="adjust_range", start_s=58)

    def test_correction_must_actually_change_something(self) -> None:
        with pytest.raises(ValidationError):
            analysis.FindingCommand(rev=0, action="correct")


class TestWorkingViewAndHistory:
    def test_pending_dismiss_leaves_history_and_removes_current(self) -> None:
        finding = current_finding()
        dismissed = {
            **finding,
            "event_id": uuid4(),
            "action": "human_dismissed",
            "rev": 1,
            "revision": 1,
            "archive_state": "pending",
        }
        result = finding_actions.overlay(
            {"findings": [finding], "history": [finding]},
            [dismissed],
        )
        assert result["findings"] == []
        assert [event["action"] for event in result["history"]] == [
            "machine_open",
            "human_dismissed",
        ]


class _Principal:
    email = "guest@example.com"

    async def assert_can_comment(self, project_id: int) -> None:
        return None


def read_model(finding: dict) -> dict:
    return {
        "clip": {"duration_s": 70.0, "scene": 12, "shot": 2},
        "findings": [finding],
    }


class TestFindingCommandSafety:
    @pytest.mark.asyncio
    async def test_a_stale_finding_action_is_a_409(self, monkeypatch: pytest.MonkeyPatch) -> None:
        finding = current_finding()

        async def no_replay(key: str, actor: str):
            return None

        async def read(project_id: int, clip_id):
            return read_model(finding)

        async def stale(**kwargs):
            raise revisions.Conflict(kwargs["expected_rev"], 1)

        monkeypatch.setattr(analysis.revisions, "replay", no_replay)
        monkeypatch.setattr(analysis, "_read", read)
        monkeypatch.setattr(analysis.finding_actions, "commit", stale)

        with pytest.raises(revisions.Conflict) as raised:
            await analysis.act_on_finding(
                1,
                uuid4(),
                finding["finding_id"],
                analysis.FindingCommand(rev=0, action="dismiss"),
                _Principal(),
                "dismiss-0001",
            )
        assert raised.value.status_code == 409

    @pytest.mark.asyncio
    async def test_an_idempotent_retry_returns_the_first_answer_without_a_write(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        finding = current_finding()
        expected = {
            "status": "recorded",
            "finding_id": str(finding["finding_id"]),
            "event_id": str(uuid4()),
            "action": "human_dismissed",
            "rev": 1,
            "archive_pending": False,
        }

        async def replay(key: str, actor: str):
            return expected

        async def should_not_commit(**kwargs):
            raise AssertionError("a replay must not create a second event")

        monkeypatch.setattr(analysis.revisions, "replay", replay)
        monkeypatch.setattr(analysis.finding_actions, "commit", should_not_commit)
        result = await analysis.act_on_finding(
            1,
            uuid4(),
            finding["finding_id"],
            analysis.FindingCommand(rev=0, action="dismiss"),
            _Principal(),
            "dismiss-0001",
        )
        assert result == expected
