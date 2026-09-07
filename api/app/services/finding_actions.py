"""Revision-safe human finding actions with durable ClickHouse delivery."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from google.cloud import firestore

from . import analysis_store, revisions
from .jobs import db

log = logging.getLogger(__name__)

STATE_COLLECTION = "finding_states"
DELIVERY_COLLECTION = "finding_event_deliveries"


@dataclass(frozen=True, slots=True)
class Committed:
    event_id: UUID
    finding_id: UUID
    rev: int
    action: str
    replayed: bool = False


def command_ref(project_id: int, clip_id: UUID, finding_id: UUID, actor: str, key: str):
    identity = f"{project_id}/{clip_id}/{finding_id}/{actor}/{key}"
    return (
        db().collection("finding_commands").document(hashlib.sha256(identity.encode()).hexdigest())
    )


def receipt_result(data: dict, request: dict) -> Committed:
    if data.get("request") != request:
        raise HTTPException(
            409, "This command key was already used for a different finding action."
        )
    result = data["result"]
    return Committed(
        UUID(result["event_id"]), UUID(result["finding_id"]), result["rev"], result["action"], True
    )


async def replay(
    project_id: int, clip_id: UUID, finding_id: UUID, actor: str, key: str, request: dict
):
    snapshot = await command_ref(project_id, clip_id, finding_id, actor, key).get()
    return receipt_result(snapshot.to_dict() or {}, request) if snapshot.exists else None


def _as_text(value) -> str:
    return str(value) if value is not None else ""


async def commit(
    *,
    project_id: int,
    clip_id: UUID,
    current: dict,
    action: str,
    expected_rev: int,
    actor: str,
    actor_role: str,
    changes: dict,
    command_key: str = "",
    request: dict | None = None,
) -> Committed:
    """Commit current operational state and its archive event atomically."""
    finding_id = UUID(_as_text(current["finding_id"]))
    fallback_rev = int(current.get("revision", 0))
    state_ref = db().collection(STATE_COLLECTION).document(str(finding_id))
    event_id = uuid4()
    delivery_ref = db().collection(DELIVERY_COLLECTION).document(str(event_id))
    now = datetime.now(UTC)
    receipt = (
        command_ref(project_id, clip_id, finding_id, actor, command_key) if command_key else None
    )

    @firestore.async_transactional
    async def write(transaction) -> Committed:
        if receipt:
            previous = await receipt.get(transaction=transaction)
            if previous.exists:
                return receipt_result(previous.to_dict() or {}, request or {})
        snapshot = await state_ref.get(transaction=transaction)
        prior = snapshot.to_dict() or {} if snapshot.exists else {}
        found_rev = int(prior.get("rev", fallback_rev))
        revisions.check(expected_rev, found_rev)

        def value(name: str, default=None):
            if name in changes and changes[name] is not None:
                return changes[name]
            if name in prior:
                return prior[name]
            return current.get(name, default)

        next_rev = found_rev + 1
        payload = {
            "event_id": str(event_id),
            "finding_id": str(finding_id),
            "run_id": _as_text(value("run_id")),
            "project_id": project_id,
            "clip_id": str(clip_id),
            "revision": next_rev,
            "action": action,
            "code": _as_text(value("code")),
            "detail": _as_text(value("detail")),
            "severity": _as_text(value("severity", "attention")) or "attention",
            "start_s": float(value("start_s", 0.0)),
            "end_s": float(value("end_s", 0.0)),
            "evidence_segment_ids": [_as_text(item) for item in value("evidence_segment_ids", [])],
            "sources": [_as_text(item) for item in value("sources", [])],
            "supersedes_event_id": _as_text(value("event_id")),
            "actor_id": actor,
            "actor_role": actor_role,
            "model_id": "",
            "prompt_version": "",
            "occurred_at": now,
            "retracts_event_id": _as_text(changes.get("retracts_event_id")) or None,
            "restored_action": _as_text(changes.get("restored_action")),
        }
        transaction.set(
            state_ref,
            {
                **payload,
                "clip_key": f"{project_id}/{clip_id}",
                "rev": next_rev,
                "archive_state": "pending",
            },
        )
        transaction.set(
            delivery_ref,
            {**payload, "state": "pending", "created_at": now},
        )
        if receipt:
            transaction.set(
                receipt,
                {
                    "request": request or {},
                    "created_at": now,
                    "result": {
                        "event_id": str(event_id),
                        "finding_id": str(finding_id),
                        "rev": next_rev,
                        "action": action,
                    },
                },
            )
        return Committed(event_id, finding_id, next_rev, action)

    return await write(db().transaction())


async def deliver(event_id: UUID) -> bool:
    ref = db().collection(DELIVERY_COLLECTION).document(str(event_id))
    snapshot = await ref.get()
    if not snapshot.exists:
        return False
    event = snapshot.to_dict() or {}
    if event.get("state") == "delivered":
        return True

    project_id = int(event["project_id"])
    if not await analysis_store.finding_event_exists(project_id, event_id):
        await analysis_store.record_finding_events(
            [
                {
                    **event,
                    "event_id": event_id,
                    "finding_id": UUID(event["finding_id"]),
                    "run_id": UUID(event["run_id"]) if event.get("run_id") else None,
                    "clip_id": UUID(event["clip_id"]),
                    "evidence_segment_ids": [
                        UUID(item) for item in event.get("evidence_segment_ids", [])
                    ],
                    "sources": list(event.get("sources", [])),
                    "supersedes_event_id": (
                        UUID(event["supersedes_event_id"])
                        if event.get("supersedes_event_id")
                        else None
                    ),
                    "retracts_event_id": (
                        UUID(event["retracts_event_id"]) if event.get("retracts_event_id") else None
                    ),
                }
            ]
        )

    delivered_at = datetime.now(UTC)
    await ref.set({"state": "delivered", "delivered_at": delivered_at}, merge=True)
    state_ref = db().collection(STATE_COLLECTION).document(event["finding_id"])
    state_snapshot = await state_ref.get()
    current = state_snapshot.to_dict() or {} if state_snapshot.exists else {}
    if current.get("event_id") == str(event_id):
        await state_ref.set({"archive_state": "delivered"}, merge=True)
    return True


async def states_for_clip(project_id: int, clip_id: UUID) -> list[dict]:
    found = []
    stream = (
        db()
        .collection(STATE_COLLECTION)
        .where("clip_key", "==", f"{project_id}/{clip_id}")
        .stream()
    )
    async for snapshot in stream:
        row = snapshot.to_dict() or {}
        row["finding_id"] = row.get("finding_id") or snapshot.id
        found.append(row)
    return found


async def pending_history(project_id: int, finding_id: UUID) -> list[dict]:
    """Read durable events even when archive delivery is delayed."""
    rows = []
    async for snapshot in (
        db().collection(DELIVERY_COLLECTION).where("finding_id", "==", str(finding_id)).stream()
    ):
        row = snapshot.to_dict() or {}
        if int(row.get("project_id", 0)) == project_id:
            rows.append(row)
    return rows


def overlay(archive: dict, operational: list[dict]) -> dict:
    """Overlay undelivered Firestore truth on the ClickHouse read model."""
    if not operational:
        return archive

    current = {str(row["finding_id"]): dict(row) for row in archive.get("findings", [])}
    history = list(archive.get("history", []))
    history_events = {str(row.get("event_id", "")) for row in history}

    for row in operational:
        finding_id = str(row["finding_id"])
        event_id = str(row.get("event_id", ""))
        current_run = str((archive.get("run") or {}).get("run_id", ""))
        same_run = not current_run or str(row.get("run_id", "")) == current_run
        effective_action = (
            row.get("restored_action")
            if row.get("action") == "human_retracted"
            else row.get("action")
        )
        if same_run and effective_action == "human_dismissed":
            current.pop(finding_id, None)
        elif same_run:
            current[finding_id] = {
                **row,
                "revision": int(row.get("rev", row.get("revision", 0))),
                "action": effective_action,
            }
        if event_id and event_id not in history_events:
            history.append(
                {
                    **row,
                    "revision": int(row.get("rev", row.get("revision", 0))),
                }
            )

    return {
        **archive,
        "findings": sorted(
            current.values(),
            key=lambda row: (float(row["start_s"]), str(row["finding_id"])),
        ),
        "history": sorted(
            history,
            key=lambda row: (
                str(row.get("finding_id", "")),
                int(row.get("revision", 0)),
                str(row.get("occurred_at", "")),
            ),
        ),
    }
