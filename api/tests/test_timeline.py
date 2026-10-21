"""Exact conform and timing safeguards; execution deferred by owner."""

from fractions import Fraction
from uuid import uuid4

import pytest

from app.evidence.contracts import EvidenceError
from app.timeline.contracts import Clip, Rate, Save, Sequence, conform, nearest, source_frame
from app.timeline.timing import verified_grid


def test_fractional_rate_and_repeated_occurrence_mapping():
    source = {"fps": {"numerator": 24000, "denominator": 1001}, "frame_count": 1000}
    clip = Clip(id=uuid4(), source_id=uuid4(), selection_id=uuid4(), in_frame=240, out_frame=480)
    sequence = Sequence()
    first = conform(clip, source, sequence, 0)
    second = conform(
        clip.model_copy(update={"id": uuid4()}), source, sequence, first["duration_frames"]
    )
    assert first["duration_frames"] == 240
    assert Fraction(**first["quantization_seconds"]) == Fraction(-1, 100)
    assert second["start_frame"] == 240 and second["id"] != first["id"]
    assert source_frame(first, sequence, 239) == 478
    assert nearest(Fraction(1, 2)) == 1
    assert Rate(numerator=48, denominator=2).model_dump() == {"numerator": 24, "denominator": 1}
    with pytest.raises(ValueError):
        Save(command_id=uuid4(), expected_revision=0, sequence=sequence, clips=[clip, clip])


def test_source_grid_rejects_vfr_and_pins_audio_offset():
    metadata = {
        "frame_rate": {"numerator": 25, "denominator": 1},
        "nominal_frame_rate": {"numerator": 25, "denominator": 1},
        "time_base": {"numerator": 1, "denominator": 1000},
        "video_start": {"numerator": 1, "denominator": 1},
        "duration": {"numerator": 3, "denominator": 25},
        "video": {"width": 1920, "height": 1080},
        "audio": [{"index": 1, "start_time": "1.12", "channels": 2, "sample_rate": "48000"}],
    }
    frames = [{"best_effort_timestamp": t} for t in (1000, 1040, 1080)]
    result = verified_grid(frames, metadata)
    assert result["frame_count"] == 3
    assert Fraction(**result["audio"]["offset_seconds"]) == Fraction(3, 25)
    with pytest.raises(EvidenceError, match="variable_rate"):
        verified_grid([frames[0], {"best_effort_timestamp": 1050}, frames[2]], metadata)
    with pytest.raises(ValueError):
        conform(
            Clip(id=uuid4(), source_id=uuid4(), selection_id=uuid4(), in_frame=0, out_frame=4),
            result,
            Sequence(),
            0,
        )
