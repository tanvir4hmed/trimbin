"""Source-time regressions for agent finetuning; no cloud credentials required."""

import csv
import io
import math
import shutil
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from trimbin_agents.segment.agent import PROMPT_VERSION

from app.services import analysis_store, clips, exports, ffmpeg_ops, ranges
from app.services.measure import RawMeasurements, Span


def test_sustained_motion_from_digital_stillness_and_isolated_flash():
    assert ffmpeg_ops._spikes([0.0] * 30 + [10.0] * 10 + [0.0] * 60, 10)
    assert not ffmpeg_ops._spikes([0.0] * 30 + [30.0] + [0.0] * 69, 10)


def test_mild_handheld_motion_is_not_reported_as_camera_shake():
    assert not ffmpeg_ops._spikes([0.0] * 30 + [3.5] * 10 + [0.0] * 60, 10)


def test_black_and_freeze_boundaries_do_not_become_camera_shake():
    measured = RawMeasurements(
        duration_s=10,
        motion_spikes=[Span(1, 2), Span(5, 6), Span(8, 9)],
        black_spans=[Span(0.5, 1.5)],
        freeze_spans=[Span(5.5, 6.5)],
    )
    ffmpeg_ops._drop_spikes_overlapping(measured)
    assert measured.motion_spikes == [Span(8, 9)]


def test_silence_is_localized_and_does_not_bridge_an_audible_gap():
    text = "silence_start: 0\nsilence_end: 1\nsilence_start: 1.5\nsilence_end: 2\nsilence_start: 9"
    measured = RawMeasurements(duration_s=10, silence_spans=ffmpeg_ops._silence_spans(text, 10))
    codes, starts, ends = clips._findings_columns(measured)
    assert codes == ["audio.silence"] * 3
    assert starts == [0, 1.5, 9]
    assert ends == [1, 2, 10]
    assert "audio.dropout" not in codes  # Silence alone cannot prove a dropout.


@pytest.mark.parametrize("action", ["human_confirmed", "human_corrected", "human_range_adjusted"])
def test_confirmed_issue_removes_even_short_span(action):
    found, _ = ranges.safe_ranges(
        10,
        [
            {
                "code": "frame.obstruction",
                "start_s": 4.001,
                "end_s": 4.101,
                "severity": "attention",
                "action": action,
            }
        ],
    )
    assert len(found) == 2
    assert found[0].end_s <= 4.001
    assert found[1].start_s >= 4.101


def test_explicit_dismissal_restores_usable_time():
    found, _ = ranges.safe_ranges(
        10,
        [
            {
                "code": "slate.present",
                "start_s": 0,
                "end_s": 3,
                "severity": "attention",
                "action": "human_dismissed",
            }
        ],
    )
    assert found == [ranges.Range(0, 10)]


def selection(start, end):
    return {"clip_id": "clip", "source_in_s": start, "source_out_s": end}


def test_save_rejects_same_source_overlap_but_allows_adjacent_ranges():
    ranges.validate_selections([selection(0, 10), selection(10, 20)], {})
    with pytest.raises(HTTPException, match="overlap"):
        ranges.validate_selections([selection(10, 20), selection(12, 30)], {})


def test_save_refuses_issue_overlap_even_during_archive_delay():
    evidence = {
        "clip": {
            "findings": [
                {
                    "start_s": 4,
                    "end_s": 6,
                    "action": "human_confirmed",
                }
            ]
        }
    }
    with pytest.raises(HTTPException, match="issue"):
        ranges.validate_selections([selection(0, 10)], evidence)
    evidence["clip"]["findings"][0]["action"] = "human_dismissed"
    ranges.validate_selections([selection(0, 10)], evidence)


async def test_backfill_selects_old_prompt_without_touching_active_runs(monkeypatch):
    query = AsyncMock(return_value=SimpleNamespace(column_names=[], result_rows=[]))
    monkeypatch.setattr(
        analysis_store, "client", AsyncMock(return_value=SimpleNamespace(query=query))
    )
    assert await analysis_store.active_clips_without_analysis(7) == []
    sql = query.call_args.args[0]
    assert "r.state = 'completed' AND r.prompt_version !=" in sql
    assert query.call_args.kwargs["parameters"] == {"p": 7, "version": PROMPT_VERSION}


