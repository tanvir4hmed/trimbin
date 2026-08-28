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
import tempfile
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
_BLUR = re.compile(r"lavfi\.blur=([\d.]+)")
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

    # One decode, two branches.
    #
    # The split matters: motion is measured from a difference frame, which
    # destroys the picture the other filters need. Branching keeps both
    # measurements honest without paying to decode the file twice — and decoding
    # is by far the expensive part of ingest.
    #
    #   branch A: exposure, sharpness, black, freeze — on the picture itself
    #   branch B: frame-to-frame difference — how much moved between frames
    #
    # Metadata goes to files rather than stdout. ffmpeg interleaves the two
    # branches' output unpredictably, and separate files are the only way to
    # know which reading came from which branch — a difference frame's average
    # brightness is a motion figure, and reading it as exposure would report
    # every moving shot as dark.
    #
    # ffmpeg is run from the temp directory so the filenames inside the filter
    # graph are bare. A path cannot be escaped reliably there: the parser treats
    # a colon as an argument separator, which every Windows absolute path
    # contains, and the escape sequences that should fix it do not survive the
    # nested quoting.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        code, _, err = await _run([
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(source.resolve()),
            "-filter_complex", (
                "[0:v]split=2[a][b];"
                "[a]blurdetect=low=0.05:high=0.3,"
                "signalstats=stat=tout+vrep+brng,"
                "blackdetect=d=0.5:pic_th=0.98,"
                "freezedetect=n=-60dB:d=1,"
                "metadata=mode=print:file=picture.txt[sa];"
                "[b]tblend=all_mode=difference,"
                "signalstats,"
                "metadata=mode=print:key=lavfi.signalstats.YAVG:file=motion.txt[sb]"
            ),
            "-map", "[sa]", "-f", "null", "-",
            "-map", "[sb]", "-f", "null", "-",
        ], timeout_s=600, cwd=tmp_dir)

        if code == 0:
            _parse_picture(_read(tmp_dir / "picture.txt"), m)
            _parse_motion(_read(tmp_dir / "motion.txt"), m)
        else:
            log.warning("measurement failed for %s: %s", source.name, err.strip()[-300:])

        # blackdetect and freezedetect report on stderr, not through metadata.
        _parse_spans(err, m)

    # A cut to or from black is an enormous frame-to-frame difference, but it is
    # not camera movement. Reporting it as such would tell an editor a locked-off
    # take was handheld because the slate was pulled away.
    _drop_spikes_overlapping(m)

    if m.has_audio:
        await _measure_audio(source, m)

    return m


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _parse_picture(output: str, m: RawMeasurements) -> None:
    """Exposure and sharpness, from the branch that still has a picture."""
    lumas: list[float] = []
    blurs: list[float] = []
    highlight_hits = 0
    shadow_hits = 0
    frames = 0

    for line in output.splitlines():
        if blur_match := _BLUR.search(line):
            blurs.append(float(blur_match.group(1)))
            continue

        stats = dict(_SIGNALSTATS.findall(line))
        if "YAVG" not in stats:
            continue

        frames += 1
        lumas.append(float(stats["YAVG"]))
        # YMAX or YMIN pinned at the extremes means detail is gone at that end,
        # and no amount of grading brings it back.
        if float(stats.get("YMAX", 0)) >= 254:
            highlight_hits += 1
        if float(stats.get("YMIN", 255)) <= 1:
            shadow_hits += 1

    if lumas:
        m.mean_luma = sum(lumas) / len(lumas)
    if frames:
        m.highlight_clip_pct = 100 * highlight_hits / frames
        m.shadow_clip_pct = 100 * shadow_hits / frames

    # blurdetect reports how blurred a frame is, so sharpness is its inverse.
    # Expressed this way so larger always means better focus, which is what every
    # comparison downstream assumes.
    if blurs:
        m.sharpness = 1.0 / (1.0 + sum(blurs) / len(blurs))
        # Where focus went, not merely that it was soft on average. The two are
        # different problems: a soft take is unusable, a take that drifts at
        # eight seconds has eight usable seconds in it, and only a timecode tells
        # the editor which one they are holding.
        m.focus_loss_spans = _spikes(blurs, m.duration_s)


