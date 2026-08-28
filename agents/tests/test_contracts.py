"""The contracts are the guarantee that agents cannot misunderstand each other.

These tests assert the guarantees themselves, not the happy path: that a winner
must have been judged, that unknown fields are rejected rather than ignored, and
that declining to pick is expressible. If any of these regress, the type system
stops protecting the boundary it exists to protect.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from trimbin_agents.contracts import (
    AnalysisResult,
    ClipRef,
    Confidence,
    Finding,
    FindingCode,
    Provenance,
    ReasonCode,
    Severity,
    TakeVerdict,
    TimeRange,
)


def _provenance() -> Provenance:
    return Provenance(
        model_id="gemini-3.6-flash",
        prompt_version="analyst/v1",
        produced_at=datetime.now(UTC),
        run_hash="deadbeef",
    )


def _verdict(clip_id, score: float = 0.9) -> TakeVerdict:
    return TakeVerdict(
        clip_id=clip_id,
        score=score,
        reason="cleanest complete take",
        reason_code=ReasonCode.CLEAN,
        findings=[],
    )


class TestWinnerIntegrity:
    def test_winner_must_have_been_judged(self) -> None:
        """A winner that was never a candidate means the pipeline lost track of
        which clips it compared — silently trusting that would corrupt the
        archive with a decision about footage nobody looked at."""
        judged = uuid4()
        never_seen = uuid4()

        with pytest.raises(ValidationError, match="clip that was judged"):
            AnalysisResult(
                subgroup_id=3,
                verdicts=[_verdict(judged)],
                winner_id=never_seen,
                margin=0.4,
                rationale="…",
                specialist_reports=[],
                confidence=Confidence.CONFIDENT,
                provenance=_provenance(),
            )

    def test_declining_to_pick_is_valid(self) -> None:
        """When no take is good enough, saying so must be expressible. Forcing a
        winner out of a bad group is the failure mode this guards against."""
        result = AnalysisResult(
            subgroup_id=3,
            verdicts=[_verdict(uuid4(), score=0.2)],
            winner_id=None,
            margin=0.0,
            rationale="No take completed the action.",
            specialist_reports=[],
            confidence=Confidence.UNCERTAIN,
            provenance=_provenance(),
        )
        assert result.winner_id is None


class TestStrictness:
    def test_unknown_fields_are_rejected(self) -> None:
        """Silently dropping an unexpected field is how two agents come to
        disagree about what a message meant."""
        with pytest.raises(ValidationError):
            ClipRef(
                clip_id=uuid4(),
                project_id=1,
                group_id=12,
                subgroup_id=3,
                take_no=4,
                scene_name="INT. APARTMENT",  # type: ignore[call-arg]
            )

    def test_scores_stay_in_range(self) -> None:
        with pytest.raises(ValidationError):
            _verdict(uuid4(), score=1.4)

    def test_reason_is_a_sentence_not_an_essay(self) -> None:
        """Reasons are read by a person scanning a queue. The cap is a product
        decision enforced by the schema."""
        with pytest.raises(ValidationError):
            TakeVerdict(
                clip_id=uuid4(),
                score=0.5,
                reason="x" * 201,
                reason_code=ReasonCode.CLEAN,
                findings=[],
            )


class TestFindings:
    def test_findings_can_be_anchored_in_time(self) -> None:
        """Editors choose moments inside takes. A finding without a timecode
        cannot become a link, and a finding that cannot be jumped to is a dead
        end for the person reading it."""
        finding = Finding(
            code="stability.outlier",
            detail="2.3x the camera movement of the group median",
            severity=Severity.ATTENTION,
            where=TimeRange(start_s=4.2, end_s=7.8),
        )
        assert finding.where is not None
        assert finding.where.duration_s() == pytest.approx(3.6)

    def test_findings_may_apply_to_a_whole_clip(self) -> None:
        finding = Finding(
            code="exposure.under",
            detail="1.8 stops below the group median throughout",
            severity=Severity.NOTE,
        )
        assert finding.where is None


class TestClosedVocabularies:
    """The regression that made the archive unqueryable.

    Findings and reason codes were free text. Across twelve real takes the panel
    produced thirty-nine distinct finding codes and four spellings of "this take
    is clean", with no two setups agreeing. Two things broke at once: per-axis
    scoring recognised none of them and silently reported perfect continuity
    everywhere, and "show me every take with a continuity problem" — the thing
    a queryable archive is for — had no answer.
    """

    def test_a_finding_code_outside_the_taxonomy_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            Finding(
                code="hair.style_mismatch",  # what the model actually wrote
                detail="Hair differs from the other takes",
                severity=Severity.ATTENTION,
            )

    def test_the_taxonomy_covers_what_the_panel_reached_for(self) -> None:
        """Each of these is a code the model invented because nothing named the
        thing it saw. A closed list that cannot express a real observation just
        moves the problem into `other`."""
        for wanted in (
            FindingCode.CONTINUITY_HAIR,
            FindingCode.CONTINUITY_SET_DRESSING,
            FindingCode.FRAME_OBSTRUCTION,
            FindingCode.CAMERA_UNMOTIVATED_MOVE,
            FindingCode.DIALOGUE_INCOMPLETE,
        ):
            assert Finding(code=wanted, detail="x", severity=Severity.NOTE).code is wanted

    def test_an_unnameable_observation_has_somewhere_to_go(self) -> None:
        """Better than forcing a wrong code onto a true observation. A rising
        count of these is a signal the list needs an entry, not noise."""
        f = Finding(code=FindingCode.OTHER, detail="Something none of these name",
                    severity=Severity.NOTE)
        assert f.code is FindingCode.OTHER

    def test_a_shake_and_an_outlier_stay_different_things(self) -> None:
        """A lurch at 4.2s can be cut around. A take that moves more than its
        siblings throughout cannot. Collapsing them would lose that."""
        assert FindingCode.STABILITY_SHAKE is not FindingCode.STABILITY_OUTLIER

    def test_an_invented_reason_code_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            TakeVerdict(
                clip_id=uuid4(),
                score=0.9,
                reason="Complete dialogue delivery and technically clean",
                reason_code="complete_and_clean",  # one of four spellings it used
                findings=[],
            )

    def test_performance_is_observable_but_carries_no_weight(self) -> None:
        """Emotion and story are the 74% of Murch's order that belongs to a
        person. One code rather than a family of them makes it hard to forget
        that none of them may move a ranking."""
        assert FindingCode.PERFORMANCE_NOTE.value == "performance.note"
        assert not [
            c for c in FindingCode
            if c.value.startswith("performance.") and c is not FindingCode.PERFORMANCE_NOTE
        ]
