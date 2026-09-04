"""The full-take intelligence gate: coverage, absolute time, and evidence."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from trimbin_agents.contracts.base import Finding, FindingCode, Severity, TimeRange
from trimbin_agents.contracts.segments import Moment, MomentKind, SegmentObservation

from app.services import full_take
from app.services import review as review_service


class TestWindowCoverage:
    def test_a_one_ten_take_reaches_its_end(self) -> None:
        windows = full_take.windows_for(70.0)
        assert [(w.start_s, w.end_s) for w in windows] == [(0.0, 60.0), (52.0, 70.0)]

    def test_every_adjacent_pair_overlaps_and_no_time_is_missing(self) -> None:
        windows = full_take.windows_for(190.0)
        assert windows[0].start_s == 0
        assert windows[-1].end_s == 190
        for left, right in pairwise(windows):
            assert right.start_s < left.end_s
            assert right.start_s <= left.end_s

    def test_invalid_window_contract_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            full_take.windows_for(70, window_s=10, overlap_s=10)


class TestRecommendationGate:
    @pytest.mark.asyncio
    async def test_no_recommendation_is_written_until_every_take_is_fully_analysed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def load(*args) -> list[dict]:
            return [
                {"clip_id": uuid4(), "analysis_complete": True},
                {"clip_id": uuid4(), "analysis_complete": False},
            ]

        monkeypatch.setattr(review_service, "_load", load)
        with pytest.raises(review_service.NotReady, match="full-take analysis is still pending"):
            await review_service.judge(1, 12, 2)


def observation(*findings: Finding) -> SegmentObservation:
    return SegmentObservation(
        description="A woman crosses the kitchen and puts a cup on the counter.",
        transcript="Put it there.",
        actions=["crosses kitchen", "sets down cup"],
        objects=["cup", "counter"],
        speakers=["woman"],
        shot_size="medium close-up",
        camera_motion="locked off",
        findings=list(findings),
    )


def focus(start: float, end: float, detail: str = "Focus drifts off the eyes.") -> Finding:
    return Finding(
        code=FindingCode.FOCUS_LOST,
        detail=detail,
        severity=Severity.ATTENTION,
        where=TimeRange(start_s=start, end_s=end),
    )


def moment(kind: MomentKind, text: str, start: float, end: float) -> Moment:
    from trimbin_agents.contracts.base import TimeRange

    return Moment(kind=kind, text=text, where=TimeRange(start_s=start, end_s=end))


class TestExactMoments:
    def test_a_local_action_in_the_second_window_gets_source_time(self) -> None:
        observed = observation().model_copy(
            update={"moments": [moment(MomentKind.ACTION, "The woman closes the door.", 6, 8)]}
        )
        window = full_take.windows_for(70.0)[1]
        found = full_take._absolute_moments(observed, window, uuid4(), [0.1] * 768)
        assert [(row["start_s"], row["end_s"]) for row in found] == [(58.0, 60.0)]

    def test_overlap_dedup_keeps_both_evidence_segments(self) -> None:
        first, second = uuid4(), uuid4()
        merged = full_take.consolidate_moments(
            [
                {
                    "kind": "dialogue",
                    "text": "Call the doctor.",
                    "start_s": 54.0,
                    "end_s": 56.0,
                    "evidence_segment_ids": [first],
                    "embedding": [],
                },
                {
                    "kind": "dialogue",
                    "text": "Call the doctor.",
                    "start_s": 54.5,
                    "end_s": 56.2,
                    "evidence_segment_ids": [second],
                    "embedding": [],
                },
            ]
        )
        assert len(merged) == 1
        assert merged[0]["evidence_segment_ids"] == [first, second]


class TestAbsoluteFindings:
    def test_a_local_six_seconds_in_the_second_window_is_source_0058(self) -> None:
        window = full_take.windows_for(70.0)[1]
        found = full_take._absolute_findings(observation(focus(6, 9)), window, uuid4())
        assert found[0]["start_s"] == 58.0
        assert found[0]["end_s"] == 61.0

    def test_performance_is_never_a_machine_finding(self) -> None:
        finding = Finding(
            code=FindingCode.PERFORMANCE_NOTE,
            detail="A subjective preference.",
            severity=Severity.NOTE,
            where=TimeRange(start_s=1, end_s=2),
        )
        assert (
            full_take._absolute_findings(
                observation(finding), full_take.windows_for(10)[0], uuid4()
            )
            == []
        )


class TestOverlapConsolidation:
    def test_one_issue_keeps_both_window_evidence_ids(self) -> None:
        first, second = uuid4(), uuid4()
        merged = full_take.consolidate_findings(
            [
                {
                    "code": "focus.lost",
                    "detail": "Focus drifts.",
                    "severity": "attention",
                    "start_s": 58.0,
                    "end_s": 60.0,
                    "evidence_segment_ids": [first],
                },
                {
                    "code": "focus.lost",
                    "detail": "Focus drifts off the eyes.",
                    "severity": "attention",
                    "start_s": 58.0,
                    "end_s": 61.0,
                    "evidence_segment_ids": [second],
                },
            ]
        )
        assert len(merged) == 1
        assert merged[0]["start_s"] == 58.0
        assert merged[0]["end_s"] == 61.0
        assert merged[0]["evidence_segment_ids"] == [first, second]

    def test_two_separate_focus_losses_remain_two_findings(self) -> None:
        merged = full_take.consolidate_findings(
            [
                {
                    "code": "focus.lost",
                    "detail": "first",
                    "severity": "attention",
                    "start_s": 10.0,
                    "end_s": 12.0,
                    "evidence_segment_ids": [uuid4()],
                },
                {
                    "code": "focus.lost",
                    "detail": "second",
                    "severity": "attention",
                    "start_s": 30.0,
                    "end_s": 32.0,
                    "evidence_segment_ids": [uuid4()],
                },
            ]
        )
        assert len(merged) == 2


class _Observer:
    calls = 0

    async def run(self, video: bytes, *, duration_s: float, briefing: str = ""):
        self.calls += 1
        if self.calls == 1:
            return observation(focus(58, 60, "Focus begins to drift."))
        return observation(focus(6, 9, "Focus drifts off the eyes."))


class TestEndToEndPersistenceShape:
    @pytest.mark.asyncio
    async def test_the_0058_issue_is_persisted_once_with_two_evidence_windows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clip_id = uuid4()
        runs: list[dict] = []
        stored_segments: list[dict] = []
        stored_findings: list[dict] = []

        async def not_done(project_id: int, key: str) -> bool:
            return False

        async def record_run(**kwargs):
            runs.append(kwargs)

        async def record_segments(rows: list[dict]) -> int:
            stored_segments.extend(rows)
            return len(rows)

        async def record_findings(rows: list[dict]) -> int:
            stored_findings.extend(rows)
            return len(rows)

        async def no_measured_findings(project_id: int, current_clip_id: UUID) -> list[dict]:
            return []

        def download(prefix: str, destination: Path, start: float, end: float) -> bool:
            destination.write_bytes(b"transport stream")
            return True

        async def remux(source: Path, destination: Path, seconds: float):
            destination.write_bytes(b"video")
            return destination

        async def embed(text: str, *, subject: str = "segment") -> list[float]:
            return [0.25] * full_take.EMBEDDING_DIMENSIONS

        class EmptyShot:
            is_empty = True

        async def shot(project_id: int, scene: int, shot_no: int):
            return EmptyShot()

        monkeypatch.setattr(full_take.analysis_store, "already_completed", not_done)
        monkeypatch.setattr(full_take.analysis_store, "record_run", record_run)
        monkeypatch.setattr(full_take.analysis_store, "record_segments", record_segments)
        monkeypatch.setattr(full_take.analysis_store, "record_finding_events", record_findings)
        monkeypatch.setattr(full_take.analysis_store, "raw_findings", no_measured_findings)
        monkeypatch.setattr(full_take.storage, "download_proxy_range", download)
        monkeypatch.setattr(full_take, "remux", remux)
        monkeypatch.setattr(full_take.identify, "embed_text", embed)
        monkeypatch.setattr(full_take.shots, "get", shot)
        monkeypatch.setattr(full_take.shots, "briefing", lambda *args: "")

        result = await full_take.analyse_clip(
            project_id=1,
            clip_id=clip_id,
            scene=12,
            shot=2,
            duration_s=70.0,
            agent=_Observer(),
        )

        assert result["status"] == "completed"
        assert result["covered_until_s"] == 70.0
        assert len(stored_segments) == 2
        assert len(stored_findings) == 1
        finding = stored_findings[0]
        assert finding["start_s"] == 58.0
        assert finding["end_s"] == 61.0
        assert len(finding["evidence_segment_ids"]) == 2
        assert runs[0]["state"] == "started"
        assert runs[-1]["state"] == "completed"
        assert runs[-1]["covered_until_s"] == 70.0

    def test_run_identity_changes_when_the_prompt_changes(self) -> None:
        clip_id = UUID("00000000-0000-0000-0000-000000000001")
        assert full_take.run_key(1, clip_id, 70, "segment/v1") != full_take.run_key(
            1, clip_id, 70, "segment/v2"
        )
