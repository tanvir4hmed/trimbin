"""Tests for getting the work out of here.

An export is the one artefact nobody checks by eye. An EDL is opened by a
conform, a marker file is imported at two in the morning, and a mistake in
either surfaces as footage on the wrong frame rather than as an error. So the
arithmetic is tested rather than the format: where a frame lands, where a marker
lands, and what happens at the boundaries where both are easy to get wrong.
"""

from __future__ import annotations

from app.services import exports


class TestTimecode:
    def test_zero_is_the_start_of_the_reel(self) -> None:
        assert exports.timecode(0.0) == "00:00:00:00"

    def test_a_whole_second_has_no_frames(self) -> None:
        assert exports.timecode(1.0, fps=24) == "00:00:01:00"

    def test_half_a_second_at_24_is_twelve_frames(self) -> None:
        assert exports.timecode(1.5, fps=24) == "00:00:01:12"

    def test_the_frame_never_reaches_the_frame_rate(self) -> None:
        """23 is the last frame of a second at 24fps. A timecode reading
        00:00:00:24 is not a timecode; some readers refuse the file and others
        quietly take it as a second and a frame."""
        for hundredths in range(0, 400):
            frames = int(exports.timecode(hundredths / 100, fps=24).split(":")[-1])
            assert frames < 24

    def test_an_hour_rolls_over(self) -> None:
        assert exports.timecode(3661.0, fps=24) == "01:01:01:00"

    def test_a_negative_time_is_the_start_rather_than_a_crash(self) -> None:
        """Nothing should produce one. If something does, an export that clamps
        is recoverable and an export that throws loses the whole scene."""
        assert exports.timecode(-5.0) == "00:00:00:00"

    def test_it_follows_the_frame_rate_it_is_given(self) -> None:
        """The value that is declared, not measured. Nothing in the archive
        records what the original was shot at, and an EDL cut at 24 for 25fps
        footage drifts a frame a second."""
        assert exports.timecode(1.0, fps=25) == "00:00:01:00"
        assert exports.timecode(0.96, fps=25) == "00:00:00:24"


def _entry(**overrides) -> dict:
    base = {
        "clip_id": "11111111-1111-1111-1111-111111111111",
        "slug": "12A",
        "take_no": 3,
        "start_s": 2.0,
        "end_s": 12.0,
        "reason": "cleanest complete take",
    }
    base.update(overrides)
    return base


class TestEdl:
    def test_the_header_names_the_frame_rate_it_assumed(self) -> None:
        """An assistant relinking this needs to know, and the file is where they
        will be looking. A frame rate declared only in a README is a frame rate
        nobody reads."""
        text = exports.edl("SCENE 12", [_entry()], fps=25)
        assert "25 FPS" in text
        assert "DECLARED, NOT MEASURED" in text

    def test_record_time_starts_at_zero_and_accumulates(self) -> None:
        """Two ten-second shots put the second one at ten seconds, not at its own
        source timecode. Getting this wrong stacks every shot on top of the
        first."""
        text = exports.edl("S", [_entry(), _entry(start_s=0.0, end_s=5.0)], fps=24)
        events = [ln for ln in text.splitlines() if ln.startswith("00")]
        assert events[0].endswith("00:00:00:00 00:00:10:00")
        assert events[1].endswith("00:00:10:00 00:00:15:00")

    def test_the_reason_travels_with_the_decision(self) -> None:
        """The whole argument of this system is that a decision carries its
        reason. It should not stop being true at the export boundary."""
        text = exports.edl("S", [_entry(reason="the pause lands")], fps=24)
        assert "the pause lands" in text

    def test_a_disagreement_with_the_circle_is_carried_out_too(self) -> None:
        text = exports.edl(
            "S", [_entry(differs_from_circle=True, circled_take=5)], fps=24
        )
        assert "CIRCLED TAKE 5" in text

    def test_a_zero_length_shot_is_skipped_rather_than_emitted(self) -> None:
        """An event of no duration is a conform error in some applications and a
        silently dropped shot in others."""
        text = exports.edl("S", [_entry(start_s=4.0, end_s=4.0)], fps=24)
        assert not [ln for ln in text.splitlines() if ln.startswith("00")]

    def test_the_reel_is_readable_across_a_room(self) -> None:
        """Eight characters is all CMX3600 has. Sliced hexadecimal fits and
        helps nobody."""
        text = exports.edl("S", [_entry(slug="12A", take_no=3)], fps=24)
        assert "S12AT03" in text

    def test_it_is_ascii_even_when_the_reason_is_not(self) -> None:
        """Some readers still mean the A in ASCII literally, and a curly quote in
        a reason is not worth an import failure."""
        text = exports.edl("S", [_entry(reason="she doesn’t land it — take 4")], fps=24)
        text.encode("ascii")
        assert "doesn't land it - take 4" in text


