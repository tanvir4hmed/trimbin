"""Tests for the EDL and the playlist.

Both are text files that other software reads without complaining much, which is
what makes them worth testing carefully: a malformed EDL conforms to the wrong
frames rather than failing, and a malformed playlist stalls during playback with
no indication of why.
"""

from __future__ import annotations

from uuid import uuid4

from trimbin_agents.assembly.deliverables import (
    ClipMedia,
    _timecode,
    build_edl,
    build_playlist,
)
from trimbin_agents.contracts.assembly import Selection
from trimbin_agents.contracts.base import TimeRange


def _selection(
    subgroup_id: int = 3,
    start: float = 1.0,
    end: float = 9.0,
    take_no: int = 4,
    reason: str = "cleanest complete take",
):
    return Selection(
        group_id=12,
        subgroup_id=subgroup_id,
        clip_id=uuid4(),
        take_no=take_no,
        span=TimeRange(start_s=start, end_s=end),
        reason=reason,
        score=0.9,
        margin=0.4,
    )


def _media(selection: Selection, duration: float = 30.0) -> dict[str, ClipMedia]:
    return {
        str(selection.clip_id): ClipMedia(
            reel=f"S12_{selection.subgroup_id}",
            source_uri="gs://originals/x.mov",
            playlist_uri="https://cdn/p1/abc/index.m3u8",
            duration_s=duration,
        )
    }


class TestTimecode:
    def test_frames_are_truncated_not_rounded(self) -> None:
        """A frame early conforms; a frame late loses the first frame of the
        take. The EDL format has no way to express the difference, so the
        direction of the error is the decision."""
        assert _timecode(1.999, fps=25) == "00:00:01:24"

    def test_hours_carry(self) -> None:
        assert _timecode(3661.0, fps=25) == "01:01:01:00"

    def test_zero_is_valid(self) -> None:
        assert _timecode(0.0) == "00:00:00:00"


class TestEdl:
    def test_record_timecodes_run_continuously(self) -> None:
        """Source timecodes say where material sits in the take; record
        timecodes say where it lands in the sequence. Confusing them produces a
        file that opens cleanly and conforms to the wrong frames."""
        a = _selection(subgroup_id=1, start=2.0, end=6.0)
        b = _selection(subgroup_id=2, start=0.0, end=5.0)
        media = {**_media(a), **_media(b)}

        edl = build_edl("Scene 12", [a, b], media)
        events = [ln for ln in edl.splitlines() if ln.startswith(("001", "002"))]

        # First event lands at zero in the sequence, second immediately after.
        assert "00:00:00:00 00:00:04:00" in events[0]
        assert "00:00:04:00 00:00:09:00" in events[1]

    def test_the_reason_travels_with_the_cut(self) -> None:
        """An editor opening this months later gets the why alongside the what,
        which is the whole product, and costs one comment line."""
        s = _selection(reason="director wanted the wider frame")
        edl = build_edl("Scene 12", [s], _media(s))
        assert "director wanted the wider frame" in edl

    def test_missing_media_is_visible_in_the_file(self) -> None:
        """A silently shortened cut is the worst outcome. The gap has to be
        legible in the artifact itself, not only in a log nobody reads."""
        s = _selection()
        edl = build_edl("Scene 12", [s], {})
        assert "MISSING MEDIA" in edl


class TestPlaylist:
    def test_every_join_is_marked_discontinuous(self) -> None:
        """Segments come from different encodes. Without the marker a player
        assumes one timeline and drifts out of sync within a few clips."""
        a, b = _selection(subgroup_id=1), _selection(subgroup_id=2)
        playlist = build_playlist([a, b], {**_media(a), **_media(b)})
        assert playlist.count("#EXT-X-DISCONTINUITY") == 2

    def test_the_stream_names_what_is_playing(self) -> None:
        """The overlay reads shot and take from the stream rather than tracking
        playback position separately, which drifts."""
        s = _selection(take_no=4)
        playlist = build_playlist([s], _media(s))
        assert "X-TAKE=4" in playlist
        assert 'ID="s12-3"' in playlist

    def test_quotes_in_a_reason_do_not_break_the_manifest(self) -> None:
        """A malformed tag takes the whole playlist with it, and reasons are
        written by editors who will eventually use a quotation mark."""
        s = _selection(reason='the "wider" frame')
        playlist = build_playlist([s], _media(s))
        daterange = next(ln for ln in playlist.splitlines() if "DATERANGE" in ln)
        assert daterange.count('"') % 2 == 0

    def test_a_span_widens_to_whole_segments(self) -> None:
        """Boundaries are fixed at encode time and a span rarely lands on one.
        Widening costs a fraction of a second nobody notices; narrowing would
        need a re-encode and defeat the point of not rendering."""
        s = _selection(start=5.0, end=9.0)  # crosses segments 1 and 2
        playlist = build_playlist([s], _media(s))
        segments = [ln for ln in playlist.splitlines() if ln.endswith(".ts")]
        assert "seg_0001.ts" in segments[0]
        assert len(segments) >= 2

    def test_a_selection_without_a_proxy_is_omitted_not_broken(self) -> None:
        """A reference to a segment that does not exist stalls the player. An
        omission is visible in the cut; a stall is a bug report."""
        s = _selection()
        playlist = build_playlist([s], {})
        assert "#EXT-X-ENDLIST" in playlist
        assert not [ln for ln in playlist.splitlines() if ln.endswith(".ts")]

    def test_the_playlist_is_closed(self) -> None:
        """Without ENDLIST a player treats it as live and waits forever for more
        segments at the end of the film."""
        s = _selection()
        assert build_playlist([s], _media(s)).rstrip().endswith("#EXT-X-ENDLIST")
