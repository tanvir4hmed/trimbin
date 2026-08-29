"""Housekeeping the system does to itself, on a schedule.

One route, called by Cloud Scheduler and nobody else. It is not public and not
part of the product; it is here rather than in a separate job because it needs
the same storage and database clients the API already holds, and a second
deployable to delete some rows would cost more to keep alive than it saves.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, status

from ..config import settings
from ..services import sandbox, storage
from ..services.analytics import client

log = logging.getLogger(__name__)
router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.post("/sandbox-retention")
async def sweep_sandbox(
    x_cloudscheduler: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    """Delete visitor footage past its keep-by date.

    A visitor's footage is theirs. Keeping it indefinitely because deleting is
    work would be the wrong default for material somebody uploaded to try a
    demo, and twenty-four hours is long enough to come back and look at it.

    Both the objects and the rows go. Leaving the rows would make the archive
    claim clips it cannot play; leaving the objects would mean paying to store
    footage nothing points at any more.

    Authorised by Cloud Run rather than here: the service allows only the
    scheduler's service account to invoke this path, which is checked before the
    container sees the request. The header below is a second, weaker signal used
    only to make an accidental call from a browser obvious in the logs.
    """
    if not (x_cloudscheduler or authorization):
        # Not a security boundary — see above. A human poking this by hand
        # should be told they are somewhere they did not mean to be.
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This route is called on a schedule, not by hand.",
        )

    expired = await sandbox.expired_clips()
    if not expired:
        return {"status": "nothing_to_do", "removed": 0}

    removed, failed = 0, 0
    for project_id, clip_id in expired:
        try:
            storage.delete_clip(project_id, clip_id)
            removed += 1
        except Exception:
            # One stubborn object must not stop the sweep. It will be picked up
            # on the next run, and the row is left alone so the two stay in step.
            log.exception("could not remove sandbox clip %s", clip_id)
            failed += 1

    if removed:
        ch = await client()
        await ch.command(
            """
            ALTER TABLE clips DELETE
            WHERE project_id = {p:UInt32}
              AND ingested_at < now() - INTERVAL {h:UInt16} HOUR
            """,
            parameters={
                "p": settings.sandbox_project_id,
                "h": settings.sandbox_retention_hours,
            },
        )
        await ch.command(
            """
            ALTER TABLE decisions DELETE
            WHERE project_id = {p:UInt32}
              AND decided_at < now() - INTERVAL {h:UInt16} HOUR
            """,
            parameters={
                "p": settings.sandbox_project_id,
                "h": settings.sandbox_retention_hours,
            },
        )

    log.info("sandbox sweep: %d removed, %d could not be", removed, failed)
    return {"status": "swept", "removed": removed, "failed": failed}
