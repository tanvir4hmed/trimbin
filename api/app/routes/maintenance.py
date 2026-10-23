"""Explicit maintenance protected by a private service token. No automatic deletion is enabled."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, status

from ..config import settings
from ..services import members, quota, storage
from ..services.analytics import client

log = logging.getLogger(__name__)
router = APIRouter(prefix="/maintenance", tags=["maintenance"])


def _is_the_scheduler(authorization: str | None) -> bool:
    import hmac

    expected = settings.maintenance_token
    return bool(
        expected and authorization and hmac.compare_digest(authorization, "Bearer " + expected)
    )


@router.post("/guest-retention")
async def sweep_guest_projects(
    authorization: str | None = Header(default=None),
) -> dict:
    """Delete guest footage past its keep-by date.

    A visitor's footage is theirs. Keeping it forever because deleting is work
    would be the wrong default for material somebody uploaded to try something,
    and a week is long enough to come back, show a colleague, and come back
    again.

    Which projects are a guest's is read from who owns them, never from an id
    range. A range would be a rule invisible in the data, and the first time
    somebody joined the company their existing projects would quietly start
    being deleted.

    Both the objects and the rows go. Leaving the rows would make the archive
    claim clips it cannot play; leaving the objects would mean paying to store
    footage nothing points at any more.

    The route kept its old name for a while and its old path was
    /sandbox-retention. Renaming it needs the Cloud Scheduler job renamed in the
    same change — Terraform owns that, so the two move together.
    """
    if not _is_the_scheduler(authorization):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This route is called on a schedule, not by hand.",
        )

    expired = await quota.expired_clips()
    if not expired:
        # Logged, not silent. "The sweep ran and found nothing" and "the sweep
        # never ran" produce the same empty log otherwise, which is exactly the
        # silence that lets a broken schedule sit unnoticed for weeks.
        log.info("guest sweep: nothing past its keep-by date")
        return {"status": "nothing_to_do", "removed": 0}

    removed, failed = 0, 0
    swept_projects: set[int] = set()
    for project_id, clip_id in expired:
        try:
            storage.delete_clip(project_id, clip_id)
            removed += 1
            swept_projects.add(project_id)
        except Exception:
            # One stubborn object must not stop the sweep. It will be picked up
            # on the next run, and the row is left alone so the two stay in step.
            log.exception("could not remove guest clip %s", clip_id)
            failed += 1

    if swept_projects:
        days = members.GUEST_LIMITS.retention_days
        ch = await client()
        await ch.command(
            """
            ALTER TABLE clips DELETE
            WHERE project_id IN {ids:Array(UInt32)}
              AND ingested_at < now() - INTERVAL {d:UInt16} DAY
            """,
            parameters={"ids": sorted(swept_projects), "d": days},
        )
        await ch.command(
            """
            ALTER TABLE decisions DELETE
            WHERE project_id IN {ids:Array(UInt32)}
              AND decided_at < now() - INTERVAL {d:UInt16} DAY
            """,
            parameters={"ids": sorted(swept_projects), "d": days},
        )
        await ch.command(
            """
            ALTER TABLE comments DELETE
            WHERE project_id IN {ids:Array(UInt32)}
              AND created_at < now() - INTERVAL {d:UInt16} DAY
            """,
            parameters={"ids": sorted(swept_projects), "d": days},
        )

    log.info("guest sweep: %d removed, %d could not be", removed, failed)
    return {"status": "swept", "removed": removed, "failed": failed}
