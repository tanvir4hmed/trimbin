"""Tests for the two things this product actually promises.

Promise one: which part of each take is safe to use. A take with a focus miss at
six seconds is sixty good seconds and two bad ones, and treating it as a bad
take is the failure mode that matters most — it throws away footage somebody
paid to shoot.

Promise two: a per-criterion breakdown, never one opaque score. An editor who
disagrees has to be able to see which axis produced the answer.
"""

from __future__ import annotations

from app.services import criteria, ranges


def finding(code: str, start: float = 0.0, end: float = 0.0, severity: str = "attention") -> dict:
    return {"code": code, "start_s": start, "end_s": end, "severity": severity, "detail": ""}


class TestSafeRanges:
    def test_a_clean_take_is_usable_end_to_end(self) -> None:
        found, trims = ranges.safe_ranges(70.0, [])
        assert len(found) == 1
        assert (found[0].start_s, found[0].end_s) == (0.0, 70.0)
        assert trims == []

    def test_a_fault_in_the_middle_leaves_two_usable_stretches(self) -> None:
        """The case the whole module exists for. Offering only the longer
        stretch would discard the other, and offering the whole take would
        include the fault."""
        found, trims = ranges.safe_ranges(70.0, [finding("focus.lost", 30.0, 34.0)])
        assert [(r.start_s, r.end_s) for r in found] == [(0.0, 30.0), (34.0, 70.0)]
        assert trims == ["focus.lost"]

    def test_a_slate_at_the_head_is_trimmed_off(self) -> None:
        found, _ = ranges.safe_ranges(70.0, [finding("slate.present", 0.0, 4.5)])
        assert [(r.start_s, r.end_s) for r in found] == [(4.5, 70.0)]

    def test_camera_shake_is_reported_but_never_cut(self) -> None:
        """A note, not a trim. Handheld movement is a choice as often as it is a
        mistake, and cutting it out would quietly delete the energy somebody
        shot on purpose."""
        found, trims = ranges.safe_ranges(70.0, [finding("stability.shake", 20.0, 26.0)])
        assert [(r.start_s, r.end_s) for r in found] == [(0.0, 70.0)]
        assert trims == []

    def test_overlapping_faults_do_not_invent_a_gap_between_them(self) -> None:
        """A freeze inside a black span. Punching two holes would leave a
        fragment between them that does not exist in the footage."""
        found, _ = ranges.safe_ranges(
            60.0,
            [finding("clip.black", 10.0, 20.0), finding("frames.frozen", 12.0, 18.0)],
        )
        assert [(r.start_s, r.end_s) for r in found] == [(0.0, 10.0), (20.0, 60.0)]

    def test_a_fault_covering_everything_leaves_nothing(self) -> None:
        """An empty list is a real answer: the take is unusable. It is not the
        same as the computation failing, which is why this returns a list."""
        found, trims = ranges.safe_ranges(30.0, [finding("clip.black", 0.0, 30.0)])
        assert found == []
        assert trims == ["clip.black"]

    def test_a_finding_with_no_span_applies_to_the_whole_take(self) -> None:
        """"Frozen throughout" carries no timecode. Skipping it because it has
        no span would silently keep the worst takes."""
        found, trims = ranges.safe_ranges(30.0, [finding("frames.frozen")])
        assert found == []
        assert trims == ["frames.frozen"]

    def test_a_flicker_too_short_to_cut_around_is_left_alone(self) -> None:
        """Removing a fifth of a second leaves two fragments nobody can use and
        a range list harder to read than the problem it describes."""
        found, _ = ranges.safe_ranges(60.0, [finding("frames.frozen", 30.0, 30.2)])
        assert [(r.start_s, r.end_s) for r in found] == [(0.0, 60.0)]

    def test_a_sliver_of_clean_footage_is_not_offered_as_usable(self) -> None:
        found, _ = ranges.safe_ranges(
            60.0, [finding("clip.black", 0.5, 60.0)]
        )
        assert found == []

    def test_the_longest_stretch_is_what_an_assembly_takes(self) -> None:
        found, _ = ranges.safe_ranges(70.0, [finding("focus.lost", 10.0, 14.0)])
        best = ranges.longest(found)
        assert best is not None
        assert (best.start_s, best.end_s) == (14.0, 70.0)

    def test_nothing_usable_means_no_assembly_span(self) -> None:
        assert ranges.longest([]) is None

    def test_a_model_observation_can_be_excluded(self) -> None:
        """A boom in shot is the panel's claim, not a measurement. Callers who
        only want to trim on measured evidence can say so."""
        observed = [finding("frame.boom_visible", 40.0, 45.0)]

        trusting, _ = ranges.safe_ranges(60.0, observed, include_observed=True)
        measured_only, _ = ranges.safe_ranges(60.0, observed, include_observed=False)

        assert len(trusting) == 2
        assert [(r.start_s, r.end_s) for r in measured_only] == [(0.0, 60.0)]


