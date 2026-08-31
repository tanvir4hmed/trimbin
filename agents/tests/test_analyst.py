"""Tests for the Analyst's non-model logic.

Everything here runs without a model, and everything here is a place where a
quiet mistake becomes a confident wrong answer in the archive: how takes are
scored against their own group, when the panel is worth its cost, and whether a
finding is raised at all.
"""

from __future__ import annotations

from uuid import uuid4

from trimbin_agents.analyst.agent import (
    OUTLIER_RATIO,
    _rank_on_measurements,
    _score,
    _shortfall,
    _technical_report,
)
from trimbin_agents.config import settings
from trimbin_agents.contracts.analysis import AnalysisRequest, Measurements
from trimbin_agents.contracts.base import ClipRef, Severity


def _measurements(**overrides) -> Measurements:
    base = {
        "exposure_rel": 1.0,
        "clipping_pct": 0.0,
        "sharpness_rel": 1.0,
        "motion_rel": 1.0,
        "audio_lufs": -19.0,
        "noise_floor_db": -56.0,
        "duration_s": 30.0,
        "dropped_frames": 0,
    }
    return Measurements(**{**base, **overrides})


def _request(*takes: Measurements) -> AnalysisRequest:
    clips, measurements = [], {}
    for i, m in enumerate(takes, start=1):
        clip = ClipRef(clip_id=uuid4(), project_id=1, group_id=12, subgroup_id=3, take_no=i)
        clips.append(clip)
        measurements[clip.clip_id] = m
    return AnalysisRequest(clips=clips, measurements=measurements)


class TestScoring:
    def test_a_take_at_the_group_median_scores_full(self) -> None:
        """Everything is measured against the group, so sitting at the median
        means nothing is wrong with this take relative to its siblings."""
        assert _score(_measurements()) == 1.0

    def test_a_deliberately_dark_scene_is_not_penalised_wholesale(self) -> None:
        """The trap this design exists to avoid. Seven dark takes are a night
        scene, not seven mistakes â€” because the values are ratios against the
        group, all seven sit at 1.0 and none is marked down."""
        request = _request(*[_measurements() for _ in range(7)])
        scores = [_score(request.measurements[c.clip_id]) for c in request.clips]
        assert all(s == 1.0 for s in scores)

    def test_the_outlier_within_a_dark_scene_is_still_found(self) -> None:
        """The other half of the pair above. Seven dark takes are a night scene;
        one take darker than the other six is an accident, and the ratio finds
        it precisely because it is measured against them.

        This built a request and never looked at it — the assertion only scored
        one take in isolation, which is the case the previous test covers. It
        ranks the group now, which is what the name claims.
        """
        darker = _measurements(exposure_rel=0.4)
        request = _request(_measurements(), _measurements(), darker)

        scores = [_score(request.measurements[c.clip_id]) for c in request.clips]
        assert scores[-1] < 1.0
        assert scores[-1] == min(scores)
        assert all(s == 1.0 for s in scores[:-1])

    def test_dropped_frames_are_heavily_penalised(self) -> None:
        """Unlike darkness or shake, a dropped frame is never an artistic
        choice."""
        assert _score(_measurements(dropped_frames=10)) < 0.2

    def test_extra_stability_earns_nothing(self) -> None:
        """A locked-off take is not better than the group; it is simply not
        moving. Rewarding stillness would bias every handheld scene."""
        still = _measurements(motion_rel=0.2)
        assert _score(still) == 1.0


class TestRanking:
    def test_a_clear_leader_produces_a_wide_margin(self) -> None:
        request = _request(_measurements(), _measurements(exposure_rel=0.3, sharpness_rel=0.4))
        _, margin = _rank_on_measurements(request)
        assert margin >= settings.panel_margin

    def test_equivalent_takes_produce_a_narrow_margin(self) -> None:
        """This is what sends a shot to a person: when the numbers cannot
        separate the takes, the decision has become an emotional one."""
        request = _request(_measurements(), _measurements(exposure_rel=0.99))
        _, margin = _rank_on_measurements(request)
        assert margin < settings.panel_margin

    def test_a_single_take_needs_no_comparison(self) -> None:
        winner, margin = _rank_on_measurements(_request(_measurements()))
        assert margin == 1.0
        assert winner is not None


class TestTechnicalReport:
    def test_an_agreeing_group_raises_nothing(self) -> None:
        """Silence is the correct output when every take sits near the median.
        Reporting on all seven would bury the one finding that matters."""
        request = _request(*[_measurements() for _ in range(5)])
        reports = _technical_report(request)
        assert all(not r.findings for r in reports)
        assert all("within the group" in r.summary for r in reports)

    def test_an_outlier_is_described_not_condemned(self) -> None:
        """The wording is the product decision: a fact an editor interprets,
        never a verdict the system has no standing to make."""
        shaky = _measurements(motion_rel=OUTLIER_RATIO + 0.5)
        request = _request(_measurements(), shaky)
        findings = [f for r in _technical_report(request) for f in r.findings]

        stability = [f for f in findings if f.code == "stability.outlier"]
        assert len(stability) == 1
        assert "most camera movement in this group" in stability[0].detail
        assert "shaky" not in stability[0].detail.lower()
        assert "bad" not in stability[0].detail.lower()

    def test_shake_alone_never_blocks_a_take(self) -> None:
        """A shaky take may hold the performance the scene needs. Blocking is
        reserved for footage carrying no information at all."""
        request = _request(_measurements(), _measurements(motion_rel=4.0))
        findings = [f for r in _technical_report(request) for f in r.findings]
        assert all(f.severity is not Severity.BLOCKING for f in findings)

    def test_dropped_frames_do_block(self) -> None:
        request = _request(_measurements(dropped_frames=3))
        findings = [f for r in _technical_report(request) for f in r.findings]
        assert any(f.severity is Severity.BLOCKING for f in findings)


class TestShortfall:
    def test_names_the_worst_axis_in_the_group_s_terms(self) -> None:
        reason = _shortfall(_measurements(exposure_rel=0.3))
        assert "darker than the rest of the group" in reason

    def test_a_near_miss_says_so_rather_than_inventing_a_fault(self) -> None:
        assert "narrowly behind" in _shortfall(_measurements(exposure_rel=0.99))
