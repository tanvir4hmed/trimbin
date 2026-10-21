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


@pytest.fixture
def media(store, tmp_path):
    from app.config import Settings
    from app.media.files import MediaPaths
    from app.media.store import MediaStore

    _, queue, project = store
    root = tmp_path / "camera"
    root.mkdir()
    paths = MediaPaths(
        Settings(
            _env_file=None,
            originals_root=str(tmp_path / "originals"),
            proxies_root=str(tmp_path / "derived"),
            staging_root=str(tmp_path / "staging"),
            allowed_media_roots=[str(tmp_path / "originals"), str(root)],
            media_roots={"camera": str(root)},
            media_root_projects={"camera": [project]},
        )
    )
    yield MediaStore(DSN), queue, project, paths
    with psycopg.connect(DSN) as conn:
        conn.execute("DELETE FROM media_uploads WHERE project_id=%s", (project,))
        conn.execute("DELETE FROM media_sources WHERE project_id=%s", (project,))
        conn.execute("DELETE FROM jobs WHERE project_id=%s", (project,))
        conn.execute("DELETE FROM project_members WHERE project_id=%s", (project,))


def test_media_registration_retry_and_duplicate_identity(media):
    repo, queue, project, _ = media
    first = repo.register(project, "camera", "a/take.mov", "editor")
    assert repo.register(project, "camera", "a/take.mov", "editor")["id"] == first["id"]
    job = queue.claim(kinds=["media_index"])
    assert job["id"] == first["job_id"]
    repo.publish(job, "a" * 64, {"size_bytes": 12}, {"directory": "first"})
    second = repo.register(project, "camera", "b/take.mov", "editor")
    job = queue.claim(kinds=["media_index"])
    repo.publish(job, "a" * 64, {"size_bytes": 12}, {"directory": "second"})
    result = repo.get(project, second["id"])
    assert result["duplicate_of"] == first["id"]
    assert first["id"] != second["id"]
    assert result["state"] == "succeeded"
    assert repo.listing(project + 1, 0, 10) == []


def test_media_upload_resume_fsync_recovery_and_completion_replay(media):
    import hashlib

    from app.media.files import CHUNK_BYTES, MediaError
    from app.media.store import MediaStore

    repo, _, project, paths = media
    data = b"a" * CHUNK_BYTES
    upload = repo.open_upload(project, "take.mov", len(data) + 3, "editor")
    with pytest.raises(MediaError, match="upload_not_found"):
        repo.upload_status(project, upload["id"], "other-editor")
    repo.append_upload(paths, project, upload["id"], "editor", 0, data, 0)
    restarted = MediaStore(DSN)
    status = restarted.upload_status(project, upload["id"], "editor")
    assert status["received_bytes"] == len(data)
    assert status["chunk_hashes"] == [hashlib.sha256(data).hexdigest()]
    with (paths.staging / f"{upload['id']}.part").open("ab") as handle:
        handle.write(b"uncommitted")
    with pytest.raises(MediaError, match="upload_offset_conflict"):
        restarted.append_upload(paths, project, upload["id"], "editor", 0, data, 0)
    restarted.append_upload(paths, project, upload["id"], "editor", len(data), b"end", 0)
    result = restarted.complete_upload(paths, project, upload["id"], "editor")
    assert restarted.complete_upload(paths, project, upload["id"], "editor") == result
    source = restarted.get(project, result["source_id"])
    assert (
        paths.resolve(project, source["root_alias"], source["relative_path"]).read_bytes()
        == data + b"end"
    )


def test_media_rename_before_commit_recovers_without_duplicate_job(media):
    repo, _, project, paths = media
    upload = repo.open_upload(project, "take.mov", 3, "editor")
    repo.append_upload(paths, project, upload["id"], "editor", 0, b"abc", 0)
    target = paths.resolve(project, "uploads", f"p{project}/{upload['id']}/take.mov", exists=False)
    target.parent.mkdir(parents=True)
    (paths.staging / f"{upload['id']}.part").rename(target)
    result = repo.complete_upload(paths, project, upload["id"], "editor")
    assert (
        repo.complete_upload(paths, project, upload["id"], "editor")["source_id"]
        == result["source_id"]
    )
    assert len(repo.listing(project, 0, 100)) == 1


def test_media_publication_fences_expired_worker_and_relink_preserves_id(media):
    from app.media.files import MediaError

    repo, queue, project, _ = media
    source = repo.register(project, "camera", "take.mov", "editor")
    old = queue.claim(kinds=["media_index"])
    with psycopg.connect(DSN) as conn:
        conn.execute(
            "UPDATE jobs SET lease_until=now()-interval '1 second' WHERE id=%s", (old["id"],)
        )
    new = queue.claim(kinds=["media_index"])
    with pytest.raises(MediaError, match="lease_lost"):
        repo.publish(old, "wrong", {}, {})
    repo.publish(new, "a" * 64, {}, {})
    with pytest.raises(MediaError, match="relink_fingerprint_mismatch"):
        repo.relink(project, source["id"], "camera", "moved.mov", "wrong")
    repo.relink(project, source["id"], "camera", "moved.mov", "a" * 64)
    assert repo.get(project, source["id"])["relative_path"] == "moved.mov"


def test_portable_project_membership_denies_other_projects_and_reader_writes(media):
    repo, _, project, _ = media
    with psycopg.connect(DSN) as conn:
        conn.execute(
            "INSERT INTO project_members VALUES (%s,'reader@example.test','viewer')", (project,)
        )
    assert repo.allowed(project, "reader@example.test", "read")
    assert not repo.allowed(project, "reader@example.test", "write")
    assert not repo.allowed(project, "reader@example.test", "owner")
    assert not repo.allowed(project + 1, "reader@example.test", "read")
    assert not repo.allowed(project, "stranger@example.test", "read")


@pytest.mark.asyncio
async def test_media_worker_publishes_real_derivatives_and_preserves_source(media):
    import subprocess

    from app.config import Settings
    from app.media.files import digest_file
    from app.media.worker import process_job

    repo, queue, project, paths = media
    source_path = paths.roots["camera"] / "take.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x90:rate=24:duration=1",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            str(source_path),
        ],
        check=True,
        timeout=30,
    )
    digest = digest_file(source_path)
    source = repo.register(project, "camera", "take.mp4", "editor")
    job = queue.claim(kinds=["media_index"])
    assert job["id"] == source["job_id"]
    config = Settings(
        _env_file=None,
        originals_root=str(paths.originals),
        proxies_root=str(paths.derivatives),
        staging_root=str(paths.staging),
        allowed_media_roots=[str(paths.originals), str(paths.roots["camera"])],
        media_roots={"camera": str(paths.roots["camera"])},
        media_root_projects={"camera": [project]},
        media_work_bytes=32 * 1024**2,
        media_reserve_bytes=0,
    )
    await process_job(job, repo, queue, config)
    result = repo.get(project, source["id"])
    assert result["state"] == "succeeded", result["error_code"]
    assert result["fingerprint"] == digest == digest_file(source_path)
    output = paths.derivatives / result["derivatives"]["directory"]
    assert (output / "proxy.mp4").stat().st_size > 0
    assert (output / "sprite.jpg").stat().st_size > 0
