"""Tests for an editor choosing a take.

This is the only route in the system that produces the data nothing else can:
a human editorial judgement with the reason a person gave for it. Everything
about the accuracy figure rests on these rows, so the ways they can be written
wrong matter more than the happy path.

No fixture here writes to the real archive. A human decision invented by a test
would be indistinguishable from one an editor made, and it would move the number
this system publishes about itself.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.routes.review import Override, rows_for_choice


class TestTheReasonIsRequired:
    """The reason is the point.

    An override without one is the exact moment the archive exists to capture,
    arriving empty. Making it optional would mean collecting the disagreement
    and losing the only part of it a model cannot reconstruct.
    """

    def test_a_reason_is_mandatory(self) -> None:
        with pytest.raises(ValidationError):
            Override(clip_id=uuid4())

    def test_whitespace_is_not_a_reason(self) -> None:
        with pytest.raises(ValidationError):
            Override(clip_id=uuid4(), reason="     ")

    def test_a_reason_is_normalised_not_stored_ragged(self) -> None:
        """Two editors typing the same thing with different spacing should
        produce one group in the archive, not two."""
        o = Override(clip_id=uuid4(), reason="  better   performance \n")
        assert o.reason == "better performance"

    def test_a_short_but_real_reason_is_accepted(self) -> None:
        """The bar is "said something", not "wrote an essay". Set it higher and
        people stop overriding rather than start explaining."""
        assert Override(clip_id=uuid4(), reason="pace").reason == "pace"

    def test_an_essay_is_refused_rather_than_silently_truncated(self) -> None:
        """Truncation would store half a sentence as if it were the whole
        thought, which is worse than asking the person to shorten it."""
        with pytest.raises(ValidationError):
            Override(clip_id=uuid4(), reason="x" * 500)


class TestNarrowingTheRange:
    """An editor may accept the panel's take and still want less of it."""

    def test_no_points_means_the_offered_range_stands(self) -> None:
        o = Override(clip_id=uuid4(), reason="fine")
        assert o.in_point_s is None
        assert o.out_point_s is None

    def test_points_are_kept_when_given(self) -> None:
        o = Override(clip_id=uuid4(), reason="trim the head", in_point_s=4.8, out_point_s=17.5)
        assert (o.in_point_s, o.out_point_s) == (4.8, 17.5)

    def test_a_negative_point_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            Override(clip_id=uuid4(), reason="x", in_point_s=-1.0)


class TestTheClipMustBeReal:
    def test_something_that_is_not_a_uuid_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            Override(clip_id="take 4", reason="better performance")


class TestWhatGetsWritten:
    """The shape of the rows an override produces.

    Exercised through the same helper the route uses, so a change to one is a
    change to both.
    """

    @staticmethod
    def _verdicts():
        chosen, other = str(uuid4()), str(uuid4())
        return chosen, other, [
            {
                "clip_id": chosen, "outcome": "not_selected", "score": 0.72,
                "findings": [{"code": "continuity.prop", "start_s": 12.0, "end_s": 14.0}],
                "criterion_names": ["focus", "continuity"], "criterion_scores": [1.0, 0.5],
                "safe_starts_s": [0.0], "safe_ends_s": [30.0], "trim_reasons": [],
                "in_point_s": 0.0, "out_point_s": 30.0,
            },
            {
                "clip_id": other, "outcome": "selected", "score": 0.91,
                "findings": [], "criterion_names": ["focus", "continuity"],
                "criterion_scores": [1.0, 1.0],
                "safe_starts_s": [0.0], "safe_ends_s": [28.0], "trim_reasons": [],
                "in_point_s": 0.0, "out_point_s": 28.0,
            },
        ]

    def test_the_panels_score_is_carried_forward_unchanged(self) -> None:
        """A person disagreeing with the conclusion does not change what was
        measured. Rewriting the score to justify the choice would destroy the
        evidence the disagreement is worth having."""
        chosen, _, verdicts = self._verdicts()
        rows = rows_for_choice(
            verdicts, chosen, Override(clip_id=chosen, reason="better performance")
        )

        by_id = {r["clip_id"]: r for r in rows}
        assert by_id[chosen]["score"] == 0.72

    def test_exactly_one_take_is_selected(self) -> None:
        chosen, other, verdicts = self._verdicts()
        rows = rows_for_choice(
            verdicts, chosen, Override(clip_id=chosen, reason="better performance")
        )

        selected = [r for r in rows if r["outcome"] == "selected"]
        assert len(selected) == 1
        assert selected[0]["clip_id"] == chosen

    def test_the_findings_survive_the_override(self) -> None:
        """The take still has a prop continuity problem. The editor decided to
        live with it, which is a different thing from it not being there."""
        chosen, _, verdicts = self._verdicts()
        rows = rows_for_choice(
            verdicts, chosen, Override(clip_id=chosen, reason="better performance")
        )

        by_id = {r["clip_id"]: r for r in rows}
        assert by_id[chosen]["findings"][0]["code"] == "continuity.prop"

    def test_the_editors_words_land_on_the_take_they_chose(self) -> None:
        chosen, other, verdicts = self._verdicts()
        rows = rows_for_choice(
            verdicts, chosen,
            Override(clip_id=chosen, reason="the pause before the line lands"),
        )

        by_id = {r["clip_id"]: r for r in rows}
        assert by_id[chosen]["reason"] == "the pause before the line lands"
        assert by_id[other]["reason"] != "the pause before the line lands"


