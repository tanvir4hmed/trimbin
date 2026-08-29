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
from ..services import sandbox, storage
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


@router.post("/sandbox-retention")
async def sweep_sandbox(
    authorization: str | None = Header(default=None),
) -> dict:
    """Delete visitor footage past its keep-by date.

    A visitor's footage is theirs. Keeping it indefinitely because deleting is
    work would be the wrong default for material somebody uploaded to try a
    demo, and twenty-four hours is long enough to come back and look at it.

    Both the objects and the rows go. Leaving the rows would make the archive
    claim clips it cannot play; leaving the objects would mean paying to store
    footage nothing points at any more.
    """
    if not _is_the_scheduler(authorization):
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
