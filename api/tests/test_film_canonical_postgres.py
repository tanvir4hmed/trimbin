"""Shot/scene film controls and export timeline must commit into one authority."""

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from test_evidence_postgres import workspace  # noqa: F401

from app.services import film, film_canonical
from app.timeline.store import TimelineStore

pytestmark = pytest.mark.skipif(
    not os.getenv("FOUNDATION_TEST_DSN"), reason="Disposable PostgreSQL required"
)


@pytest.fixture
def editor(request, monkeypatch):
    evidence, project, source = request.getfixturevalue("workspace")
    timing = {
        "fps": {"numerator": 24, "denominator": 1},
        "frame_count": 240,
        "width": 1920,
        "height": 1080,
        "sha256": "a" * 64,
    }
    with evidence.connection() as conn:
        conn.execute(
            "INSERT INTO state_documents(project_id,kind,document_id,body) "
            "VALUES (%s,'source_timing',%s,%s)",
            (project, f"{source}/" + "a" * 64, Jsonb(timing)),
        )

    async def prepare(*args):
        return timing

    async def sources(*args, **kwargs):
        return []

    monkeypatch.setattr(film_canonical, "prepare", prepare)
    monkeypatch.setattr(film, "sources", sources)
    monkeypatch.setattr(film_canonical.settings, "database_url", evidence.dsn)
    return evidence, project, source


@pytest.mark.asyncio
async def test_compatibility_replay_reordering_and_history_share_canonical_revision(editor):
    evidence, project, source = editor
    body = film.FilmSave(
        rev=0,
        command_id=uuid4(),
        name="Cut",
        ranges=[film.FilmRange(id=uuid4(), clip_id=source, start_s=1, end_s=4)],
    )
    first = await film_canonical.save(project, body, "editor@example.test")
    assert first.rev == 1
    assert (await film_canonical.save(project, body, "editor@example.test")).rev == 1
    assert TimelineStore(evidence.dsn).read(project, "film")["body"]["clips"][0]["in_frame"] == 24
    with pytest.raises(HTTPException) as rejected:
        await film_canonical.save(
            project, body.model_copy(update={"name": "Changed retry"}), "editor@example.test"
        )
    assert rejected.value.status_code == 409
    second = body.model_copy(update={"rev": 1, "command_id": uuid4(), "name": "Renamed"})
    assert (await film_canonical.save(project, second, "editor@example.test")).rev == 2
    assert len(evidence.snapshot(project)["selections"]) == 1
    assert (await film_canonical.read(project, 1)).name == "Cut"


@pytest.mark.asyncio
async def test_invalid_later_range_rolls_back_evidence_and_timeline_together(editor):
    evidence, project, source = editor
    body = film.FilmSave(
        rev=0,
        command_id=uuid4(),
        name="Cut",
        ranges=[
            film.FilmRange(id=uuid4(), clip_id=source, start_s=1, end_s=4),
            film.FilmRange(id=uuid4(), clip_id=source, start_s=8, end_s=20),
        ],
    )
    with pytest.raises(ValueError):
        await film_canonical.save(project, body, "editor@example.test")
    assert evidence.snapshot(project)["revision"] == 0
    assert TimelineStore(evidence.dsn).read(project, "film")["revision"] == 0