async def test_shot_comparison_keeps_human_acceptance_for_safe_ranges(monkeypatch):
    clip_id = uuid4()
    query = AsyncMock(
        side_effect=[
            SimpleNamespace(result_rows=[(clip_id,)]),
            SimpleNamespace(
                result_rows=[
                    (clip_id, "frame.obstruction", 4, 6, "foreground", "note", "human_confirmed")
                ]
            ),
        ]
    )
    monkeypatch.setattr(
        analysis_store, "client", AsyncMock(return_value=SimpleNamespace(query=query))
    )
    _, findings = await analysis_store.working_findings_for_clips(7, [clip_id])
    usable, _ = ranges.safe_ranges(10, findings[str(clip_id)])
    assert usable == [ranges.Range(0, 4), ranges.Range(6, 10)]


async def test_coverage_endpoint_rejects_overlap_before_committing(monkeypatch):
    from app.routes import analysis, review

    clip_id = uuid4()
    monkeypatch.setattr(review.revisions, "replay", AsyncMock(return_value=None))
    monkeypatch.setattr(
        review.review_service,
        "takes_in_shot",
        AsyncMock(return_value=[{"clip_id": clip_id, "duration_s": 30, "take_no": 1}]),
    )
    monkeypatch.setattr(
        analysis,
        "_read",
        AsyncMock(
            return_value={"findings": [{"start_s": 10, "end_s": 20, "action": "human_confirmed"}]}
        ),
    )
    commit = AsyncMock()
    monkeypatch.setattr(review.selections, "commit_coverage", commit)
    body = review.CoverageCommand(
        rev=0,
        reason="Selected usable action",
        segments=[{"clip_id": clip_id, "source_in_s": 12, "source_out_s": 30}],
    )
    principal = SimpleNamespace(email="editor@example.com", assert_can_comment=AsyncMock())
    with pytest.raises(HTTPException, match="issue"):
        await review.set_coverage(7, 1, 1, body, principal)
    commit.assert_not_awaited()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg executable required")
async def test_real_pcm_silence_detection_and_finite_loudness(tmp_path):
    # Representative media, not mocked stderr: silence/tone/silence, then pure silence.
    for name, expression, expected in [
        ("gaps", "if(between(t,1,2),0.2*sin(2*PI*440*t),0)", [(0, 1), (2, 3)]),
        ("silent", "0", [(0, 3)]),
    ]:
        source = tmp_path / f"{name}.wav"
        code, _, err = await ffmpeg_ops._run(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-f",
                "lavfi",
                "-i",
                f"aevalsrc='{expression}':s=48000:d=3",
                "-c:a",
                "pcm_s16le",
                str(source),
            ]
        )
        assert code == 0, err
        measured = RawMeasurements(duration_s=3, has_audio=True)
        await ffmpeg_ops._measure_audio(source, measured)
        assert len(measured.silence_spans) == len(expected)
        for span, (start, end) in zip(measured.silence_spans, expected, strict=True):
            assert span.start_s == pytest.approx(start, abs=0.03)
            assert span.end_s == pytest.approx(end, abs=0.03)
        assert math.isfinite(measured.audio_lufs)
        assert math.isfinite(measured.noise_floor_db)


def test_marker_splits_across_used_ranges_without_marking_removed_gap():
    entries = [
        {"clip_id": "c", "start_s": 0, "end_s": 5},
        {"clip_id": "c", "start_s": 10, "end_s": 15},
    ]
    findings = [
        {"clip_id": "c", "start_s": 3, "end_s": 12, "code": "context"},
        {"clip_id": "c", "start_s": 6, "end_s": 9, "code": "removed_issue"},
    ]
    rows = list(csv.DictReader(io.StringIO(exports.markers(entries, findings, []))))
    assert [(r["In"], r["Out"]) for r in rows] == [
        ("00:00:03:00", "00:00:05:00"),
        ("00:00:05:00", "00:00:07:00"),
    ]
    assert all(r["Marker Name"] == "context" for r in rows)


def test_edl_source_and_record_durations_match_without_subframe_drift():
    entries = [{"clip_id": str(i), "start_s": 0.02, "end_s": 0.08} for i in range(40)]
    text = exports.edl("Quantization regression", entries, fps=24)
    events = [line.split() for line in text.splitlines() if line[:3].isdigit()]

    def frames(tc):
        h, m, s, f = map(int, tc.split(":"))
        return ((h * 60 + m) * 60 + s) * 24 + f

    cursor = 0
    for event in events:
        source_in, source_out, record_in, record_out = map(frames, event[-4:])
        assert record_in == cursor
        assert source_out - source_in == record_out - record_in == 2
        cursor = record_out
    assert cursor == 80
    assert "SOURCE TC IS ZERO-BASED" in text
    assert "ORIGINAL FILENAME MISSING" in text
