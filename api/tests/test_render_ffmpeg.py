"""Deferred real-FFmpeg frame/audio checks; run with the later runtime acceptance suite."""

import asyncio
import hashlib
import shutil
from fractions import Fraction

import pytest

from app.media.processing import run_process
from app.renders.plan import filters


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg required")
def test_original_frame_trim_and_silent_audio_exact_lengths(tmp_path):
    # Every frame has a distinct luminance. Compare raw selected pixels, not just duration.
    original = b"".join(bytes([16 + i]) * 256 + bytes([128]) * 128 for i in range(24))
    source = tmp_path / "source.yuv"
    source.write_bytes(original)
    before = hashlib.sha256(original).hexdigest()
    clip = {
        "in_frame": 3,
        "out_frame": 9,
        "start_frame": 0,
        "duration_frames": 6,
        "muted": True,
        "source": {"audio": None},
    }
    vf, af = filters(clip, Fraction(24))
    args = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-n",
        "-f",
        "rawvideo",
        "-pixel_format",
        "yuv420p",
        "-video_size",
        "16x16",
        "-framerate",
        "24",
        "-i",
        str(source),
        "-filter_complex",
        f"[0:v:0]{vf}[v];{af}[a]",
        "-map",
        "[v]",
        "-c:v",
        "rawvideo",
        "-fps_mode",
        "passthrough",
        "-f",
        "rawvideo",
        str(tmp_path / "cut.yuv"),
        "-map",
        "[a]",
        "-c:a",
        "pcm_f32le",
        "-f",
        "f32le",
        str(tmp_path / "cut.pcm"),
    ]
    asyncio.run(run_process(args, timeout=30, check=lambda: None))
    assert (tmp_path / "cut.yuv").read_bytes() == original[3 * 384 : 9 * 384]
    assert (tmp_path / "cut.pcm").read_bytes() == bytes(12000 * 8)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
