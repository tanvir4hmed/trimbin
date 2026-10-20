"""Real database tests; CI provides a disposable PostgreSQL instance."""

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest

from app.foundation.jobs import PostgresJobs
from app.foundation.repository import Conflict, PostgresRepository, migrate

DSN = os.getenv("FOUNDATION_TEST_DSN", "")
pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL not configured")


@pytest.fixture
def store():
    migrate(DSN)
    migrate(DSN)  # Idempotent migration ledger, no duplicate schema.
    project = uuid4().int % (2**62)
    with psycopg.connect(DSN) as conn:
        conn.execute("INSERT INTO projects VALUES (%s, 'test')", (project,))
    return PostgresRepository(DSN), PostgresJobs(DSN), project


def test_atomic_revisions_receipts_outbox_and_project_scope(store):
    repo, _, project = store
    key = uuid4()
    first = repo.save(project, "timeline", "film", 0, {"ranges": [1]}, "editor", key)
    assert first["revision"] == 1
    assert repo.save(project, "timeline", "film", 0, {"ranges": [1]}, "editor", key)["replayed"]
    with pytest.raises(Conflict):
        repo.save(project, "timeline", "film", 0, {"ranges": [2]}, "editor", key)
    with pytest.raises(Conflict):
        repo.save(project, "timeline", "film", 0, {}, "editor", uuid4())
    assert repo.read(project, "timeline", "film")["revision"] == 1
    assert repo.read(project + 1, "timeline", "film") is None
    with psycopg.connect(DSN) as conn:
        assert (
            conn.execute("SELECT count(*) FROM outbox WHERE project_id=%s", (project,)).fetchone()[
                0
            ]
            == 1
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM state_versions WHERE project_id=%s", (project,)
            ).fetchone()[0]
            == 1
        )


def test_simultaneous_writes_have_one_winner(store):
    repo, _, project = store

    def save(_):
        try:
            return repo.save(project, "timeline", "film", 0, {}, "editor", uuid4())
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, range(2)))
    assert sum(result is not None for result in results) == 1


def test_concurrent_command_replay_is_exactly_one_event(store):
    repo, _, project = store
    key = uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: repo.save(project, "timeline", "film", 0, {}, "editor", key), range(2)
            )
        )
    assert results[0]["event_id"] == results[1]["event_id"]
    assert sum(result["replayed"] for result in results) == 1


def test_queue_recovery_fences_old_worker_and_preserves_result(store):
    _, queue, project = store
    job_id = queue.enqueue(project, "render", {"revision": 1}, "render-1")
    assert queue.enqueue(project, "render", {"revision": 1}, "render-1") == job_id
    with pytest.raises(Conflict):
        queue.enqueue(project, "render", {"revision": 2}, "render-1")
    job = queue.claim()
    assert job["id"] == job_id
    with psycopg.connect(DSN) as conn:
        conn.execute("UPDATE jobs SET lease_until=now()-interval '1 second' WHERE id=%s", (job_id,))
    replacement = queue.claim()
    assert replacement["attempts"] == 2
    assert not queue.finish(job_id, job["lease_token"], {"wrong": True})
    assert not queue.heartbeat(job_id, job["lease_token"])
    assert queue.finish(job_id, replacement["lease_token"], {"checksum": "test"})
    assert not queue.cancel(project, job_id)


def test_cancel_scoped_and_bounded_retry(store):
    _, queue, project = store
    job_id = queue.enqueue(project, "render", {}, "cancel", max_attempts=1)
    assert not queue.cancel(project + 1, job_id)
    job = queue.claim()
    assert queue.cancel(project, job_id)
    assert not queue.heartbeat(job_id, job["lease_token"])
    assert queue.finish(job_id, job["lease_token"], {"discard": True})
    with psycopg.connect(DSN) as conn:
        row = conn.execute("SELECT state,result FROM jobs WHERE id=%s", (job_id,)).fetchone()
        assert row == ("cancelled", None)
    retry_id = queue.enqueue(project, "analyze", {}, "retry", max_attempts=1)
    job = queue.claim()
    assert job["id"] == retry_id
    assert queue.fail(retry_id, job["lease_token"], "provider_timeout")
    with psycopg.connect(DSN) as conn:
        assert (
            conn.execute("SELECT state FROM jobs WHERE id=%s", (retry_id,)).fetchone()[0]
            == "failed"
        )
