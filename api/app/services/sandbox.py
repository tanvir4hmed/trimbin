"""The rules that let a stranger use this without it becoming a way to spend us.

A visitor with no account can upload their own footage and watch the pipeline
run on it. That is the strongest thing this project can show someone in three
minutes, and it is also an open door to a paid model and a video encoder.

So the limits are deliberately tight and deliberately several. Any one of them
alone is easy to walk around: a byte cap does not stop a hundred small files, a
file count does not stop a hundred requests, and an IP quota does not stop one
enormous clip. Together they bound the cost of a visit without needing to
identify anybody.

Nothing here is a security control. An IP is not a person and a determined
visitor can find another one; this is a cost ceiling, and treating it as
authentication would be a mistake. Anything that must not be abused is behind
sign-in instead.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, Request, status
from google.cloud import firestore

from ..config import settings
from .jobs import db

log = logging.getLogger(__name__)

COLLECTION = "sandbox_quota"

# What a signed URL for the sandbox will accept. Small enough that thirty
# seconds of phone video fits comfortably and a feature does not.
MAX_SANDBOX_BYTES = 200 * 1024 * 1024


def is_sandbox(project_id: int) -> bool:
    return project_id == settings.sandbox_project_id


def caller_ip(request: Request) -> str:
    """The visitor's address, as far as it can be known.

    Behind Cloud Run and a load balancer the socket peer is Google's
    infrastructure, so the client is the first entry in X-Forwarded-For. That
    header is client-settable on a direct connection — which is why this is a
    cost ceiling and not a security control.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _doc(ip: str, day: date):
    # One document per address per day, so yesterday's use never counts against
    # today and nothing has to be swept.
    return db().collection(COLLECTION).document(f"{day.isoformat()}/{ip}".replace("/", "_"))


async def check_and_count(request: Request, clips: int) -> None:
    """Refuse a visitor who has already had their turn today.

    Counted in a transaction. Two tabs opened at once would otherwise both read
    the old total, both decide there was room, and both proceed — which is
    exactly how a limit gets doubled by someone who was not even trying.

    Raises before anything is queued, because the point is not to spend the
    money and then complain.
    """
    if clips > settings.sandbox_max_clips:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"The sandbox takes up to {settings.sandbox_max_clips} clips at a time. "
            f"Sign in to work on a real project without limits.",
        )

    ip = caller_ip(request)
    ref = _doc(ip, datetime.now(UTC).date())
    allowance = settings.sandbox_max_per_ip_per_day

    @firestore.async_transactional
    async def count(transaction) -> int:
        snapshot = await ref.get(transaction=transaction)
        used = (snapshot.to_dict() or {}).get("clips", 0) if snapshot.exists else 0

        if used + clips > allowance:
            return used

        transaction.set(
            ref,
            {
                "clips": used + clips,
                "last_seen": datetime.now(UTC),
                # Kept so the collection can be swept if it ever grows; one doc
                # per visitor per day is small, but "small" compounds.
                "expires_at": datetime.now(UTC) + timedelta(days=2),
            },
        )
        return used + clips

    total = await count(db().transaction())

    if total > allowance or total == 0 and clips > 0:
        log.info("sandbox quota reached for %s", ip)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"The sandbox allows {allowance} clips a day from one address, and "
            f"you have used them. It resets at midnight UTC. Signing in removes "
            f"the limit.",
        )


def clip_is_too_long(duration_s: float) -> bool:
    """Enforced after measurement, because length cannot be known before it.

    A byte cap on the signed URL bounds what can arrive; only ffmpeg can say
    whether what arrived is thirty seconds or three minutes at a low bitrate.
    The clip is rejected with a reason rather than dropped, so the visitor sees
    the limit rather than a gap.
    """
    return duration_s > settings.sandbox_max_seconds


async def expired_clips(hours: int | None = None) -> list[tuple[int, str]]:
    """Sandbox clips past their keep-by date.

    A visitor's footage is theirs. Keeping it indefinitely because deleting is
    work would be the wrong default for material somebody uploaded to try a
    demo, and twenty-four hours is long enough to come back and look.
    """
    from .analytics import client

    limit = hours if hours is not None else settings.sandbox_retention_hours
    ch = await client()
    result = await ch.query(
        """
        SELECT project_id, toString(clip_id)
        FROM clips
        WHERE project_id = {p:UInt32}
          AND ingested_at < now() - INTERVAL {h:UInt16} HOUR
        """,
        parameters={"p": settings.sandbox_project_id, "h": limit},
    )
    return [(int(r[0]), str(r[1])) for r in result.result_rows]
