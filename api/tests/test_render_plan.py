"""Deferred render contracts; these do not establish encoded fidelity."""

from fractions import Fraction

import pytest
from test_editable_exports import example as timeline_example

from app.evidence.contracts import EvidenceError
from app.renders.plan import filters, samples, validated


def example():
    body, media = timeline_example()
    for clip in body["clips"]:
        clip["source"]["color"] = dict(
            color_space="bt709",
            color_transfer="bt709",
            color_primaries="bt709",
            color_range="tv",
            pix_fmt="yuv420p",
        )
        clip["source"]["audio"]["stream_index"] = 1
    return body, media


def test_audio_boundaries_do_not_accumulate_rounding():
    fps = Fraction(30000, 1001)
    cuts = [{"start_frame": i, "duration_frames": 1} for i in range(10000)]
    assert sum(samples(c, fps) for c in cuts) == 16016000
    assert set(samples(c, fps) for c in cuts) == {1601, 1602}


@pytest.mark.parametrize(
    "field,value",
    [("pix_fmt", "yuv420p10le"), ("color_transfer", "smpte2084"), ("color_range", None)],
)
def test_no_implicit_color_downgrade(field, value):
    body, _ = example()
    body["clips"][0]["source"]["color"][field] = value
    with pytest.raises(EvidenceError, match="render_requires_explicit"):
        validated(body)


def test_delayed_audio_and_muted_cut():
    body, _ = example()
    validated(body)
    clip = body["clips"][0]
    clip["source"]["audio"]["offset_seconds"] = {"numerator": 1, "denominator": 1}
    video, audio = filters(clip, Fraction(30000, 1001))
    assert "start_frame=15:end_frame=45" in video
    assert "adelay=23976S" in audio
    assert "volume=-6.0dB" in audio
    _, silent = filters(body["clips"][1], Fraction(30000, 1001))
    assert silent.startswith("anullsrc=")


def test_resolution_change_fails_instead_of_upscaling():
    body, _ = example()
    body["sequence"]["width"] = 3840
    with pytest.raises(EvidenceError, match="render_scaling_not_supported"):
        validated(body)
