"""Job tracking, in Firestore.

An editor drops two hundred clips and closes the tab. Without something durable
to come back to, a long ingest is indistinguishable from one that died quietly —
and the difference is discovered weeks later in the edit.

Firestore rather than ClickHouse because progress is the opposite of what
ClickHouse is for: it changes constantly, it is read one row at a time, and none
of its history is worth keeping.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from google.cloud import firestore, pubsub_v1

from ..config import settings

log = logging.getLogger(__name__)

COLLECTION = "jobs"

_db: firestore.AsyncClient | None = None
_publisher: pubsub_v1.PublisherClient | None = None


def db() -> firestore.AsyncClient:
    global _db
    if _db is None:
        _db = firestore.AsyncClient(project=settings.project_id)
    return _db


def publisher() -> pubsub_v1.PublisherClient:
    global _publisher
    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient()
    return _publisher


@dataclass
class Job:
    job_id: UUID
    project_id: int
    kind: str
    state: str
    total_items: int
    completed_items: int
    failed_items: int
    failures: list[dict] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    opened_by: str = ""


async def open_job(
    project_id: int,
    kind: str,
    total_items: int,
    opened_by: str,
) -> UUID:
    """Create the record before any work starts.

    Deliberately before a single byte moves. A job that only appears once
    something succeeds cannot represent an upload that failed at the first file.
    """
    job_id = uuid4()
    await db().collection(COLLECTION).document(str(job_id)).set({
        "project_id": project_id,
        "kind": kind,
        "state": "uploading",
        "total_items": total_items,
        "completed_items": 0,
        "failed_items": 0,
        "failures": [],
        "started_at": datetime.now(UTC),
        "finished_at": None,
        "opened_by": opened_by,
    })
    log.info("job %s opened: %s, %d items", job_id, kind, total_items)
    return job_id


async def get_job(job_id: UUID) -> Job | None:
    snapshot = await db().collection(COLLECTION).document(str(job_id)).get()
    if not snapshot.exists:
        return None
    d = snapshot.to_dict() or {}
    return Job(
        job_id=job_id,
        project_id=d.get("project_id", 0),
        kind=d.get("kind", ""),
        state=d.get("state", "unknown"),
        total_items=d.get("total_items", 0),
        completed_items=d.get("completed_items", 0),
        failed_items=d.get("failed_items", 0),
        failures=d.get("failures", []),
        started_at=d.get("started_at") or datetime.now(UTC),
        finished_at=d.get("finished_at"),
        opened_by=d.get("opened_by", ""),
    )


async def set_total(job_id: UUID, total: int) -> None:
    """Correct the count once we know what actually arrived.

    The grant was issued for what the browser intended to upload; this is what
    turned up. Leaving the optimistic figure would show a progress bar that never
    reaches the end.
    """
    await db().collection(COLLECTION).document(str(job_id)).update({
        "total_items": total,
        "state": "processing",
    })


async def record_missing(job_id: UUID, missing: list[UUID]) -> None:
    """Clips the browser claimed and storage does not have.

    Recorded as failures rather than dropped, because an ingest that silently
    processes 196 of 200 files is worse than one that fails.
    """
    ref = db().collection(COLLECTION).document(str(job_id))
    await ref.update({
        "failed_items": firestore.Increment(len(missing)),
        "failures": firestore.ArrayUnion([
            {"clip_id": str(c), "reason": "not found in storage after upload"}
            for c in missing
        ]),
    })


async def record_progress(job_id: UUID, clip_id: UUID, ok: bool, reason: str = "") -> None:
    """Count one clip, and close the job if that was the last one.

    In a transaction, not two writes. Ten workers finish at once, and the last
    of them has to see the other nine's counts to know it is the last. Reading
    after an unconditioned increment gives every worker a different answer, and
    either all of them or none of them decide the job is over.

    Closing here rather than in a sweeper because there is no other moment that
    knows. Nothing polls this collection, and a job left in "processing" tells an
    editor who came back that their upload is still going.
    """
    ref = db().collection(COLLECTION).document(str(job_id))

    @firestore.async_transactional
    async def count(transaction) -> tuple[int, int, int]:
        snapshot = await ref.get(transaction=transaction)
        d = snapshot.to_dict() or {}

        completed = d.get("completed_items", 0) + (1 if ok else 0)
        failed = d.get("failed_items", 0) + (0 if ok else 1)
        total = d.get("total_items", 0)

        update: dict = {"completed_items": completed, "failed_items": failed}
        if not ok:
            update["failures"] = firestore.ArrayUnion(
                [{"clip_id": str(clip_id), "reason": reason}]
            )

        # Every clip accounted for, one way or the other. A job with failures
        # still finishes — "done" describes the work, not the outcome, and the
        # failures are listed beside it.
        if total and completed + failed >= total:
            update["state"] = "done"
            update["finished_at"] = datetime.now(UTC)

        transaction.update(ref, update)
        return completed, failed, total

    completed, failed, total = await count(db().transaction())

    if total and completed + failed >= total:
        log.info(
            "job %s finished: %d done, %d failed of %d", job_id, completed, failed, total
        )


async def abandon(job_id: UUID, reason: str) -> None:
    """Close a job that failed before any work could be queued.

    A job is opened before the first byte moves, which is right — an upload that
    dies on the first file should still leave a record. But it means a failure
    between opening and queueing leaves a job that nothing will ever advance,
    and an editor watching a progress bar for work that was never started.
    """
    await db().collection(COLLECTION).document(str(job_id)).update({
        "state": "failed",
        "finished_at": datetime.now(UTC),
        "failures": firestore.ArrayUnion([{"clip_id": "", "reason": reason}]),
    })
    log.warning("job %s abandoned: %s", job_id, reason)


async def close_empty(job_id: UUID) -> None:
    """Finish a job that has nothing to process.

    Every clip the browser claimed is missing from storage, so no worker will
    ever run and nothing will ever close this. Without it the editor watches a
    progress bar for an upload that finished failing before it started.
    """
    await db().collection(COLLECTION).document(str(job_id)).update({
        "state": "done",
        "finished_at": datetime.now(UTC),
    })
    log.info("job %s closed with nothing to process", job_id)


async def enqueue_ingest(job_id: UUID, project_id: int, clip_ids: list[UUID]) -> None:
    """One message per clip.

    Per clip rather than per batch so a single unreadable file cannot take the
    other 199 down with it, and so a retry re-runs one clip instead of a day.

    project_id is not optional and is not a convenience. The worker builds the
    object path from it, so a message without one sends the worker looking in a
    bucket prefix that does not exist, and the clip is reported as never having
    been uploaded — which is both wrong and the least helpful thing it could
    say. This was exactly that bug.
    """
    topic = publisher().topic_path(settings.project_id, settings.ingest_topic)

    for clip_id in clip_ids:
        publisher().publish(
            topic,
            b"",
            job_id=str(job_id),
            clip_id=str(clip_id),
            project_id=str(project_id),
        )

    log.info("queued %d clips for job %s, project %d", len(clip_ids), job_id, project_id)
