"""Job tracking, in Firestore.

An editor drops two hundred clips and closes the tab. Without something durable
to come back to, a long ingest is indistinguishable from one that died quietly —
and the difference is discovered weeks later in the edit.

Firestore rather than ClickHouse because progress is the opposite of what
ClickHouse is for: it changes constantly, it is read one row at a time, and none
of its history is worth keeping.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from google.cloud import firestore, pubsub_v1

from ..config import settings

log = logging.getLogger(__name__)

COLLECTION = "jobs"
ANALYSIS_QUEUE_COLLECTION = "analysis_tasks"


class State:
    """Every state a job can be in, named once.

    The worker wrote "done" and the route asked whether the state was
    "finished" — two vocabularies for one thing, neither of them wrong on its
    own. The upload screen polled forever, showed real progress the whole time,
    and never said it had finished. Nothing errored anywhere.

    A string literal in two files is not a shared vocabulary. This is.
    """

    UPLOADING = "uploading"  # tickets issued, bytes moving
    PROCESSING = "processing"  # queued, workers running
    DONE = "done"  # every clip accounted for, failures included
    FAILED = "failed"  # abandoned before any work could start


# States from which nothing further happens. The interface stops polling here.
#
# "done" covers a batch with failures in it: the word describes the work, not
# the outcome, and the failures are listed beside it.
TERMINAL = frozenset({State.DONE, State.FAILED})

ALL_STATES = frozenset(
    {
        State.UPLOADING,
        State.PROCESSING,
        State.DONE,
        State.FAILED,
    }
)

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
    # Where the uploader said this footage belongs. Zero means they did not say
    # and the slate decides.
    target_scene: int = 0
    target_shot: int = 0
    # One entry per clip: what happened to it, and where it landed.
    items: list[dict] = field(default_factory=list)


async def open_job(
    project_id: int,
    kind: str,
    total_items: int,
    opened_by: str,
    target_scene: int = 0,
    target_shot: int = 0,
) -> UUID:
    """Create the record before any work starts.

    Deliberately before a single byte moves. A job that only appears once
    something succeeds cannot represent an upload that failed at the first file.
    """
    job_id = uuid4()
    await (
        db()
        .collection(COLLECTION)
        .document(str(job_id))
        .set(
            {
                "project_id": project_id,
                "kind": kind,
                "state": State.UPLOADING,
                "total_items": total_items,
                "completed_items": 0,
                "failed_items": 0,
                "failures": [],
                "started_at": datetime.now(UTC),
                "finished_at": None,
                "opened_by": opened_by,
                "target_scene": target_scene,
                "target_shot": target_shot,
                "items": [],
            }
        )
    )
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
        target_scene=int(d.get("target_scene", 0) or 0),
        target_shot=int(d.get("target_shot", 0) or 0),
        items=d.get("items", []),
    )


async def set_total(job_id: UUID, total: int) -> None:
    """Correct the count once we know what actually arrived.

    The grant was issued for what the browser intended to upload; this is what
    turned up. Leaving the optimistic figure would show a progress bar that never
    reaches the end.
    """
    await (
        db()
        .collection(COLLECTION)
        .document(str(job_id))
        .update(
            {
                "total_items": total,
                "state": State.PROCESSING,
            }
        )
    )


async def record_missing(job_id: UUID, missing: list[UUID]) -> None:
    """Clips the browser claimed and storage does not have.

    Recorded as failures rather than dropped, because an ingest that silently
    processes 196 of 200 files is worse than one that fails.
    """
    ref = db().collection(COLLECTION).document(str(job_id))
    await ref.update(
        {
            "failed_items": firestore.Increment(len(missing)),
            "failures": firestore.ArrayUnion(
                [
                    {"clip_id": str(c), "reason": "not found in storage after upload"}
                    for c in missing
                ]
            ),
        }
    )


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
            update["failures"] = firestore.ArrayUnion([{"clip_id": str(clip_id), "reason": reason}])

        # Every clip accounted for, one way or the other. A job with failures
        # still finishes — "done" describes the work, not the outcome, and the
        # failures are listed beside it.
        if total and completed + failed >= total:
            update["state"] = State.DONE
            update["finished_at"] = datetime.now(UTC)

        transaction.update(ref, update)
        return completed, failed, total

    completed, failed, total = await count(db().transaction())

    if total and completed + failed >= total:
        log.info("job %s finished: %d done, %d failed of %d", job_id, completed, failed, total)


async def record_placement(
    job_id: UUID,
    clip_id: UUID,
    filename: str,
    scene: int,
    shot: int,
    take_no: int,
    slate_raw: str,
    confident: bool,
    mismatch: str = "",
) -> None:
    """Where one clip ended up, and whether that is where it was sent.

    Written per clip so the upload screen can show the grouping as it forms
    rather than only a count. `mismatch` is empty when the slate agreed with the
    declared target, or when nothing was declared.
    """
    await (
        db()
        .collection(COLLECTION)
        .document(str(job_id))
        .update(
            {
                "items": firestore.ArrayUnion(
                    [
                        {
                            "clip_id": str(clip_id),
                            "filename": filename,
                            "scene": scene,
                            "shot": shot,
                            "take_no": take_no,
                            "slate_raw": slate_raw[:120],
                            "confident": bool(confident),
                            "mismatch": mismatch,
                        }
                    ]
                )
            }
        )
    )


async def abandon(job_id: UUID, reason: str) -> None:
    """Close a job that failed before any work could be queued.

    A job is opened before the first byte moves, which is right — an upload that
    dies on the first file should still leave a record. But it means a failure
    between opening and queueing leaves a job that nothing will ever advance,
    and an editor watching a progress bar for work that was never started.
    """
    await (
        db()
        .collection(COLLECTION)
        .document(str(job_id))
        .update(
            {
                "state": State.FAILED,
                "finished_at": datetime.now(UTC),
                "failures": firestore.ArrayUnion([{"clip_id": "", "reason": reason}]),
            }
        )
    )
    log.warning("job %s abandoned: %s", job_id, reason)


async def close_empty(job_id: UUID) -> None:
    """Finish a job that has nothing to process.

    Every clip the browser claimed is missing from storage, so no worker will
    ever run and nothing will ever close this. Without it the editor watches a
    progress bar for an upload that finished failing before it started.
    """
    await (
        db()
        .collection(COLLECTION)
        .document(str(job_id))
        .update(
            {
                "state": State.DONE,
                "finished_at": datetime.now(UTC),
            }
        )
    )
    log.info("job %s closed with nothing to process", job_id)


async def enqueue_ingest(
    job_id: UUID,
    project_id: int,
    clip_ids: list[UUID],
    filenames: dict[str, str] | None = None,
    target_scene: int = 0,
    target_shot: int = 0,
    uploaded_by: str = "",
) -> None:
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
            # Pub/Sub attributes are strings. Zero means "not declared", which
            # the worker reads as "the slate decides".
            target_scene=str(target_scene),
            target_shot=str(target_shot),
            filename=(filenames or {}).get(str(clip_id), "")[:180],
            # So the clip row can say who put it here. It has been written as an
            # empty string since the first week.
            uploaded_by=uploaded_by[:120],
        )

    log.info("queued %d clips for job %s, project %d", len(clip_ids), job_id, project_id)


async def enqueue_analysis(
    project_id: int,
    clips: list[dict],
) -> int:
    """Queue independent full-take work, one retryable message per clip."""
    topic = publisher().topic_path(settings.project_id, settings.ingest_topic)
    queued = 0
    for clip in clips:
        clip_id = str(clip["clip_id"])
        attributes = {
            "task": "full_take_analysis",
            "project_id": str(project_id),
            "clip_id": clip_id,
            "scene": str(int(clip.get("group_id", clip.get("scene", 0)) or 0)),
            "shot": str(int(clip.get("subgroup_id", clip.get("shot", 0)) or 0)),
            "take_no": str(int(clip.get("take_no", 0) or 0)),
            "duration_s": f"{float(clip.get('duration_s', 0.0)):.3f}",
        }
        task_ref = db().collection(ANALYSIS_QUEUE_COLLECTION).document(f"p{project_id}_{clip_id}")
        await task_ref.set(
            {
                **attributes,
                "state": "pending",
                "updated_at": datetime.now(UTC),
                "error": "",
            }
        )
        try:
            future = publisher().publish(topic, b"", **attributes)
            message_id = await asyncio.to_thread(future.result, timeout=30)
            await task_ref.set(
                {
                    "state": "queued",
                    "message_id": message_id,
                    "updated_at": datetime.now(UTC),
                },
                merge=True,
            )
            queued += 1
        except Exception as exc:
            await task_ref.set(
                {
                    "state": "publish_failed",
                    "error": str(exc)[:500],
                    "updated_at": datetime.now(UTC),
                },
                merge=True,
            )
            log.exception("could not queue full-take analysis for clip %s", clip_id)

    log.info(
        "queued full-take analysis for %d/%d clips in project %d", queued, len(clips), project_id
    )
    return queued


async def record_analysis_state(
    project_id: int,
    clip_id: UUID,
    state: str,
    error: str = "",
) -> None:
    await (
        db()
        .collection(ANALYSIS_QUEUE_COLLECTION)
        .document(f"p{project_id}_{clip_id}")
        .set(
            {
                "state": state,
                "error": error[:500],
                "updated_at": datetime.now(UTC),
            },
            merge=True,
        )
    )
