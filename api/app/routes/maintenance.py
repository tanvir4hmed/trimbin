"""Housekeeping the system does to itself, on a schedule.

One route, called by Cloud Scheduler and nobody else. It is not public and not
part of the product; it is here rather than in a separate job because it needs
the same storage and database clients the API already holds, and a second
deployable to delete some rows would cost more to keep alive than it saves.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from ..config import settings
from ..services import members, quota, storage
from ..services.analytics import client

log = logging.getLogger(__name__)
router = APIRouter(prefix="/maintenance", tags=["maintenance"])

_request_adapter = google_requests.Request()


def _is_the_scheduler(authorization: str | None) -> bool:
    """Whether this request really came from our Cloud Scheduler job.

    Checked here, not by Cloud Run, and the difference is the point. The API
    service carries an allUsers invoker binding because the public pages need
    one — so Cloud Run lets everybody through and enforces nothing on this path.

    An earlier version of this route said the opposite in a comment and accepted
    any request carrying any Authorization header. That is not a check; it is a
    check-shaped thing, and the comment made it look deliberate.

    So the token is verified properly: signature, issuer, audience, and then
    that the email inside it is the scheduler's own service account. Anything
    less accepts a token minted for something else entirely.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return False

    expected = settings.scheduler_service_account.lower()
    if not expected:
        # Nothing to compare against. Refuse rather than guess: a maintenance
        # route that runs for whoever asks is worse than one that never runs.
        log.error("TRIMBIN_SCHEDULER_SERVICE_ACCOUNT is unset; refusing.")
        return False

    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = id_token.verify_oauth2_token(
            token, _request_adapter, audience=settings.scheduler_audience or None
        )
    except ValueError as exc:
        log.warning("rejected a maintenance token: %s", exc)
        return False

    caller = (claims.get("email") or "").lower()
    if caller != expected:
        log.warning("maintenance called by %s, which is not the scheduler", caller)
        return False

    return True


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
