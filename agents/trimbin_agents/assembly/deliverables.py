"""The two things assembly hands over: an EDL and a playlist.

Both describe the same cut in different languages. The EDL is for the editor's
NLE, which is where the real work happens — Trimbin does the job around the cut
and never the cut itself. The playlist is for watching it here, without a render.

Neither is an export in the usual sense. Nothing is transcoded, nothing is
written but text, and regenerating either costs nothing — which is what lets an
override be reflected on the next play rather than after a wait.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..contracts.assembly import Selection

log = logging.getLogger(__name__)

# CMX3600 is forty years old and every NLE on earth reads it. A newer
# interchange format would be more expressive and less useful.
EDL_FPS = 25

# Must match the proxy encoder exactly. The playlist stitches segments from many
# clips into one stream, and that only holds if every clip was cut on the same
# boundaries — a mismatch stalls playback at the join, and the symptom appears
# nowhere near the cause.
SEGMENT_SECONDS = 4


@dataclass(frozen=True)
class ClipMedia:
    """What assembly needs to know about a clip to reference it."""

    reel: str            # short name the NLE shows
    source_uri: str      # the original, for conform
    playlist_uri: str    # the proxy's own HLS manifest
    duration_s: float


def _timecode(seconds: float, fps: int = EDL_FPS) -> str:
    """HH:MM:SS:FF. The EDL format predates fractional frame rates and does not
    accommodate them, so the value is truncated rather than rounded — a frame
    early conforms, a frame late loses the first frame of the take."""
    total_frames = int(seconds * fps)
    frames = total_frames % fps
    total_seconds = total_frames // fps
    return (
        f"{total_seconds // 3600:02d}:"
        f"{(total_seconds % 3600) // 60:02d}:"
        f"{total_seconds % 60:02d}:"
        f"{frames:02d}"
    )


def build_edl(
    title: str,
    selections: list[Selection],
    media: dict[str, ClipMedia],
) -> str:
    """A CMX3600 edit decision list.

    Source timecodes are where the material sits inside the original take;
    record timecodes are where it lands in the assembled sequence. Getting these
    the wrong way round produces a file that opens without complaint and conforms
    to the wrong frames, which is worse than one that fails.
    """
    lines = [
        f"TITLE: {title}",
        "FCM: NON-DROP FRAME",
        "",
    ]

    record_position = 0.0

    for index, selection in enumerate(selections, start=1):
        clip = media.get(str(selection.clip_id))
        if clip is None:
            # A selection whose media is missing would silently shorten the cut.
            # Recorded as a comment so the gap is visible in the file itself.
            lines.append(f"* MISSING MEDIA FOR SHOT {selection.subgroup_id}")
            continue

        duration = selection.span.end_s - selection.span.start_s

        lines.append(
            f"{index:03d}  {clip.reel:<8} V     C        "
            f"{_timecode(selection.span.start_s)} {_timecode(selection.span.end_s)} "
            f"{_timecode(record_position)} {_timecode(record_position + duration)}"
        )
        # The reason travels with the cut. An editor opening this in six months
        # gets the why alongside the what, which is the entire point of the
        # system and costs one comment line.
        lines.append(f"* FROM CLIP NAME: {clip.reel} TAKE {selection.take_no}")
        lines.append(f"* COMMENT: {selection.reason}")
        lines.append("")

        record_position += duration

    return "\n".join(lines)


def build_playlist(
    selections: list[Selection],
    media: dict[str, ClipMedia],
) -> str:
    """An HLS manifest that plays the selected spans as one continuous film.

    No rendering. The segments already exist from proxy generation, and this is
    a text file that points at the ones the cut uses, in order. That is why an
    override is visible on the next play instead of after an export — and why
    watching the assembly is cheap enough to be the default way to review it.

    EXT-X-DISCONTINUITY marks every join. Without it a player assumes one
    continuous timeline and drifts out of sync within a few clips, because the
    segments genuinely come from different encodes.
    """
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        f"#EXT-X-TARGETDURATION:{SEGMENT_SECONDS}",
        "#EXT-X-PLAYLIST-TYPE:VOD",
        "#EXT-X-MEDIA-SEQUENCE:0",
    ]

    for selection in selections:
        clip = media.get(str(selection.clip_id))
        if clip is None:
            log.warning(
                "shot %d selected but has no proxy; omitted from playlist",
                selection.subgroup_id,
            )
            continue

        lines.append("#EXT-X-DISCONTINUITY")
        # The player is told which shot and take it is watching, so the overlay
        # in the interface reads it from the stream rather than tracking position
        # separately and drifting.
        lines.append(
            f'#EXT-X-DATERANGE:ID="s{selection.group_id}-{selection.subgroup_id}",'
            f'X-TAKE={selection.take_no},'
            f'X-REASON="{_escape(selection.reason)}"'
        )

        for segment in _segments_for(selection, clip):
            lines.append(f"#EXTINF:{segment.duration:.3f},")
            lines.append(segment.uri)

    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines)


@dataclass(frozen=True)
class _Segment:
    uri: str
    duration: float


def _segments_for(selection: Selection, clip: ClipMedia) -> list[_Segment]:
    """Which of a clip's segments the selected span covers.

    Segment boundaries are fixed at encode time, so a span rarely lands on one.
    The range is widened to whole segments rather than narrowed: a fraction of a
    second of extra material at each end is invisible, while cutting a segment
    short would need a re-encode and defeat the point of not rendering.
    """
    first = int(selection.span.start_s // SEGMENT_SECONDS)
    last = int((selection.span.end_s - 0.001) // SEGMENT_SECONDS)

    base = clip.playlist_uri.rsplit("/", 1)[0]
    total = max(1, int(clip.duration_s // SEGMENT_SECONDS) + 1)

    return [
        _Segment(uri=f"{base}/seg_{i:04d}.ts", duration=float(SEGMENT_SECONDS))
        for i in range(first, min(last, total - 1) + 1)
    ]


def _escape(value: str) -> str:
    """Attribute values in a manifest are quoted, so quotes inside them break
    the line — and a malformed tag takes the whole playlist with it."""
    return value.replace('"', "'").replace("\n", " ")
