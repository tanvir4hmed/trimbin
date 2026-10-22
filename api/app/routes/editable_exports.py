"""Scoped export job creation, cancellation and authenticated ZIP download."""

import hashlib
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from starlette.concurrency import run_in_threadpool

from ..config import settings
from ..evidence.contracts import EvidenceError
from ..exports.store import ExportRequest, ExportStore
from ..exports.worker import LIMIT, export_root
from ..foundation.jobs import PostgresJobs
from ..foundation.repository import Conflict
from ..media.files import safe_path
from .media_library import User, authorize
from .timelines import Key

router = APIRouter(prefix="/editable-exports", tags=["editable-exports"])


@router.post("/{project}/sequences/{sequence_id}", status_code=202)
async def create(project: int, sequence_id: Key, body: ExportRequest, principal: User) -> dict:
    await authorize(principal, project, "write")
    if not settings.export_root:
        raise EvidenceError("exports_not_configured")
    try:
        return await run_in_threadpool(
            ExportStore(settings.database_url).enqueue_export,
            project,
            sequence_id,
            principal.email,
            body,
        )
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{project}/sequences/{sequence_id}")
async def listing(project: int, sequence_id: Key, principal: User) -> dict:
    await authorize(principal, project, "read")
    return {
        "jobs": await run_in_threadpool(
            ExportStore(settings.database_url).exports, project, sequence_id
        )
    }


@router.post("/{project}/jobs/{job_id}/cancel")
async def cancel(project: int, job_id: UUID, principal: User) -> dict:
    await authorize(principal, project, "write")
    await run_in_threadpool(ExportStore(settings.database_url).export_job, project, job_id)
    return {
        "requested": await run_in_threadpool(
            PostgresJobs(settings.database_url).cancel, project, job_id
        )
    }


@router.get("/{project}/jobs/{job_id}/download")
async def download(project: int, job_id: UUID, principal: User):
    await authorize(principal, project, "read")

    def read():
        job = ExportStore(settings.database_url).export_job(project, job_id)
        if job["state"] != "succeeded" or not job["result"]:
            raise EvidenceError("export_not_ready")
        result = job["result"]
        path = safe_path(export_root(settings), result["path"])
        with path.open("rb") as handle:
            data = handle.read(LIMIT + 1)
        if (
            len(data) > LIMIT
            or len(data) != result["bytes"]
            or hashlib.sha256(data).hexdigest() != result["sha256"]
        ):
            raise EvidenceError("export_artifact_changed")
        return data

    try:
        data = await run_in_threadpool(read)
    except FileNotFoundError as exc:
        raise EvidenceError("export_artifact_not_found") from exc
    return Response(
        data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="timeline-{job_id}.zip"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
