"""Revision-safe current take selection with an immutable ClickHouse delivery.

Firestore owns the mutable answer to "what stands now". ClickHouse owns the
decision event and its evidence. The two writes cannot be one database
transaction, so the Firestore transaction also creates a durable delivery row.
If ClickHouse is unavailable, the choice is not lost or silently half-written:
the event remains pending and can be delivered idempotently later.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from google.cloud import firestore

from . import decisions, revisions
from .analytics import client
from .jobs import db

log = logging.getLogger(__name__)

COLLECTION = "selection_events"


@dataclass(frozen=True)
class Committed:
    event_id: str
    rev: int
    previous: str | None


async def commit_coverage(
    project_id: int,
    scene: int,
    shot: int,
    *,
    segments: list[dict],
    reason: str,
    actor: str,
    expected_rev: int,
    source_set_hash: str = "",
) -> Committed:
    """Replace the ordered current coverage for one shot, revision-safely.

    This is a snapshot command, not a destructive history rewrite. The previous
    and new ordered lists are kept in the durable event; ClickHouse receives the
    immutable event asynchronously. A clip may appear more than once because an
    editor may use two separate source ranges from the same take.
    """
    event_id = uuid4().hex
    shot_id = f"p{project_id}_s{scene}_h{shot}"
    shot_ref = db().collection("shots").document(shot_id)
    event_ref = db().collection(COLLECTION).document(event_id)
    now = datetime.now(UTC)

    @firestore.async_transactional
    async def write(transaction) -> Committed:
        snapshot = await shot_ref.get(transaction=transaction)
        current = snapshot.to_dict() or {} if snapshot.exists else {}
        found_rev = int(current.get("rev", 0) or 0)
        revisions.check(expected_rev, found_rev)
        previous_segments = list(current.get("coverage_segments") or [])
        previous_clip = current.get("selected_clip_id") or None
        chosen = str(segments[0]["clip_id"]) if segments else ""
        transaction.set(
            shot_ref,
            {
                "project_id": project_id,
                "scene": scene,
                "shot": shot,
                "coverage_segments": segments,
                "previous_coverage_segments": previous_segments,
                # Kept during compatibility migration for old consumers.
                "selected_clip_id": chosen,
                "previous_selected_clip_id": previous_clip or "",
                "selection_reason": reason,
                "selection_by": actor,
                "selection_at": now,
                "selection_event_id": event_id,
                "selection_archive_state": "pending",
                "observed_source_set_hash": source_set_hash,
                "rev": found_rev + 1,
            },
            merge=True,
        )
        transaction.set(
            event_ref,
            {
                "event_id": event_id,
                "kind": "coverage_snapshot",
                "project_id": project_id,
                "scene": scene,
                "shot": shot,
                "chosen": chosen,
                "previous": previous_clip or "",
                "reason": reason,
                "actor": actor,
                "segments": segments,
                "source_set_hash": source_set_hash,
                "previous_segments": previous_segments,
                "revision": found_rev + 1,
                "state": "pending",
                "created_at": now,
            },
        )
        return Committed(event_id, found_rev + 1, previous_clip)

    return await write(db().transaction())


async def commit(
    project_id: int,
    scene: int,
    shot: int,
    *,
    chosen: str,
    fallback_previous: str | None,
    reason: str,
    actor: str,
    rows: list[dict],
    expected_rev: int,
) -> Committed:
    """Set the current choice and enqueue its archive event atomically."""
    event_id = uuid4().hex
    shot_id = f"p{project_id}_s{scene}_h{shot}"
    shot_ref = db().collection("shots").document(shot_id)
    event_ref = db().collection(COLLECTION).document(event_id)
    now = datetime.now(UTC)

    @firestore.async_transactional
    async def write(transaction) -> Committed:
        snapshot = await shot_ref.get(transaction=transaction)
        current = snapshot.to_dict() or {} if snapshot.exists else {}
        found_rev = int(current.get("rev", 0) or 0)
        revisions.check(expected_rev, found_rev)

        previous = current.get("selected_clip_id") or fallback_previous
        transaction.set(
            shot_ref,
            {
                "project_id": project_id,
                "scene": scene,
                "shot": shot,
                "selected_clip_id": chosen,
                "previous_selected_clip_id": previous or "",
                "selection_reason": reason,
                "selection_by": actor,
                "selection_at": now,
                "selection_event_id": event_id,
                "selection_archive_state": "pending",
                "rev": found_rev + 1,
            },
            merge=True,
        )
        transaction.set(
            event_ref,
            {
                "event_id": event_id,
                "project_id": project_id,
                "scene": scene,
                "shot": shot,
                "chosen": chosen,
                "previous": previous or "",
                "reason": reason,
                "actor": actor,
                "rows": rows,
                "state": "pending",
                "created_at": now,
            },
        )
        return Committed(event_id, found_rev + 1, previous or None)

    return await write(db().transaction())


async def deliver(event_id: str) -> bool:
    """Idempotently deliver one event from the durable Firestore row.

    Returns True when ClickHouse has it, including when a previous attempt
    wrote it and crashed before marking the outbox row delivered.
    """
    if not event_id:
        return True

    event_ref = db().collection(COLLECTION).document(event_id)
    snapshot = await event_ref.get()
    if not snapshot.exists:
        return False
    event = snapshot.to_dict() or {}
    if event.get("state") == "delivered":
        return True

    project_id = int(event["project_id"])
    if event.get("kind") == "coverage_snapshot":
        if not await _coverage_already_recorded(project_id, event_id):
            await _record_coverage_event(event)
        await _mark_delivered(event_ref, event)
        return True

    if not await decisions.already_recorded(project_id, event_id):
        await decisions.record(
            project_id=project_id,
            group_id=int(event["scene"]),
            subgroup_id=int(event["shot"]),
            verdicts=list(event.get("rows") or []),
            key=event_id,
            model_id="",
            prompt_version="",
            decided_by="human",
            actor_id=str(event.get("actor") or ""),
        )

    delivered_at = datetime.now(UTC)
    await event_ref.set({"state": "delivered", "delivered_at": delivered_at}, merge=True)

    shot_ref = (
        db()
        .collection("shots")
        .document(f"p{project_id}_s{int(event['scene'])}_h{int(event['shot'])}")
    )
    current = await shot_ref.get()
    current_data = current.to_dict() or {} if current.exists else {}
    if current_data.get("selection_event_id") == event_id:
        await shot_ref.set({"selection_archive_state": "delivered"}, merge=True)
    return True


async def _coverage_already_recorded(project_id: int, event_id: str) -> bool:
    result = await (await client()).query(
        "SELECT count() FROM coverage_selection_events "
        "WHERE project_id = {p:UInt32} AND event_id = {e:String}",
        parameters={"p": project_id, "e": event_id},
    )
    return bool(result.result_rows and result.result_rows[0][0])


async def _record_coverage_event(event: dict) -> None:
    segments = list(event.get("segments") or [])
    occurred = event.get("created_at") or datetime.now(UTC)
    count = len(segments)
    source = segments or [
        {
            "segment_id": "00000000-0000-0000-0000-000000000000",
            "clip_id": "00000000-0000-0000-0000-000000000000",
            "source_in_s": 0,
            "source_out_s": 0,
            "take_no": 0,
            "position": 0,
        }
    ]
    rows = [
        [
            int(event["project_id"]),
            int(event["scene"]),
            int(event["shot"]),
            str(event["event_id"]),
            occurred,
            int(event.get("revision", 0) or 0),
            count,
            int(segment.get("position", index)),
            UUID(str(segment["segment_id"])),
            UUID(str(segment["clip_id"])),
            float(segment.get("source_in_s", 0)),
            float(segment.get("source_out_s", 0)),
            int(segment.get("take_no", 0) or 0),
            str(event.get("reason") or "")[:400],
            str(event.get("actor") or ""),
            str(segment.get("reason") or event.get("reason") or "")[:400],
            str(segment.get("origin") or "human")[:40],
            str(segment.get("created_by") or event.get("actor") or "")[:254],
        ]
        for index, segment in enumerate(source)
    ]
    await (await client()).insert(
        "coverage_selection_events",
        rows,
        column_names=[
            "project_id",
            "group_id",
            "subgroup_id",
            "event_id",
            "occurred_at",
            "revision",
            "segment_count",
            "position",
            "segment_id",
            "clip_id",
            "source_in_s",
            "source_out_s",
            "take_no",
            "reason",
            "actor_id",
            "segment_reason",
            "segment_origin",
            "segment_created_by",
        ],
    )


async def _mark_delivered(event_ref, event: dict) -> None:
    await event_ref.set({"state": "delivered", "delivered_at": datetime.now(UTC)}, merge=True)
    shot_ref = (
        db()
        .collection("shots")
        .document(f"p{int(event['project_id'])}_s{int(event['scene'])}_h{int(event['shot'])}")
    )
    current = await shot_ref.get()
    data = current.to_dict() or {} if current.exists else {}
    if data.get("selection_event_id") == event.get("event_id"):
        await shot_ref.set({"selection_archive_state": "delivered"}, merge=True)
