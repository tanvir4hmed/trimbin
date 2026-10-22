"""Deferred export request isolation and exact-revision queue tests."""

import os
from uuid import UUID, uuid4

import pytest
from test_editable_exports import example
from test_evidence_postgres import workspace  # noqa: F401

from app.evidence.contracts import EvidenceError
from app.exports.store import ExportRequest, ExportStore
from app.foundation.repository import Conflict, PostgresRepository
from app.inference.contracts import fingerprint

pytestmark = pytest.mark.skipif(
    not os.getenv("FOUNDATION_TEST_DSN"), reason="Disposable PostgreSQL not configured"
)


def test_export_pins_old_revision_and_replays_request(request):
    evidence, project, _ = request.getfixturevalue("workspace")
    body, _ = example()
    repo = PostgresRepository(evidence.dsn)
    repo.save(project, "canonical_timeline", "film", 0, body, "editor@example.test", uuid4())
    store = ExportStore(evidence.dsn)
    command = ExportRequest(command_id=uuid4(), format="native", revision=1)
    first = store.enqueue_export(project, "film", "editor@example.test", command)
    assert (
        store.enqueue_export(project, "film", "editor@example.test", command)["job_id"]
        == first["job_id"]
    )
    changed = {**body, "sequence": {**body["sequence"], "name": "Changed"}}
    repo.save(project, "canonical_timeline", "film", 1, changed, "editor@example.test", uuid4())
    job = store.export_job(project, UUID(first["job_id"]))
    assert job["payload"]["snapshot_sha256"] == fingerprint(body)
    assert job["payload"]["revision"] == 1
    with pytest.raises(Conflict):
        store.enqueue_export(
            project, "film", "editor@example.test", command.model_copy(update={"format": "fcp7"})
        )
    with pytest.raises(EvidenceError, match="project_not_found"):
        store.enqueue_export(project, "film", "viewer@example.test", command)
    with pytest.raises(EvidenceError, match="export_not_found"):
        store.export_job(project + 1, UUID(first["job_id"]))
    with store.connection() as conn:
        conn.execute(
            "UPDATE jobs SET state='cancelled',cancel_requested=true WHERE id=%s",
            (first["job_id"],),
        )
