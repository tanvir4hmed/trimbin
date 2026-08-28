"""Upload: the browser talks to storage directly, never through us.

Video never passes through this API. The browser asks for a signed URL, uploads
to Cloud Storage itself, and tells us when it is done. Proxying gigabytes through
Cloud Run would cost twice — once in ingress, once in egress — and would make the
service scale with footage volume rather than with request count.

The interaction is deliberately shallow. An editor drops a folder and leaves;
there is no form to fill, no per-file naming, and nothing to come back to except
the result.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ..auth import Principal, require_member
from ..services import jobs, storage

log = logging.getLogger(__name__)
router = APIRouter(prefix="/uploads", tags=["uploads"])

# Extensions a camera actually produces. Anything else is a mistake worth
# catching at the door rather than after an upload completes — the person who
# dragged a folder containing a PDF should know immediately.
ACCEPTED_SUFFIXES = frozenset({".mov", ".mp4", ".mxf", ".m4v", ".avi", ".mkv", ".braw", ".r3d"})

MAX_CLIP_BYTES = 8 * 1024**3  # 8 GiB: a long take at high bitrate, with room
SIGNED_URL_TTL = timedelta(hours=6)  # long enough for a slow connection

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


class UploadRequest(BaseModel):
    project_id: int
    filenames: list[str] = Field(min_length=1, max_length=500)

    @field_validator("filenames")
    @classmethod
    def _check_extensions(cls, names: list[str]) -> list[str]:
        rejected = [
            n for n in names
            if not any(n.lower().endswith(s) for s in ACCEPTED_SUFFIXES)
        ]
        if rejected:
            shown = ", ".join(rejected[:5])
            more = f" and {len(rejected) - 5} more" if len(rejected) > 5 else ""
            raise ValueError(f"These are not video files: {shown}{more}")
        return names


class UploadTicket(BaseModel):
    clip_id: UUID
    filename: str
    upload_url: str
    storage_uri: str


class UploadGrant(BaseModel):
    job_id: UUID
    tickets: list[UploadTicket]
    expires_in_s: int


class UploadComplete(BaseModel):
    job_id: UUID
    clip_ids: list[UUID]


@router.post("/grant", response_model=UploadGrant)
async def grant_upload(
    request: UploadRequest,
    principal: Annotated[Principal, Depends(require_member)],
) -> UploadGrant:
    """Hand back one signed URL per file, and open a job to track the batch.

    The job exists before a single byte moves, because the editor is going to
    close the tab. Without something durable to come back to, a long ingest is
    indistinguishable from one that silently died.
    """
    await principal.assert_can_write(request.project_id)

    job_id = await jobs.open_job(
        project_id=request.project_id,
        kind="ingest",
        total_items=len(request.filenames),
        opened_by=principal.email,
    )

    tickets: list[UploadTicket] = []
    for filename in request.filenames:
        clip_id = uuid4()
        # The stored name comes from us, not from the browser: a filename is
        # attacker-controlled input, and object paths are not the place to find
        # out what someone typed.
        safe = _SAFE_NAME.sub("_", filename)[-120:]
        object_path = f"p{request.project_id}/{clip_id}/{safe}"

        tickets.append(
            UploadTicket(
                clip_id=clip_id,
                filename=filename,
                upload_url=await storage.signed_upload_url(
                    object_path,
                    ttl=SIGNED_URL_TTL,
                    max_bytes=MAX_CLIP_BYTES,
                ),
                storage_uri=storage.originals_uri(object_path),
            )
        )

    log.info("granted %d upload URLs for project %d", len(tickets), request.project_id)
    return UploadGrant(
        job_id=job_id,
        tickets=tickets,
        expires_in_s=int(SIGNED_URL_TTL.total_seconds()),
    )


@router.post("/complete", status_code=status.HTTP_202_ACCEPTED)
async def complete_upload(
    body: UploadComplete,
    principal: Annotated[Principal, Depends(require_member)],
) -> dict[str, str]:
    """Queue the clips that actually arrived.

    The browser reports which uploads succeeded. It is not trusted: each object
    is confirmed present in storage before anything is queued, because a client
    that crashed mid-upload will happily claim otherwise, and a queued job for a
    file that does not exist fails five times and lands in the dead letter queue
    for no reason.
    """
    job = await jobs.get_job(body.job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such job")
    await principal.assert_can_write(job.project_id)

    confirmed, missing = await storage.confirm_uploads(job.project_id, body.clip_ids)

    if missing:
        log.warning("%d clips reported but not found in storage", len(missing))
        await jobs.record_missing(body.job_id, missing)

    # The total is corrected before the work is queued, not after. A worker on a
    # short clip can finish and close the job in the time it takes to make one
    # more Firestore call, and a set_total arriving afterwards would reopen a
    # job that had already finished.
    await jobs.set_total(body.job_id, len(confirmed) + len(missing))

    if not confirmed:
        # Nothing arrived. No worker will run, so nothing else will ever mark
        # this finished.
        await jobs.close_empty(body.job_id)
    else:
        await jobs.enqueue_ingest(
            job_id=body.job_id, project_id=job.project_id, clip_ids=confirmed
        )

    return {
        "status": "queued",
        "queued": str(len(confirmed)),
        "missing": str(len(missing)),
    }


@router.get("/jobs/{job_id}")
async def job_status(
    job_id: UUID,
    principal: Annotated[Principal, Depends(require_member)],
) -> dict:
    """Progress for an editor who walked away and came back.

    Failures are reported alongside progress rather than hidden. Four clips that
    could not be processed is information; a batch that quietly reports success
    while missing four clips is a bug the editor discovers weeks later in the
    edit, which is the worst possible time.
    """
    job = await jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such job")
    await principal.assert_can_read(job.project_id)

    return {
        "job_id": str(job.job_id),
        "state": job.state,
        "total": job.total_items,
        "completed": job.completed_items,
        "failed": job.failed_items,
        "failures": job.failures[:20],
        "started_at": job.started_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
