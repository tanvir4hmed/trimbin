"""Measure a clip and build its proxy in one ffmpeg pass.

The measurements here are the ones a model should never be asked for. Whether a
frame is clipping, how sharp it is, how much the camera moved — these are signal
processing, and ffmpeg answers them exactly, deterministically, and for a fraction
of a cent. Asking a language model to estimate them would be slower, dearer and
less accurate, and it would put a probabilistic answer where an arithmetic one
belongs.

What the model is for is everything these numbers cannot say: whether the shake
serves the moment, whether the performance landed. That judgement needs this
data, not a replacement for it.

Two properties matter more than the individual metrics:

  Everything is timecoded. Editors choose moments inside takes, so "unstable"
  is useless where "unstable 4.2s-7.8s" becomes a link the interface can act on.

  Nothing here is normalised. These are raw per-clip values; the comparison
  against the rest of the shot happens later, once the whole group is known. A
  clip has no idea whether it is unusual until it has siblings to be unusual
  against.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# HLS settings. These are not tuning preferences — they are a contract.
#
# The assembled cut plays as one continuous stream stitched from many clips'
# segments, and that only works if every proxy shares resolution, codec and
# keyframe placement. A clip encoded differently will stall or glitch at its
# boundary, and the failure appears in playback rather than in encoding, which
# makes it expensive to trace. Changing any of these means re-encoding the
# entire archive.
PROXY_HEIGHT = 540
PROXY_BITRATE = "1200k"
PROXY_AUDIO_BITRATE = "96k"
SEGMENT_SECONDS = 4
GOP_SECONDS = SEGMENT_SECONDS  # a keyframe exactly at every segment boundary
PROXY_FPS = 25

# Sprite sheet for scrub preview, so hovering the timeline costs no video fetch.
SPRITE_INTERVAL_S = 2
SPRITE_WIDTH = 160
SPRITE_COLUMNS = 10


@dataclass(slots=True)
class Span:
    start_s: float
    end_s: float


@dataclass(slots=True)
class RawMeasurements:
    """Per-clip, un-normalised. Comparison happens once the group is known."""

    duration_s: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0

    # Exposure. mean_luma sits on 0-255; the clipped percentages are what
    # actually matter, since detail lost at either end cannot be graded back.
    mean_luma: float = 0.0
    highlight_clip_pct: float = 0.0
    shadow_clip_pct: float = 0.0

    # Focus. Higher is sharper. Only meaningful against other takes of the same
    # shot — a soft lens and a missed focus pull produce similar absolute numbers.
    sharpness: float = 0.0

    # Motion, from frame-to-frame difference. Again, only meaningful relatively:
    # a locked-off shot and a handheld one are both "correct" depending on intent.
    motion_mean: float = 0.0
    motion_peak: float = 0.0
    motion_spikes: list[Span] = field(default_factory=list)

    # Audio, EBU R128.
    audio_lufs: float = 0.0
    audio_peak_db: float = 0.0
    noise_floor_db: float = 0.0
    has_audio: bool = False

    # Faults with no interpretation needed.
    dropped_frames: int = 0
    freeze_spans: list[Span] = field(default_factory=list)
    black_spans: list[Span] = field(default_factory=list)

    def is_usable(self) -> tuple[bool, str]:
        """Tier 1: can this be cut at all?

        Deliberately narrow. This rejects footage that carries no information,
        not footage that is merely poor — a dark, shaky, badly framed take may
        still hold the performance the scene needs, and discarding it here would
        be the worst failure this system could have.
        """
        if self.duration_s < 1.0:
            return False, "clip.too_short"
        if self.width == 0 or self.height == 0:
            return False, "clip.no_video"
        # Ninety percent black is a lens cap or a camera that never rolled.
        black_total = sum(s.end_s - s.start_s for s in self.black_spans)
        if black_total > self.duration_s * 0.9:
            return False, "clip.black"
        if self.freeze_spans and sum(s.end_s - s.start_s for s in self.freeze_spans) > self.duration_s * 0.8:
            return False, "clip.frozen"
        return True, ""


class FfmpegUnavailable(RuntimeError):
    pass


def _require_ffmpeg() -> None:
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            raise FfmpegUnavailable(
                f"{binary} not found. It ships in the API container image; "
                "install it locally to run this outside the container."
            )


async def _run(
    cmd: list[str],
    timeout_s: int = 900,
    cwd: Path | None = None,
) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd) if cwd else None,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


async def probe(source: Path) -> dict:
    """Container and stream metadata. Cheap, and it tells us whether to bother."""
    _require_ffmpeg()
    code, out, err = await _run([
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(source),
    ], timeout_s=60)
    if code != 0:
        raise RuntimeError(f"ffprobe failed: {err.strip()[:300]}")
    return json.loads(out)
