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
    ref = db().collection(COLLECTION).document(str(job_id))
    if ok:
        await ref.update({"completed_items": firestore.Increment(1)})
        return

    await ref.update({
        "failed_items": firestore.Increment(1),
        "failures": firestore.ArrayUnion([{"clip_id": str(clip_id), "reason": reason}]),
    })


async def finish(job_id: UUID) -> None:
    await db().collection(COLLECTION).document(str(job_id)).update({
        "state": "done",
        "finished_at": datetime.now(UTC),
    })


async def enqueue_ingest(job_id: UUID, clip_ids: list[UUID]) -> None:
    """One message per clip.

    Per clip rather than per batch so a single unreadable file cannot take the
    other 199 down with it, and so a retry re-runs one clip instead of a day.
    """
    topic = publisher().topic_path(settings.project_id, settings.ingest_topic)

    for clip_id in clip_ids:
        publisher().publish(
            topic,
            b"",
            job_id=str(job_id),
            clip_id=str(clip_id),
        )

    log.info("queued %d clips for job %s", len(clip_ids), job_id)