class TestSeveritySurvivesTheWrite:
    """How bad a finding is, kept rather than reconstructed.

    The panel has always produced a severity and the writer dropped it. That was
    survivable while findings were only read back into one screen, which colours
    them all alike, and stopped being survivable the moment they became timeline
    markers: the exporter had to say which of a hundred notes to stop for, had
    nothing to go on, and guessed from the code's name.

    The guess was `code.endswith(".blocking")`. `continuity.blocking` is a note
    about where an actor stands, so every one of them arrived in Resolve as a
    red marker meaning the take could not be used.
    """

    def test_the_panels_severity_is_kept(self) -> None:
        from trimbin_agents.contracts.base import (
            Finding,
            FindingCode,
            Severity,
            TimeRange,
        )

        from app.services.decisions import _findings

        _, _, _, severities = _findings([
            Finding(
                code=FindingCode.CONTINUITY_BLOCKING,
                detail="she crosses left instead of right",
                severity=Severity.NOTE,
                where=TimeRange(start_s=2.0, end_s=4.0),
            )
        ])
        # A note, because that is what the panel said — not "blocking", which is
        # what the code happens to be called.
        assert severities == ["note"]

    def test_a_blocking_severity_is_kept_too(self) -> None:
        from trimbin_agents.contracts.base import (
            Finding,
            FindingCode,
            Severity,
            TimeRange,
        )

        from app.services.decisions import _findings

        _, _, _, severities = _findings([
            Finding(
                code=FindingCode.FRAMES_DROPPED,
                detail="3 dropped frames",
                severity=Severity.BLOCKING,
                where=TimeRange(start_s=0.0, end_s=10.0),
            )
        ])
        assert severities == ["blocking"]

    def test_the_enums_value_is_written_not_its_repr(self) -> None:
        """The same trap the codes fell into. From Python 3.11 a `str, Enum`
        member stringifies to `Severity.BLOCKING`, which matches nothing."""
        from trimbin_agents.contracts.base import (
            Finding,
            FindingCode,
            Severity,
            TimeRange,
        )

        from app.services.decisions import _findings

        _, _, _, severities = _findings([
            Finding(
                code=FindingCode.FOCUS_LOST,
                detail="focus goes",
                severity=Severity.ATTENTION,
                where=TimeRange(start_s=1.0, end_s=2.0),
            )
        ])
        assert severities == ["attention"]
        assert "Severity." not in severities[0]


class TestTimecodesSurviveTheWrite:
    """The bug that made every finding in the archive say "throughout".

    Two shapes reach the writer. A contract Finding nests its span under
    `where`; review._merge_findings and a human override pass it flat, as
    start_s and end_s. The writer read only `where`, found nothing on the flat
    shape, and wrote 0.0.

    So every timecode in the decisions table was zero from the day it was
    written — and it looked like a model problem. The prompt was rewritten to
    demand spans, the schema was made to require them, and Vertex rejected the
    stricter schema outright. None of that was the cause. The model had been
    supplying them all along and they were being flattened on the way in.
    """

    def test_a_flat_finding_keeps_its_span(self) -> None:
        from app.services.decisions import _findings

        codes, starts, ends, _ = _findings(
            [{"code": "stability.shake", "start_s": 4.2, "end_s": 7.8}]
        )
        assert (codes, starts, ends) == (["stability.shake"], [4.2], [7.8])

    def test_a_nested_finding_keeps_its_span(self) -> None:
        from trimbin_agents.contracts.base import (
            FindingCode,
            Finding,
            Severity,
            TimeRange,
        )

        from app.services.decisions import _findings

        f = Finding(
            code=FindingCode.CONTINUITY_PROP,
            detail="cup in the other hand",
            severity=Severity.ATTENTION,
            where=TimeRange(start_s=12.0, end_s=14.0),
        )
        codes, starts, ends, severities = _findings([f])
        assert (codes, starts, ends) == (["continuity.prop"], [12.0], [14.0])
        assert severities == ["attention"]

    def test_a_finding_with_no_span_at_all_is_still_written(self) -> None:
        """Zero-zero here means "we do not know", which review widens to the
        whole take before it gets this far. Losing the row entirely would be
        worse than losing its timecode."""
        from app.services.decisions import _findings

        codes, starts, ends, severities = _findings([{"code": "performance.note"}])
        assert codes == ["performance.note"]
        assert (starts, ends) == ([0.0], [0.0])
        # And no severity, said as an empty string rather than as a level. A
        # default of "attention" here would be a judgement nobody made.
        assert severities == [""]

    def test_both_shapes_in_one_batch(self) -> None:
        """review._merge_findings emits exactly this: ffmpeg's flat findings
        beside the panel's contract objects, in one list."""
        from trimbin_agents.contracts.base import (
            FindingCode,
            Finding,
            Severity,
            TimeRange,
        )

        from app.services.decisions import _findings

        mixed = [
            {"code": "focus.lost", "start_s": 6.0, "end_s": 12.0},
            Finding(
                code=FindingCode.DIALOGUE_INCOMPLETE,
                detail="stops mid-line",
                severity=Severity.BLOCKING,
                where=TimeRange(start_s=28.0, end_s=30.0),
            ),
        ]
        codes, starts, ends, severities = _findings(mixed)
        assert codes == ["focus.lost", "dialogue.incomplete"]
        assert starts == [6.0, 28.0]
        assert ends == [12.0, 30.0]
        # ffmpeg's flat finding carries no severity; the panel's does. Both are
        # written, and the arrays stay the same length as the codes — a shorter
        # one would silently shift every colour by a row.
        assert severities == ["", "blocking"]
        assert len(severities) == len(codes)
