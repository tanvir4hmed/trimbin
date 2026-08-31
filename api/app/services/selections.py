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
from uuid import uuid4

from google.cloud import firestore

from . import decisions, revisions
from .jobs import db

log = logging.getLogger(__name__)

COLLECTION = "selection_events"


@dataclass(frozen=True)
class Committed:
    event_id: str
    rev: int
    previous: str | None


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
