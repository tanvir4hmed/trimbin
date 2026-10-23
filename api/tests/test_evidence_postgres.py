"""Deferred disposable-PostgreSQL verification for portable evidence commands."""

import os
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.evidence.contracts import EditCommand, EvidenceError
from app.evidence.store import EvidenceStore
from app.foundation.repository import Conflict, migrate

DSN = os.getenv("FOUNDATION_TEST_DSN", "")
pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL not configured")


@pytest.fixture
def workspace():
    migrate(DSN)
    project, source, job = uuid4().int % (2**62), uuid4(), uuid4()
    with psycopg.connect(DSN) as conn:
        conn.execute("INSERT INTO projects(id,name) VALUES (%s,'evidence-test')", (project,))
        conn.execute(
            "INSERT INTO project_members VALUES (%s,'editor@example.test','editor')", (project,)
        )
        conn.execute(
            "INSERT INTO project_members VALUES (%s,'viewer@example.test','viewer')", (project,)
        )
        conn.execute(
            "INSERT INTO jobs(id,project_id,kind,payload,dedup_key,max_attempts,state) "
            "VALUES (%s,%s,'media',%s,%s,1,'succeeded')",
            (job, project, Jsonb({}), str(job)),
        )
        conn.execute(
            "INSERT INTO media_sources(id,project_id,root_alias,relative_path,filename,"
            "job_id,fingerprint,metadata,created_by) VALUES (%s,%s,'library','a.mov',"
            "'a.mov',%s,%s,%s,'editor@example.test')",
            (
                source,
                project,
                job,
                "a" * 64,
                Jsonb({"duration": {"numerator": 10, "denominator": 1}}),
            ),
        )
    return EvidenceStore(DSN), project, source


def edit(store, project, revision, operation, **kwargs):
    command = EditCommand(
        command_id=uuid4(), expected_revision=revision, operation=operation, **kwargs
    )
    return command, store.edit(project, "editor@example.test", command)


def note(source, text="Original observation"):
    return {
        "source_id": str(source),
        "start_us": 0,
        "end_us": 1000000,
        "kind": "moment",
        "text": text,
    }


def test_corrections_replay_and_pinned_selections(workspace):
    store, project, source = workspace
    command, result = edit(store, project, 0, "note", note=note(source))
    assert result["revision"] == 1
    assert store.edit(project, "editor@example.test", command)["replayed"]
    item = store.snapshot(project)["items"][0]
    edit(store, project, 1, "correct", item_id=UUID(item["id"]), note=note(source, "Corrected"))
    edit(store, project, 2, "select", item_id=UUID(item["id"]))
    edit(store, project, 3, "correct", item_id=UUID(item["id"]), decision="retracted")
    state = store.snapshot(project)
    assert state["items"][0]["text"] == "Corrected"
    assert state["items"][0]["decision"] == "retracted"
    assert state["selections"][0]["text"] == "Corrected"
    assert state["selections"][0]["decision"] == "accepted"
    with pytest.raises(Conflict):
        edit(store, project, 1, "note", note=note(source))
    assert store.snapshot(project)["revision"] == 4


def test_scope_role_and_source_intervals(workspace):
    store, project, source = workspace
    command = EditCommand(
        command_id=uuid4(), expected_revision=0, operation="note", note=note(source)
    )
    with pytest.raises(EvidenceError, match="project_not_found"):
        store.edit(project, "viewer@example.test", command)
    with pytest.raises(EvidenceError, match="project_not_found"):
        store.edit(project + 1, "editor@example.test", command)
    with pytest.raises(EvidenceError, match="range_outside_source"):
        edit(store, project, 0, "note", note={**note(source), "end_us": 11000000})
    assert store.snapshot(project)["revision"] == 0
    assert not store.snapshot(project + 1)["items"]


def test_complete_generation_fencing_preserves_previous_head(workspace):
    from app.evidence.contracts import AnalyzeCommand
    from app.foundation.jobs import PostgresJobs
    from app.inference.contracts import TaskRequest

    store, project, source = workspace
    queue = PostgresJobs(DSN)

    def enqueue(revision):
        command = AnalyzeCommand(
            command_id=uuid4(), expected_revision=revision, source_id=source, mode="fixture"
        )
        result = store.enqueue(project, "editor@example.test", command.model_dump(mode="json"), {})
        return store.run(project, UUID(result["run_id"]))

    def records(run):
        request = TaskRequest.model_validate(
            {
                "project_id": project,
                "task": "visual",
                "sources": run["plan"]["sources"],
                "windows": [
                    {"id": "w", "source_id": str(source), "start_us": 0, "end_us": 10000000}
                ],
                "frames": [
                    {
                        "id": "f",
                        "source_id": str(source),
                        "at_us": 0,
                        "sha256": "b" * 64,
                        "mime": "image/png",
                    }
                ],
                "brief_revision": "1",
                "evidence_revision": "0",
                "recipe": "explicit-test",
            }
        )
        return [
            {
                "status": "fixture",
                "input_manifest": request.model_dump(mode="json"),
                "output": {
                    "status": "abstained",
                    "reason": "No inference in this fixture",
                    "findings": [],
                },
            }
        ]

    first = enqueue(0)
    job = queue.claim(kinds=["evidence_analysis"])
    store.publish(job, first, records(first))
    second = enqueue(1)
    job2 = queue.claim(kinds=["evidence_analysis"])
    third = enqueue(1)
    store.publish(job2, second, records(second))
    assert not store.run(project, second["id"])["published"]
    assert store.snapshot(project)["revision"] == 1
    job3 = queue.claim(kinds=["evidence_analysis"])
    assert queue.cancel(project, third["job_id"])
    with pytest.raises(EvidenceError, match="lease_lost"):
        store.publish(job3, third, records(third))
    with store.connection() as conn:
        assert store.current(conn, project)["body"]["heads"][first["scope"]] == str(first["id"])
    queue.finish(job3["id"], job3["lease_token"], {})