class TestCriteria:
    @staticmethod
    def _typical(**overrides) -> dict:
        base = {
            "exposure_rel": 1.0, "sharpness_rel": 1.0, "motion_rel": 1.0,
            "clipping_pct": 0.0, "audio_lufs": -23.0, "noise_floor_db": -60.0,
            "dropped_frames": 0,
        }
        return {**base, **overrides}

    def test_a_take_at_the_group_median_scores_full_marks(self) -> None:
        s = criteria.score_take(self._typical(), [])
        assert s.values["focus"] == 1.0
        assert s.values["exposure"] == 1.0
        assert s.values["stability"] == 1.0

    def test_every_axis_is_reported_not_just_a_total(self) -> None:
        s = criteria.score_take(self._typical(), [])
        assert set(s.names) == set(criteria.AXES)
        assert len(s.scores) == len(criteria.AXES)

    def test_a_softer_take_than_its_siblings_loses_focus_score(self) -> None:
        s = criteria.score_take(self._typical(sharpness_rel=0.7), [])
        assert s.values["focus"] < 1.0

    def test_a_sharper_take_is_not_rewarded_beyond_parity(self) -> None:
        """1.4x the group's focus is not 40% more usable. Crediting it would let
        one unusually sharp take make its siblings look faulty."""
        s = criteria.score_take(self._typical(sharpness_rel=1.4), [])
        assert s.values["focus"] == 1.0

    def test_a_steadier_take_among_handheld_ones_is_not_penalised(self) -> None:
        """Only excess movement costs. Punishing the steadiest take in a
        handheld setup would be exactly backwards."""
        s = criteria.score_take(self._typical(motion_rel=0.4), [])
        assert s.values["stability"] == 1.0

    def test_a_shakier_take_than_its_siblings_loses_stability(self) -> None:
        s = criteria.score_take(self._typical(motion_rel=1.5), [])
        assert s.values["stability"] < 1.0

    def test_exposure_is_penalised_in_both_directions(self) -> None:
        dark = criteria.score_take(self._typical(exposure_rel=0.7), [])
        bright = criteria.score_take(self._typical(exposure_rel=1.3), [])
        assert dark.values["exposure"] < 1.0
        assert bright.values["exposure"] < 1.0

    def test_clipping_cannot_be_averaged_away_by_good_exposure(self) -> None:
        """A take correctly exposed on average and blowing its highlights is not
        a correctly exposed take. Subtracting would let the two cancel."""
        s = criteria.score_take(self._typical(exposure_rel=1.0, clipping_pct=20.0), [])
        assert s.values["exposure"] < 0.7

    def test_unmeasured_audio_says_so_rather_than_guessing(self) -> None:
        """Zero would penalise a take for a measurement we did not take. Full
        marks would claim it is clean."""
        s = criteria.score_take(self._typical(audio_lufs=0.0), [])
        assert s.values["audio"] == 0.5

    def test_quiet_production_sound_is_not_a_fault(self) -> None:
        """The regression this replaced. Production sound is recorded with
        headroom and normalised later, so scoring it against R 128's -23 LUFS
        delivery target marked down every honestly recorded take on the shoot.
        All twelve dataset takes sit between -33 and -43 LUFS."""
        s = criteria.score_take(self._typical(audio_lufs=-38.0, noise_floor_db=-70.0), [])
        assert s.values["audio"] == 1.0

    def test_a_microphone_that_barely_recorded_is_a_fault(self) -> None:
        """Quiet is a choice; this far down is a mic that was not on the actor."""
        s = criteria.score_take(self._typical(audio_lufs=-55.0, noise_floor_db=-90.0), [])
        assert s.values["audio"] < 0.5

    def test_hiss_under_the_dialogue_costs_audio_score(self) -> None:
        """What normalising cannot fix. The floor is judged against the
        programme level, not on its own: -60 dB under -23 LUFS is clean, and the
        same floor under -43 is audible the moment anyone lifts the take."""
        clean = criteria.score_take(self._typical(audio_lufs=-38.0, noise_floor_db=-75.0), [])
        noisy = criteria.score_take(self._typical(audio_lufs=-38.0, noise_floor_db=-53.0), [])
        assert clean.values["audio"] > noisy.values["audio"]

    def test_the_same_floor_is_judged_differently_at_different_levels(self) -> None:
        loud = criteria.score_take(self._typical(audio_lufs=-23.0, noise_floor_db=-60.0), [])
        quiet = criteria.score_take(self._typical(audio_lufs=-45.0, noise_floor_db=-60.0), [])
        assert loud.values["audio"] > quiet.values["audio"]

    def test_audio_is_absolute_not_group_relative(self) -> None:
        """The part of the old design that was right. A group-relative audio
        score would call the least-bad take in a badly recorded setup correct."""
        bad = criteria.score_take(self._typical(audio_lufs=-38.0, noise_floor_db=-48.0), [])
        assert bad.values["audio"] < 1.0

    def test_incomplete_dialogue_costs_completion_not_focus(self) -> None:
        """The axes have to stay separable, or the breakdown says nothing the
        single score did not."""
        s = criteria.score_take(self._typical(), [finding("dialogue.incomplete")])
        assert s.values["completion"] < 0.5
        assert s.values["focus"] == 1.0

    def test_a_continuity_note_costs_less_than_a_blocking_one(self) -> None:
        note = criteria.score_take(
            self._typical(), [finding("continuity.prop", severity="note")]
        )
        attention = criteria.score_take(
            self._typical(), [finding("continuity.prop", severity="attention")]
        )
        assert note.values["continuity"] > attention.values["continuity"]

    def test_several_minor_notes_do_not_outweigh_one_real_fault(self) -> None:
        """Costs multiply rather than sum. Summing lets three small notes score
        a take below one that genuinely cannot be used."""
        minor = criteria.score_take(
            self._typical(),
            [
                finding("continuity.lighting", severity="note"),
                finding("continuity.blocking", severity="note"),
                finding("frame.shadow", severity="note"),
            ],
        )
        major = criteria.score_take(self._typical(), [finding("frame.crew_visible")])
        assert minor.values["continuity"] > major.values["continuity"]

    def test_dropped_frames_damage_the_image_axes(self) -> None:
        s = criteria.score_take(self._typical(dropped_frames=8), [])
        assert s.values["focus"] < 1.0
        assert s.values["stability"] < 1.0

    def test_no_score_escapes_zero_to_one(self) -> None:
        extreme = criteria.score_take(
            self._typical(
                exposure_rel=5.0, sharpness_rel=0.01, motion_rel=9.0,
                clipping_pct=99.0, dropped_frames=500, noise_floor_db=0.0,
            ),
            [finding("dialogue.incomplete"), finding("continuity.screen_direction")],
        )
        assert all(0.0 <= v <= 1.0 for v in extreme.values.values())

    def test_the_measured_axes_are_separable_from_the_observed_ones(self) -> None:
        """An editor should be able to see which numbers a machine measured and
        which a model claimed."""
        s = criteria.score_take(self._typical(), [])
        assert set(s.measured_only) == criteria.MEASURED
        assert not (set(s.measured_only) & criteria.OBSERVED)