def _parse_motion(output: str, m: RawMeasurements) -> None:
    """How much changed between frames.

    This branch sees difference frames, so its average brightness is the amount
    of change — a locked-off shot is near black, a whip pan is bright.
    """
    diffs = [float(v) for _, v in _SIGNALSTATS.findall(output)]
    if not diffs:
        return
    m.motion_mean = sum(diffs) / len(diffs)
    m.motion_peak = max(diffs)
    m.motion_spikes = _spikes(diffs, m.duration_s)


def _parse_spans(stderr: str, m: RawMeasurements) -> None:
    """Black and freeze, which report on stderr rather than through metadata."""
    for start, end in _BLACK.findall(stderr):
        m.black_spans.append(Span(float(start), float(end)))

    starts = [float(s) for s in _FREEZE_START.findall(stderr)]
    ends = [float(e) for e in _FREEZE_END.findall(stderr)]
    for i, start in enumerate(starts):
        end = ends[i] if i < len(ends) else m.duration_s
        m.freeze_spans.append(Span(start, end))


def _drop_spikes_overlapping(m: RawMeasurements) -> None:
    """Remove motion spikes that coincide with a black or freeze event.

    Both produce a large frame difference without anything having moved: a cut
    to black changes every pixel, and the frame either side of a freeze does the
    same. Left in, they would report camera movement on the one kind of take
    that definitionally has none.
    """
    excluded = m.black_spans + m.freeze_spans
    if not excluded:
        return

    def overlaps(span: Span) -> bool:
        return any(
            span.start_s < other.end_s + 0.5 and other.start_s - 0.5 < span.end_s
            for other in excluded
        )

    m.motion_spikes = [s for s in m.motion_spikes if not overlaps(s)]


def _spikes(series: list[float], duration_s: float) -> list[Span]:
    """Where motion runs well above this clip's own baseline.

    Compared against the clip's own average rather than a fixed threshold: a
    handheld take is elevated throughout and has no spikes, while a locked-off
    take that gets knocked has one obvious burst. That distinction is what turns
    "this take is shaky" into "unstable 4.2s to 7.8s, clean either side" — and
    the second is a span an editor can still cut around.
    """
    if len(series) < 10 or duration_s <= 0:
        return []

    # The lower quartile, not the mean or the median.
    #
    # The faults this looks for are sustained: a handheld section runs for
    # seconds, focus can drift for half a take. Any sustained elevation drags
    # the mean up with it until the section cannot exceed a threshold derived
    # from itself, and the median falls over too once a fault covers around half
    # the clip. The lower quartile stays with the well-behaved part of the clip
    # even when most of it is not, which is the baseline actually wanted here:
    # what does this clip look like when nothing is wrong?
    ordered = sorted(series)
    baseline = ordered[len(ordered) // 4]
    if baseline <= 0:
        return []

    threshold = baseline * 2.5
    seconds_per_frame = duration_s / len(series)

    # Half a second. Anything briefer is a cut, a flash, or a subject crossing
    # frame — none of which is camera movement, and all of which would produce
    # findings an editor learns to ignore.
    min_frames = max(3, int(0.5 / seconds_per_frame))

    spans: list[Span] = []
    start_index: int | None = None

    for i, value in enumerate(series):
        if value > threshold and start_index is None:
            start_index = i
        elif value <= threshold and start_index is not None:
            if i - start_index >= min_frames:
                spans.append(Span(start_index * seconds_per_frame, i * seconds_per_frame))
            start_index = None

    if start_index is not None and len(series) - start_index >= min_frames:
        spans.append(Span(start_index * seconds_per_frame, duration_s))

    return spans


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
