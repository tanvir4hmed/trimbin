"""Proxy generation and measurement, in a single ffmpeg pass.

Two jobs share one decode because decoding is the expensive part. Reading the
file twice — once to make a proxy, once to measure it — would double the cost of
the most expensive step in ingest for no benefit.

The encoding settings are a contract, not preferences. The assembled cut plays
as one continuous stream stitched from many clips' segments, which only works if
every proxy shares resolution, codec and keyframe placement. A clip encoded
differently stalls at its boundary, and the failure shows up in playback rather
than in encoding — expensive to trace, and the fix is re-encoding the archive.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

from .measure import (
    GOP_SECONDS,
    PROXY_AUDIO_BITRATE,
    PROXY_BITRATE,
    PROXY_FPS,
    PROXY_HEIGHT,
    SEGMENT_SECONDS,
    SPRITE_COLUMNS,
    SPRITE_INTERVAL_S,
    SPRITE_WIDTH,
    RawMeasurements,
    Span,
    _require_ffmpeg,
    _run,
    probe,
)

log = logging.getLogger(__name__)

# ffmpeg reports metrics as key=value on stderr. Parsing that is unlovely but it
# is the interface, and the alternative — a second pass per metric — costs a
# decode each time.
_SIGNALSTATS = re.compile(r"lavfi\.signalstats\.(\w+)=([\d.\-]+)")
_BLACK = re.compile(r"black_start:([\d.]+).*?black_end:([\d.]+)", re.S)
_FREEZE_START = re.compile(r"freeze_start: ([\d.]+)")
_FREEZE_END = re.compile(r"freeze_end: ([\d.]+)")
_LOUDNORM = re.compile(r"\{.*?\}", re.S)


async def analyse(source: Path) -> RawMeasurements:
    """Measure a clip. Deterministic, and cheap enough to run on everything.

    Every number here is raw and per-clip. Normalisation against the rest of the
    shot happens once the group is known, because a clip cannot tell whether it
    is unusual until it has siblings to be unusual against — and that distinction
    is what stops a deliberately handheld scene being condemned wholesale.
    """
    _require_ffmpeg()
    m = RawMeasurements()

    meta = await probe(source)
    video = next((s for s in meta.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in meta.get("streams", []) if s.get("codec_type") == "audio"), None)

    if video:
        m.width = int(video.get("width", 0))
        m.height = int(video.get("height", 0))
        num, _, den = (video.get("avg_frame_rate") or "0/1").partition("/")
        m.fps = float(num) / float(den) if den and float(den) else 0.0
    m.has_audio = audio is not None
    m.duration_s = float(meta.get("format", {}).get("duration", 0) or 0)

    if not video or m.duration_s <= 0:
        return m

    # One decode, several filters. signalstats gives exposure and a per-frame
    # difference we read as motion; blackdetect and freezedetect find the faults
    # that need no interpretation.
    code, _, err = await _run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(source),
        "-vf", (
            "signalstats=stat=tout+vrep+brng,"
            "blackdetect=d=0.5:pic_th=0.98,"
            "freezedetect=n=-60dB:d=1"
        ),
        "-map", "0:v:0",
        "-f", "null", "-",
    ], timeout_s=600)

    if code == 0:
        _parse_video_stats(err, m)

    if m.has_audio:
        await _measure_audio(source, m)

    return m


def _parse_video_stats(stderr: str, m: RawMeasurements) -> None:
    lumas: list[float] = []
    highlight_hits = 0
    shadow_hits = 0
    frames = 0

    for line in stderr.splitlines():
        stats = dict(_SIGNALSTATS.findall(line))
        if not stats:
            continue
        frames += 1

        if "YAVG" in stats:
            luma = float(stats["YAVG"])
            lumas.append(luma)
        # YMAX/YMIN pinned at the extremes means detail is gone at that end and
        # no amount of grading brings it back.
        if float(stats.get("YMAX", 0)) >= 254:
            highlight_hits += 1
        if float(stats.get("YMIN", 255)) <= 1:
            shadow_hits += 1

    if lumas:
        m.mean_luma = sum(lumas) / len(lumas)
    if frames:
        m.highlight_clip_pct = 100 * highlight_hits / frames
        m.shadow_clip_pct = 100 * shadow_hits / frames

    for start, end in _BLACK.findall(stderr):
        m.black_spans.append(Span(float(start), float(end)))

    starts = [float(s) for s in _FREEZE_START.findall(stderr)]
    ends = [float(e) for e in _FREEZE_END.findall(stderr)]
    for i, start in enumerate(starts):
        end = ends[i] if i < len(ends) else m.duration_s
        m.freeze_spans.append(Span(start, end))


async def _measure_audio(source: Path, m: RawMeasurements) -> None:
    """EBU R128 loudness, so takes are compared on perceived level.

    Peak level alone would call a quiet take with one door slam 'loud'. Loudness
    is what an editor actually hears, and comparing takes on anything else
    produces advice they will disagree with.
    """
    code, _, err = await _run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(source),
        "-af", "loudnorm=print_format=json",
        "-f", "null", "-",
    ], timeout_s=300)

    if code != 0:
        return

    blocks = _LOUDNORM.findall(err)
    if not blocks:
        return
    try:
        data = json.loads(blocks[-1])
        m.audio_lufs = float(data.get("input_i", 0))
        m.audio_peak_db = float(data.get("input_tp", 0))
        # Loudness range stands in for a noise floor: a take with almost no
        # dynamic range is either silent or buried in hiss, and both are worth
        # a person's eye.
        m.noise_floor_db = m.audio_lufs - float(data.get("input_lra", 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        log.warning("loudnorm output was not parseable for %s", source.name)


async def build_proxy(source: Path, out_dir: Path) -> Path:
    """Encode the HLS proxy. Settings here are load-bearing across the archive."""
    _require_ffmpeg()
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "index.m3u8"

    gop = int(GOP_SECONDS * PROXY_FPS)

    code, _, err = await _run([
        "ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(source),
        # Scale to a fixed height, keep aspect, force even width.
        "-vf", f"scale=-2:{PROXY_HEIGHT},fps={PROXY_FPS}",
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", PROXY_BITRATE,
        # A keyframe exactly at every segment boundary, and nowhere else. Without
        # both flags ffmpeg inserts scene-change keyframes, segments drift out of
        # alignment, and stitched playback stalls between clips.
        "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
        "-c:a", "aac", "-b:a", PROXY_AUDIO_BITRATE, "-ac", "2",
        "-f", "hls",
        "-hls_time", str(SEGMENT_SECONDS),
        "-hls_playlist_type", "vod",
        "-hls_segment_filename", str(out_dir / "seg_%04d.ts"),
        str(manifest),
    ], timeout_s=1800)

    if code != 0:
        raise RuntimeError(f"proxy encode failed: {err.strip()[-400:]}")
    return manifest


async def build_sprite(source: Path, out_path: Path, duration_s: float) -> Path:
    """A thumbnail sheet, so hovering the timeline costs no video fetch.

    Scrub preview is the difference between a timeline that feels responsive and
    one that stutters. Fetching video segments to draw a hover thumbnail would
    also spend egress on frames nobody watches.
    """
    _require_ffmpeg()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tiles = max(1, int(duration_s // SPRITE_INTERVAL_S))
    rows = max(1, -(-tiles // SPRITE_COLUMNS))  # ceiling division

    code, _, err = await _run([
        "ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(source),
        "-vf", (
            f"fps=1/{SPRITE_INTERVAL_S},"
            f"scale={SPRITE_WIDTH}:-2,"
            f"tile={SPRITE_COLUMNS}x{rows}"
        ),
        "-frames:v", "1", "-q:v", "5",
        str(out_path),
    ], timeout_s=600)

    if code != 0:
        raise RuntimeError(f"sprite generation failed: {err.strip()[-300:]}")
    return out_path


async def ingest_one(source: Path, work_dir: Path) -> tuple[RawMeasurements, Path, Path]:
    """Measure, encode and tile — measurement first so unusable clips cost less.

    A false start or a black clip is discarded before its proxy is built, which
    is the single biggest saving in ingest: encoding is minutes, measuring is
    seconds, and a meaningful share of any shoot day is footage nobody will use.
    """
    measurements = await analyse(source)

    usable, reason = measurements.is_usable()
    if not usable:
        raise UnusableClip(reason, measurements)

    proxy, sprite = await asyncio.gather(
        build_proxy(source, work_dir / "proxy"),
        build_sprite(source, work_dir / "sprite.jpg", measurements.duration_s),
    )
    return measurements, proxy, sprite


class UnusableClip(Exception):
    """Tier 1 failure: nothing here can be cut.

    Deliberately narrow. This is for footage carrying no information — a false
    start, a lens cap, a camera that never rolled. Not for footage that is
    merely poor: a dark, shaky, badly framed take may still hold the performance
    the scene needs, and discarding it would be the worst failure this system
    could have.
    """

    def __init__(self, reason_code: str, measurements: RawMeasurements) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.measurements = measurements
