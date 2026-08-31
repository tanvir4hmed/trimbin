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

from ..auth import Principal, current_principal, require_signed_in
from ..services import activity, jobs, members, quota, storage

log = logging.getLogger(__name__)
router = APIRouter(prefix="/uploads", tags=["uploads"])

# Extensions a camera actually produces. Anything else is a mistake worth
# catching at the door rather than after an upload completes — the person who
# dragged a folder containing a PDF should know immediately.
ACCEPTED_SUFFIXES = frozenset({".mov", ".mp4", ".mxf", ".m4v", ".avi", ".mkv", ".braw", ".r3d"})

SIGNED_URL_TTL = timedelta(hours=6)  # long enough for a slow connection

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


class UploadRequest(BaseModel):
    project_id: int
    filenames: list[str] = Field(min_length=1, max_length=500)
    # Where this footage belongs, if the uploader says. Absent means read the
    # slates and group by what they say.
    scene: int = Field(default=0, ge=0)
    shot: int = Field(default=0, ge=0)

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
    # Part of the signature, not advice. Cloud Storage refuses a PUT that omits
    # a signed header and does not say which one is missing.
    headers: dict[str, str]


class UploadGrant(BaseModel):
    job_id: UUID
    tickets: list[UploadTicket]
    expires_in_s: int


class UploadComplete(BaseModel):
    job_id: UUID
    clip_ids: list[UUID]
    # So the upload screen can name a file rather than a uuid when something
    # goes wrong with it.
    filenames_by_clip: dict[str, str] | None = None


@router.post("/grant", response_model=UploadGrant)
async def grant_upload(
    request: UploadRequest,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> UploadGrant:
    """Hand back one signed URL per file, and open a job to track the batch.

    The job exists before a single byte moves, because the editor is going to
    close the tab. Without something durable to come back to, a long ingest is
    indistinguishable from one that silently died.

    Uploading is the one thing a guest cannot do in our productions. Not for
    lack of trust — they may overrule any call we made — but because footage
    costs storage, encoding and model time, and none of those are free. In their
    own project they upload like anybody else.
    """
    await principal.assert_can_upload(request.project_id)

    # Checked before the job is opened, so a refused upload leaves nothing
    # behind to clean up.
    await quota.check_room_for(request.project_id, len(request.filenames))
    max_bytes = await quota.max_bytes_for(request.project_id)

    job_id = await jobs.open_job(
        project_id=request.project_id,
        kind="ingest",
        total_items=len(request.filenames),
        opened_by=principal.email or "",
        target_scene=request.scene,
        target_shot=request.shot,
    )

    # The job exists now, so a failure from here on has to close it. Otherwise
    # the editor is handed an error while a job sits in "uploading" forever,
    # waiting for files that were never granted a URL to arrive with.
    try:
        tickets: list[UploadTicket] = []
        for filename in request.filenames:
            clip_id = uuid4()
            # The stored name comes from us, not from the browser: a filename is
            # attacker-controlled input, and object paths are not the place to
            # find out what someone typed.
            safe = _SAFE_NAME.sub("_", filename)[-120:]
            object_path = f"p{request.project_id}/{clip_id}/{safe}"

            url, headers = await storage.signed_upload_url(
                object_path,
                ttl=SIGNED_URL_TTL,
                # A byte cap is the only limit enforceable before anything
                # arrives. Length is checked after measurement, because only
                # ffmpeg can tell sixty seconds from six minutes at a low
                # bitrate. Which cap applies follows the project's owner, not
                # the person uploading — otherwise a guest could raise their own
                # limit by inviting an editor.
                max_bytes=max_bytes,
            )

            tickets.append(
                UploadTicket(
                    clip_id=clip_id,
                    filename=filename,
                    upload_url=url,
                    headers=headers,
                    storage_uri=storage.originals_uri(object_path),
                )
            )
    except Exception:
        log.exception("could not issue upload URLs for job %s", job_id)
        await jobs.abandon(job_id, "could not issue upload URLs")
        raise

    log.info("granted %d upload URLs for project %d", len(tickets), request.project_id)
    return UploadGrant(
        job_id=job_id,
        tickets=tickets,
        expires_in_s=int(SIGNED_URL_TTL.total_seconds()),
    )


@router.post("/complete", status_code=status.HTTP_202_ACCEPTED)
async def complete_upload(
    body: UploadComplete,
    principal: Annotated[Principal, Depends(current_principal)],
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
    await principal.assert_can_upload(job.project_id)

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
            job_id=body.job_id,
            project_id=job.project_id,
            clip_ids=confirmed,
            filenames=body.filenames_by_clip or {},
            target_scene=job.target_scene,
            target_shot=job.target_shot,
        )

    await activity.record(
        job.project_id, principal.email or "", "uploaded",
        detail=(
            f"scene {job.target_scene} shot {job.target_shot}"
            if job.target_scene
            else "slates decide"
        ),
        scene=job.target_scene, shot=job.target_shot,
        quantity=len(confirmed),
        actor_role=members.role_of(principal.email),
    )

    return {
        "status": "queued",
        "queued": str(len(confirmed)),
        "missing": str(len(missing)),
    }


@router.get("/jobs/{job_id}")
async def job_status(
    job_id: UUID,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    """Progress, and where the footage landed.

    Polled by the upload screen while the workers run, so an editor can see the
    grouping form rather than reload the page and guess. Failures are reported
    alongside progress: four clips that could not be processed is information,
    and a batch quietly reporting success while missing four is a bug found
    weeks later in the edit.
    """
    job = await jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such job")
    await principal.assert_can_read(job.project_id)

    # Grouped as the upload screen shows it: one row per shot the footage
    # landed in, flagged where the slate could not be read or disagreed with
    # where the clip was sent.
    groups: dict[tuple[int, int], dict] = {}
    for item in job.items:
        key = (int(item.get("scene", 0)), int(item.get("shot", 0)))
        group = groups.setdefault(key, {
            "scene": key[0],
            "shot": key[1],
            "takes": 0,
            "unread_slates": 0,
            "mismatches": [],
        })
        group["takes"] += 1
        if not item.get("confident"):
            group["unread_slates"] += 1
        if item.get("mismatch"):
            group["mismatches"].append({
                "filename": item.get("filename", ""),
                "detail": item.get("mismatch", ""),
                "slate_raw": item.get("slate_raw", ""),
            })

    for group in groups.values():
        if group["mismatches"]:
            group["status"] = "mismatch"
        elif group["unread_slates"]:
            group["status"] = "unread"
        else:
            group["status"] = "clean"

    done = job.state in jobs.TERMINAL
    return {
        "job_id": str(job.job_id),
        "state": job.state,
        "done": done,
        "total": job.total_items,
        "completed": job.completed_items,
        "failed": job.failed_items,
        "failures": job.failures[:20],
        "target": (
            {"scene": job.target_scene, "shot": job.target_shot}
            if job.target_scene
            else None
        ),
        "groups": sorted(groups.values(), key=lambda g: (g["scene"], g["shot"])),
        "needs_a_look": sum(1 for g in groups.values() if g["status"] != "clean"),
        "started_at": job.started_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
