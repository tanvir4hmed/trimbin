"""Film source integrity and honest review denominators."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.services import film, quality
from app.services.full_take import consolidate_findings


def source():
    return film.FilmSource(
        clip_id=uuid4(),
        scene=1,
        shot=2,
        scene_code="12A-PU",
        shot_code="B",
        take_no=4,
        duration_s=70,
        fps=23.976,
        proxy_uri="/media/proxy.m3u8",
        sprite_uri="",
    )


def test_no_reviews_is_not_perfect_or_zero_accuracy():
    stats = quality.counts({"findings": 20, "analysed": 8})
    assert stats.agreement_pct is None
    assert stats.reviewed == 0


def test_accuracy_denominator_excludes_unreviewed():
    stats = quality.counts({"findings": 200, "confirmed": 6, "corrected": 2, "dismissed": 2})
    assert stats.reviewed == 10
    assert stats.agreement_pct == 60


@pytest.mark.parametrize(
    "start,end", [(5, 5), (5, 4), (-1, 4), (0, float("inf")), (float("nan"), 4)]
)
def test_invalid_film_range(start, end):
    with pytest.raises(ValidationError):
        film.FilmRange(id=uuid4(), clip_id=uuid4(), start_s=start, end_s=end)


def test_multiranges_do_not_expand_a_scene_or_deduplicate_editorial_repeats():
    media = source()
    ranges = [
        film.FilmRange(id=uuid4(), clip_id=media.clip_id, start_s=a, end_s=b)
        for a, b in [(58, 61), (4, 8), (58, 61)]
    ]
    film.validate_sources(ranges, [media])
    result = film.materialize(9, {"ranges": [r.model_dump(mode="json") for r in ranges]}, [media])
    assert result.duration_s == 10
    assert [e.record_start_s for e in result.entries] == [0, 3, 7]
    assert all(e.available for e in result.entries)
    assert [e.start_s for e in result.entries] == [58, 4, 58]


def test_missing_or_cross_project_source_refused():
    row = film.FilmRange(id=uuid4(), clip_id=uuid4(), start_s=1, end_s=2)
    with pytest.raises(HTTPException) as error:
        film.validate_sources([row], [source()])
    assert error.value.status_code == 422


def test_out_beyond_source_refused():
    media = source()
    row = film.FilmRange(id=uuid4(), clip_id=media.clip_id, start_s=69, end_s=71)
    with pytest.raises(HTTPException):
        film.validate_sources([row], [media])


def test_deleted_source_is_visible_as_unavailable_not_silently_removed():
    row = film.FilmRange(id=uuid4(), clip_id=uuid4(), start_s=1, end_s=6)
    result = film.materialize(9, {"ranges": [row.model_dump(mode="json")]}, [])
    assert len(result.entries) == 1
    assert not result.entries[0].available
    assert result.duration_s == 5


def test_duplicate_row_identity_refused_but_duplicate_clip_allowed():
    row = film.FilmRange(id=uuid4(), clip_id=uuid4(), start_s=1, end_s=2)
    with pytest.raises(ValidationError):
        film.FilmSave(rev=0, command_id=uuid4(), ranges=[row, row])
    film.FilmSave(rev=0, command_id=uuid4(), ranges=[row, row.model_copy(update={"id": uuid4()})])


def test_revision_is_mandatory():
    with pytest.raises(ValidationError):
        film.FilmSave(command_id=uuid4(), ranges=[])


def test_descriptive_focus_note_cannot_expand_a_localized_fault():
    base = {"code": "focus.lost", "evidence_segment_ids": [uuid4()], "sources": ["measured"]}
    findings = consolidate_findings(
        [
            {**base, "severity": "note", "start_s": 0, "end_s": 70},
            {**base, "severity": "attention", "start_s": 58, "end_s": 61},
        ]
    )
    assert len(findings) == 2
    fault = next(row for row in findings if row["severity"] == "attention")
    assert (fault["start_s"], fault["end_s"]) == (58, 61)
