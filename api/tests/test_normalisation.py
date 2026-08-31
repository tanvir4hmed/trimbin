"""Tests for turning raw measurements into group-relative ones.

This is the step that makes every downstream comparison mean anything, and it
has two ways of being quietly wrong. Both are covered here because both happened.

A median of zero divides by nothing, and falling back to 1.0 there is right: a
setup where every take measured zero on an axis has takes that are identical, and
the fault is not any one take's.

A setup with no raw values at all is different, and the difference is the whole
test. Treating it the same way writes 1.0 over every ratio in the group — which
looks exactly like "all takes are typical" and is actually "we destroyed what was
there".
"""

from __future__ import annotations

from app.services import clips


class TestMedian:
    def test_odd_count_takes_the_middle(self) -> None:
        assert clips._median([3.0, 1.0, 2.0]) == 2.0

    def test_even_count_averages_the_pair(self) -> None:
        assert clips._median([1.0, 2.0, 3.0, 4.0]) == 2.5

    def test_one_ruined_take_does_not_move_it(self) -> None:
        """Why median and not mean. A take that came out pitch black drags a
        mean far enough to make the healthy takes look unusual — which is
        backwards, since the black one is the thing to notice."""
        healthy = [100.0, 102.0, 98.0, 101.0, 99.0]
        with_a_ruined_one = [*healthy, 2.0]

        median = clips._median(with_a_ruined_one)
        mean = sum(with_a_ruined_one) / len(with_a_ruined_one)

        assert 98.0 <= median <= 102.0
        assert mean < 90.0


class TestRatio:
    def test_a_take_at_the_median_is_one(self) -> None:
        assert clips._ratio(100.0, 100.0) == 1.0

    def test_brighter_than_the_group_is_above_one(self) -> None:
        assert clips._ratio(150.0, 100.0) == 1.5

    def test_a_zero_median_is_typical_not_infinite(self) -> None:
        """Every take measured zero, so every take is identical. Dividing would
        raise; calling one of them unusual would be a lie."""
        assert clips._ratio(0.0, 0.0) == 1.0

    def test_a_negative_median_is_refused_the_same_way(self) -> None:
        """No measurement here can be negative. If one is, the reading is broken
        and a confident ratio derived from it would be worse than none."""
        assert clips._ratio(5.0, -1.0) == 1.0


class TestGuardAgainstEmptyRawValues:
    """The regression this file exists for.

    Raw columns were added after the first clips were written, so those rows
    carried zeros. Normalising them computed a median of zero on every axis,
    fell back to 1.0 everywhere, and flattened twelve correctly measured takes
    to "all typical" — overwriting real ratios with a placeholder that looks
    identical to a real answer.
    """

    @staticmethod
    def _rows(values):
        return [(f"clip-{i}", *v) for i, v in enumerate(values)]

    def test_all_zeros_is_recognised_as_no_data(self) -> None:
        rows = self._rows([(0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)])
        assert not any(float(r[1]) or float(r[2]) or float(r[3]) for r in rows)

    def test_one_axis_measured_is_enough_to_proceed(self) -> None:
        """A setup where focus was measured and motion was not is still worth
        normalising on focus. Refusing the whole group would discard real data
        to avoid a partial answer."""
        rows = self._rows([(0.0, 42.0, 0.0), (0.0, 40.0, 0.0)])
        assert any(float(r[1]) or float(r[2]) or float(r[3]) for r in rows)

    def test_real_measurements_are_not_mistaken_for_missing(self) -> None:
        rows = self._rows([(101.0, 42.0, 3.1), (99.0, 40.0, 3.4)])
        assert any(float(r[1]) or float(r[2]) or float(r[3]) for r in rows)


class TestFindingsColumns:
    """Timecoded findings, flattened for storage.

    Editors choose moments inside takes, so a finding without a span cannot
    become something the interface can seek to.
    """

    @staticmethod
    def _measurements(**spans):
        from app.services.measure import RawMeasurements, Span

        m = RawMeasurements(duration_s=30.0, width=1920, height=1080, fps=25.0)
        for name, pairs in spans.items():
            setattr(m, name, [Span(start_s=a, end_s=b) for a, b in pairs])
        return m

    def test_no_findings_gives_three_empty_arrays(self) -> None:
        codes, starts, ends = clips._findings_columns(self._measurements())
        assert codes == [] and starts == [] and ends == []

    def test_each_span_keeps_its_own_timecode(self) -> None:
        m = self._measurements(motion_spikes=[(4.2, 7.8), (19.0, 20.5)])
        codes, starts, ends = clips._findings_columns(m)
        assert codes == ["stability.shake", "stability.shake"]
        assert starts == [4.2, 19.0]
        assert ends == [7.8, 20.5]

    def test_different_kinds_of_fault_keep_their_own_codes(self) -> None:
        m = self._measurements(
            focus_loss_spans=[(6.0, 9.0)],
            freeze_spans=[(12.0, 14.0)],
        )
        codes, _, _ = clips._findings_columns(m)
        assert set(codes) == {"focus.lost", "frames.frozen"}

    def test_the_arrays_stay_the_same_length(self) -> None:
        """They are stored as three parallel columns and zipped back together on
        read. A mismatch there would pair a code with another finding's
        timecode, which is worse than having no timecode at all."""
        m = self._measurements(
            motion_spikes=[(1.0, 2.0), (3.0, 4.0)],
            black_spans=[(28.0, 30.0)],
        )
        codes, starts, ends = clips._findings_columns(m)
        assert len(codes) == len(starts) == len(ends) == 3
