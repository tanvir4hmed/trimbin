"""Deferred database timeline replay/history/authority checks."""

import os
from uuid import UUID, uuid4

import pytest
from psycopg.types.json import Jsonb
from test_evidence_postgres import workspace  # noqa: F401

from app.evidence.contracts import EditCommand, EvidenceError
from app.foundation.repository import Conflict
from app.timeline.contracts import Clip, Save, Sequence
from app.timeline.store import TimelineStore

pytestmark = pytest.mark.skipif(
    not os.getenv("FOUNDATION_TEST_DSN"), reason="Disposable PostgreSQL not configured"
)


def test_timeline_receipts_stale_writes_and_historical_evidence(request):
    evidence, project, source = request.getfixturevalue("workspace")
    evidence.edit(
        project,
        "editor@example.test",
        EditCommand(
            command_id=uuid4(),
            expected_revision=0,
            operation="note",
            note={
                "source_id": source,
                "start_us": 0,
                "end_us": 1000000,
                "kind": "moment",
                "text": "Selected",
            },
        ),
    )
    item = evidence.snapshot(project)["items"][0]
    selection = uuid4()
    evidence.edit(
        project,
        "editor@example.test",
        EditCommand(
            command_id=selection, expected_revision=1, operation="select", item_id=UUID(item["id"])
        ),
    )
    with evidence.connection() as conn:
        conn.execute(
            "INSERT INTO state_documents(project_id,kind,document_id,body) "
            "VALUES (%s,'source_timing',%s,%s)",
            (
                project,
                f"{source}/" + "a" * 64,
                Jsonb(
                    {
                        "fps": {"numerator": 24, "denominator": 1},
                        "frame_count": 240,
                        "sha256": "a" * 64,
                    }
                ),
            ),
        )
    store = TimelineStore(evidence.dsn)
    clip = Clip(id=uuid4(), source_id=source, selection_id=selection, in_frame=0, out_frame=24)
    first = Save(command_id=uuid4(), expected_revision=0, sequence=Sequence(), clips=[clip])
    assert store.save(project, "film", "editor@example.test", first)["revision"] == 1
    assert store.save(project, "film", "editor@example.test", first)["replayed"]
    with pytest.raises(Conflict):
        store.save(
            project, "film", "editor@example.test", first.model_copy(update={"command_id": uuid4()})
        )
    with pytest.raises(EvidenceError, match="project_not_found"):
        store.save(project, "film", "viewer@example.test", first)
    store.save(
        project,
        "film",
        "editor@example.test",
        Save(command_id=uuid4(), expected_revision=1, sequence=Sequence(), clips=[]),
    )
    evidence.edit(
        project,
        "editor@example.test",
        EditCommand(
            command_id=uuid4(), expected_revision=2, operation="unselect", item_id=selection
        ),
    )
    restored = first.model_copy(update={"command_id": uuid4(), "expected_revision": 2})
    assert store.save(project, "film", "editor@example.test", restored)["revision"] == 3
    assert (
        store.read(project, "film", 1)["body"]["clips"]
        == store.read(project, "film", 3)["body"]["clips"]
    )
    assert store.read(project + 1, "film")["body"] is None
