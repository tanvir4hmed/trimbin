"""Optimistic concurrency, and replayed commands.

Two editors open shot 12B. One assigns it to themselves; the other, looking at
the page as it was thirty seconds ago, marks it approved. Both writes succeed
and the second silently discards the first — no error, no record, and the only
evidence is that somebody's change is gone.

Firestore's `set(merge=True)` is what made that possible: it is a blind write. It
does not know what the caller was looking at, so it cannot tell an edit from an
overwrite.

A revision fixes it without locks. Every mutable document carries `rev`. A
command sends the rev it was shown; the write happens in a transaction that
compares, increments and stores in one step. A mismatch is a 409 carrying the
current state, so the interface can say what changed rather than "try again".

The second half is idempotency, which is a different problem with a similar
shape. A browser retries a POST it never saw the answer to — a dropped
connection, a closed laptop — and a second identical override lands in the
archive. The rev does not catch it, because the first write moved the rev and
the retry carries the old one, so the retry looks exactly like a conflict when
it is not. So a command may carry a key, and a replay of that key returns the
first answer instead of doing the work again.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from google.cloud import firestore

from .jobs import db

log = logging.getLogger(__name__)

COLLECTION = "commands"

# How long a replayed key still returns its first answer.
#
# Long enough to cover a retry a person actually makes — a refresh, a flaky
# connection, a phone waking up — and short enough that the collection does not
# become a second archive. Beyond this a repeat is treated as a new command,
# which is the correct default: somebody pressing the same button an hour later
# means it.
REPLAY_WINDOW = timedelta(hours=6)


class Conflict(HTTPException):
    """Somebody else changed this while you were looking at it.

    409 rather than 412, and carrying the current state rather than only saying
    no. An interface that is told "conflict" can offer nothing but a reload; one
    that is handed the current value can say what changed and who changed it.
    """

    def __init__(self, expected: int, found: int, current: Any = None) -> None:
        super().__init__(
            status.HTTP_409_CONFLICT,
            {
                "detail": ("Somebody else changed this while you were looking at it."),
                "expected_rev": expected,
                "current_rev": found,
                "current": current,
            },
        )


@dataclass(frozen=True)
class Written:
    rev: int
    replayed: bool = False


def check(expected: int | None, found: int) -> None:
    """Refuse a write built on a version that is no longer current.

    `None` means the caller did not say, which is accepted. Requiring it
    everywhere would break the first request after a deploy for every client
    that had not reloaded, and the cost of that is worse than the race it
    prevents on endpoints nobody edits concurrently.

    Zero is a real revision: a document nobody has written yet.
    """
    if expected is None:
        return
    if expected != found:
        raise Conflict(expected, found)


async def bump(
    collection: str,
    doc_id: str,
    fields: dict,
    expected: int | None = None,
) -> Written:
    """Merge fields into a document, checking and incrementing its revision.

    One transaction, not a read then a write. Between a read and a write another
    request fits, and the whole point of this function is the moment between
    those two.
    """
    ref = db().collection(collection).document(doc_id)

    @firestore.async_transactional
    async def write(transaction) -> int:
        snapshot = await ref.get(transaction=transaction)
        current = (snapshot.to_dict() or {}).get("rev", 0) if snapshot.exists else 0

        if expected is not None and expected != current:
            raise Conflict(expected, current, snapshot.to_dict() if snapshot.exists else None)

        transaction.set(ref, {**fields, "rev": current + 1}, merge=True)
        return current + 1

    return Written(rev=await write(db().transaction()))


async def replay(key: str, actor: str) -> dict | None:
    """The answer this command already gave, if it has been seen.

    Keyed on the command and the person, so two editors pressing the same button
    are two commands. A key alone would make the second one silently receive the
    first one's answer, which is a worse bug than the duplicate it prevents.
    """
    if not key:
        return None

    snapshot = await db().collection(COLLECTION).document(_id(key, actor)).get()
    if not snapshot.exists:
        return None

    d = snapshot.to_dict() or {}
    written = d.get("at")
    if written and datetime.now(UTC) - written > REPLAY_WINDOW:
        return None

    log.info("replayed command %s for %s", key[:12], actor)
    return d.get("result")


async def remember(key: str, actor: str, result: dict) -> None:
    """Keep a command's answer so a retry returns it rather than repeating it."""
    if not key:
        return
    await (
        db()
        .collection(COLLECTION)
        .document(_id(key, actor))
        .set(
            {
                "key": key,
                "actor": actor,
                "result": result,
                "at": datetime.now(UTC),
                # So the collection can be swept. One document per command is small,
                # and small compounds.
                "expires_at": datetime.now(UTC) + REPLAY_WINDOW,
            }
        )
    )


def _id(key: str, actor: str) -> str:
    safe_key = "".join(c for c in key if c.isalnum() or c in "-_")[:80]
    safe_actor = "".join(c for c in actor if c.isalnum() or c in "-_@.")[:80]
    return f"{safe_actor}:{safe_key}".replace("/", "_")
