"""Human finding decisions remain current, attributed, and recoverable."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

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
    def test_old_run_review_does_not_reappear_in_current_analysis(self) -> None:
        finding = current_finding()
        old = {
            **finding,
            "finding_id": uuid4(),
            "event_id": uuid4(),
            "run_id": uuid4(),
            "action": "human_confirmed",
            "rev": 1,
        }
        result = finding_actions.overlay(
            {"run": {"run_id": finding["run_id"]}, "findings": [finding], "history": []},
            [old],
        )
        assert result["findings"] == [finding]
        assert result["history"][0]["event_id"] == old["event_id"]

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


def read_model(finding: dict, duration_s: float = 70.0) -> dict:
    return {
        "clip": {"duration_s": duration_s, "scene": 12, "shot": 2},
        "findings": [finding],
        "history": [],
    }


class TestFindingCommandSafety:
    @pytest.mark.asyncio
    async def test_dismiss_clamps_an_overlong_full_take_finding(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        finding = {**current_finding(), "start_s": 0.0, "end_s": 59.6264}
        committed = finding_actions.Committed(uuid4(), finding["finding_id"], 1, "human_dismissed")
        captured: dict = {}

        async def read(project_id: int, clip_id):
            return read_model(finding, duration_s=59.626)

        async def commit(**kwargs):
            captured.update(kwargs)
            return committed

        monkeypatch.setattr(analysis.finding_actions, "replay", AsyncMock(return_value=None))
        monkeypatch.setattr(analysis, "_read", read)
        monkeypatch.setattr(analysis.finding_actions, "commit", commit)
        monkeypatch.setattr(analysis.finding_actions, "deliver", AsyncMock(return_value=True))
        monkeypatch.setattr(analysis.activity, "record", AsyncMock())

        result = await analysis.act_on_finding(
            1,
            uuid4(),
            finding["finding_id"],
            analysis.FindingCommand(rev=0, action="dismiss"),
            _Principal(),
            "dismiss-0001",
        )

        assert result["action"] == "human_dismissed"
        assert captured["changes"]["start_s"] == 0.0
        assert captured["changes"]["end_s"] == 59.626

    @pytest.mark.asyncio
    async def test_a_stale_finding_action_is_a_409(self, monkeypatch: pytest.MonkeyPatch) -> None:
        finding = current_finding()

        async def no_replay(*args):
            return None

        async def read(project_id: int, clip_id):
            return read_model(finding)

        async def stale(**kwargs):
            raise revisions.Conflict(kwargs["expected_rev"], 1)

        monkeypatch.setattr(analysis.finding_actions, "replay", no_replay)
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

        async def replay(*args):
            return finding_actions.Committed(
                event_id=UUID(expected["event_id"]),
                finding_id=finding["finding_id"],
                rev=1,
                action="human_dismissed",
                replayed=True,
            )

        async def delivered(*args):
            return True

        async def should_not_commit(**kwargs):
            raise AssertionError("a replay must not create a second event")

        monkeypatch.setattr(analysis.finding_actions, "replay", replay)
        monkeypatch.setattr(analysis.finding_actions, "deliver", delivered)
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
