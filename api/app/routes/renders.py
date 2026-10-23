"""Scoped render jobs, cancellation and ticketed streaming movie downloads."""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse

from ..config import settings
from ..evidence.contracts import EvidenceError
from ..exports.worker import export_root
from ..foundation.jobs import PostgresJobs
from ..foundation.repository import Conflict
from ..media import tickets
from ..media.files import safe_path
from ..renders.store import RenderRequest, RenderStore
from .media_library import User, authorize
from .timelines import Key

router = APIRouter(prefix="/renders", tags=["renders"])


@router.post("/{project}/sequences/{sequence_id}", status_code=202)
async def create(project: int, sequence_id: Key, body: RenderRequest, principal: User) -> dict:
    await authorize(principal, project, "write")
    if not settings.export_root:
        raise EvidenceError("exports_not_configured")
    try:
        return await run_in_threadpool(
            RenderStore(settings.database_url).enqueue_export,
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
            RenderStore(settings.database_url).exports, project, sequence_id
        )
    }


@router.post("/{project}/jobs/{job_id}/cancel")
async def cancel(project: int, job_id: UUID, principal: User) -> dict:
    await authorize(principal, project, "write")
    await run_in_threadpool(RenderStore(settings.database_url).export_job, project, job_id)
    return {
        "requested": await run_in_threadpool(
            PostgresJobs(settings.database_url).cancel, project, job_id
        )
    }


@router.post("/{project}/jobs/{job_id}/access")
async def access(project: int, job_id: UUID, principal: User):
    await authorize(principal, project, "read")
    job = await run_in_threadpool(RenderStore(settings.database_url).export_job, project, job_id)
    if job["state"] != "succeeded":
        raise EvidenceError("render_not_ready")
    ticket = tickets.issue(settings.session_secret, project, str(job_id), "render")
    return {"url": f"/renders/{project}/jobs/{job_id}/download?ticket={ticket}"}


@router.get("/{project}/jobs/{job_id}/download")
async def download(project: int, job_id: UUID, ticket: str):
    tickets.verify(settings.session_secret, project, str(job_id), "render", ticket)
    job = await run_in_threadpool(RenderStore(settings.database_url).export_job, project, job_id)
    if job["state"] != "succeeded" or not job["result"]:
        raise EvidenceError("render_not_ready")
    result = job["result"]
    try:
        path = await run_in_threadpool(safe_path, export_root(settings), result["path"])
        stat = await run_in_threadpool(path.stat)
    except FileNotFoundError as exc:
        raise EvidenceError("render_artifact_not_found") from exc
    if stat.st_size != result["bytes"] or stat.st_mtime_ns != result["mtime_ns"]:
        raise EvidenceError("render_artifact_changed")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"movie-{job_id}.mp4",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Content-SHA256": result["sha256"],
        },
    )