class TestMarkers:
    ENTRIES = [
        _entry(clip_id="aaa", start_s=2.0, end_s=12.0),
        _entry(clip_id="bbb", start_s=0.0, end_s=5.0),
    ]

    def test_a_finding_lands_in_record_time_not_source_time(self) -> None:
        """A fault 4.2 seconds into a take that starts at 2.0 and sits at 0:00 on
        the timeline belongs at 2.2 seconds, not at 4.2. This is the arithmetic
        the whole file exists for."""
        csv_text = exports.markers(
            self.ENTRIES,
            [{"clip_id": "aaa", "start_s": 4.2, "end_s": 4.2, "code": "stability.shake"}],
            [],
            fps=24,
        )
        assert "00:00:02:05" in csv_text

    def test_a_marker_on_the_second_shot_is_offset_by_the_first(self) -> None:
        csv_text = exports.markers(
            self.ENTRIES,
            [{"clip_id": "bbb", "start_s": 1.0, "end_s": 1.0, "code": "focus.lost"}],
            [],
            fps=24,
        )
        assert "00:00:11:00" in csv_text

    def test_a_finding_on_a_take_that_is_not_in_the_cut_is_left_out(self) -> None:
        """It is real and it stays in the archive. Putting it on a timeline that
        does not contain that take would place it on whatever happens to be
        there instead, which is worse than omitting it."""
        csv_text = exports.markers(
            self.ENTRIES,
            [{"clip_id": "zzz", "start_s": 1.0, "end_s": 2.0, "code": "focus.lost"}],
            [],
            fps=24,
        )
        assert "focus.lost" not in csv_text

    def test_a_finding_past_the_trim_is_pinned_to_the_last_used_frame(self) -> None:
        """A fault at 0:52 of a take trimmed at 0:12 did happen. The honest place
        for it on this timeline is the last frame that survived."""
        csv_text = exports.markers(
            self.ENTRIES,
            [{"clip_id": "aaa", "start_s": 52.0, "end_s": 53.0, "code": "focus.lost"}],
            [],
            fps=24,
        )
        assert "00:00:10:00" in csv_text

    def test_severity_becomes_a_colour_an_editor_already_knows(self) -> None:
        csv_text = exports.markers(
            self.ENTRIES,
            [{
                "clip_id": "aaa", "start_s": 3.0, "end_s": 4.0,
                "code": "frames.dropped", "severity": "blocking",
            }],
            [],
            fps=24,
        )
        assert "Red" in csv_text

    def test_a_comment_arrives_as_a_marker_too(self) -> None:
        """Frame.io's most-used feature is exactly this. Notes that cannot reach
        the timeline become a second place to look, and a second place to look is
        a place people stop looking."""
        csv_text = exports.markers(
            self.ENTRIES,
            [],
            [{"clip_id": "aaa", "at_s": 3.0, "to_s": 4.0,
              "author": "maya@example.com", "body": "the pause lands"}],
            fps=24,
        )
        assert "the pause lands" in csv_text
        assert "Green" in csv_text

    def test_the_header_is_the_one_resolve_expects(self) -> None:
        first = exports.markers([], [], [], fps=24).splitlines()[0]
        assert first.startswith("Marker Name,Description,In,Out,Duration")

    def test_a_marker_is_never_zero_frames_long(self) -> None:
        """A zero-duration marker is invisible in some applications and refused
        by others. One frame is the shortest thing that means anything."""
        csv_text = exports.markers(
            self.ENTRIES,
            [{"clip_id": "aaa", "start_s": 3.0, "end_s": 3.0, "code": "x"}],
            [],
            fps=24,
        )
        duration = csv_text.splitlines()[1].split(",")[4]
        assert duration == "00:00:00:01"