class TestCodesReachStorageAsTheirValues:
    """The bug that made every score perfect.

    From Python 3.11 a `str, Enum` member stringifies to its class name, so
    codes reached ClickHouse as "FindingCode.CONTINUITY_BLOCKING". Nothing
    matched: not a query against the taxonomy, and not the cost tables here —
    so every take scored 1.0 on continuity and completion while carrying
    findings that said otherwise.
    """

    def test_an_enum_member_stores_as_its_taxonomy_string(self) -> None:
        from trimbin_agents.contracts.base import FindingCode

        from app.services.decisions import _code_value

        assert _code_value(FindingCode.CONTINUITY_BLOCKING) == "continuity.blocking"
        assert "FindingCode" not in _code_value(FindingCode.CONTINUITY_BLOCKING)

    def test_a_plain_string_passes_through(self) -> None:
        """A human override arrives as JSON with no enum to unwrap."""
        from app.services.decisions import _code_value

        assert _code_value("continuity.prop") == "continuity.prop"

    def test_scoring_matches_what_gets_stored(self) -> None:
        """The two have to agree or the breakdown is decorative."""
        from trimbin_agents.contracts.base import FindingCode

        from app.services.decisions import _code_value

        stored = _code_value(FindingCode.DIALOGUE_INCOMPLETE)
        assert stored in criteria.COMPLETION_COSTS

        scored = criteria.score_take(
            TestCriteria._typical(), [{"code": stored, "severity": "attention"}]
        )
        assert scored.values["completion"] < 1.0
