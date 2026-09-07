"""Transactional dispatch and worker leases for independent media analysis."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from google.cloud import firestore

LEASE = timedelta(minutes=15)
ACTIVE = {"pending", "queued", "processing"}


def active(data: dict, now: datetime) -> bool:
    until = data.get("lease_until")
    if not isinstance(until, datetime):
        updated = data.get("updated_at")
        until = updated + LEASE if isinstance(updated, datetime) else now
    return data.get("state") in ACTIVE and until > now


async def reserve(client, ref, attributes: dict) -> bool:
    @firestore.async_transactional
    async def command(transaction):
        data = (await ref.get(transaction=transaction)).to_dict() or {}
        now = datetime.now(UTC)
        if active(data, now):
            return False
        transaction.set(
            ref,
            {
                **attributes,
                "state": "pending",
                "updated_at": now,
                "lease_until": now + LEASE,
                "error": "",
                "worker_id": "",
            },
        )
        return True

    return await command(client.transaction())


async def published(client, ref, dispatch_id: str, *, message_id: str = "", error: str = ""):
    @firestore.async_transactional
    async def command(transaction):
        data = (await ref.get(transaction=transaction)).to_dict() or {}
        # A fast worker may already have finished before publish() returns.
        if data.get("dispatch_id") != dispatch_id or data.get("state") != "pending":
            return
        transaction.update(
            ref,
            {
                "state": "publish_failed" if error else "queued",
                "message_id": message_id,
                "error": error[:500],
                "updated_at": datetime.now(UTC),
            },
        )

    await command(client.transaction())


async def claim(client, ref, dispatch_id: str) -> tuple[str, str]:
    """Return claimed/busy/obsolete and a unique, fenced execution token."""
    worker_id = str(uuid4())

    @firestore.async_transactional
    async def command(transaction):
        data = (await ref.get(transaction=transaction)).to_dict() or {}
        now = datetime.now(UTC)
        if data.get("dispatch_id", "") != dispatch_id or data.get("state") == "completed":
            return "obsolete", ""
        if data.get("state") == "processing" and active(data, now):
            return "busy", ""
        transaction.set(
            ref,
            {
                "dispatch_id": dispatch_id,
                "worker_id": worker_id,
                "state": "processing",
                "updated_at": now,
                "lease_until": now + LEASE,
                "error": "",
            },
            merge=True,
        )
        return "claimed", worker_id

    return await command(client.transaction())


async def advance(
    client, ref, dispatch_id: str, worker_id: str, state: str, error: str = ""
) -> bool:
    @firestore.async_transactional
    async def command(transaction):
        data = (await ref.get(transaction=transaction)).to_dict() or {}
        if (
            data.get("dispatch_id", "") != dispatch_id
            or data.get("worker_id") != worker_id
            or data.get("state") != "processing"
        ):
            return False
        now = datetime.now(UTC)
        transaction.update(
            ref,
            {
                "state": state,
                "error": error[:500],
                "updated_at": now,
                "lease_until": now + LEASE if state == "processing" else now,
            },
        )
        return True

    return await command(client.transaction())
