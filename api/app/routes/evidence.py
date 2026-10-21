"""Project-authorized portable review, analysis, selections and archive retrieval."""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from ..config import settings
from ..evidence.contracts import AnalyzeCommand, CompareCommand, EditCommand, EvidenceError, Search
from ..evidence.projection import search
from ..evidence.store import EvidenceStore
from ..evidence.worker import configuration_identity, windows
from ..foundation.jobs import PostgresJobs
from ..foundation.repository import Conflict
from ..inference.provider import InferenceError, live_preflight
from .media_library import User, authorize

router = APIRouter(prefix="/evidence", tags=["evidence"])


def store() -> EvidenceStore:
    return EvidenceStore(settings.database_url)


def mode_preflight(mode: str) -> None:
    if mode != settings.inference_mode:
        raise EvidenceError("analysis_mode_mismatch")
    if mode == "fixture":
        if settings.profile != "development":
            raise EvidenceError("fixtures_require_development")
    else:
        live_preflight(settings)


@router.get("/{project}")
async def workspace(project: int, principal: User) -> dict:
    await authorize(principal, project, "read")
    snapshot = await run_in_threadpool(store().snapshot, project)
    return {
        **snapshot,
        "analysis_mode": settings.inference_mode,
        "runs": await run_in_threadpool(store().runs, project),
    }


@router.post("/{project}/commands")
async def edit(project: int, body: EditCommand, principal: User) -> dict:
    await authorize(principal, project, "write")
    try:
        return await run_in_threadpool(store().edit, project, principal.email, body)
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{project}/analyze", status_code=202)
async def analyze(project: int, body: AnalyzeCommand, principal: User) -> dict:
    await authorize(principal, project, "write")
    mode_preflight(body.mode)
    if body.overlap_seconds >= body.window_seconds:
        raise EvidenceError("overlap_must_be_smaller_than_window")
    if set(body.allowed_labels) - {"scene", "shot", "take"}:
        raise EvidenceError("invalid_label_category")

    def validate_windows():
        with store().connection() as conn:
            source = store().source(conn, project, body.source_id)
        windows(
            source["duration_us"], body.window_seconds * 1000000, body.overlap_seconds * 1000000
        )

    await run_in_threadpool(validate_windows)
    return await enqueue(project, body, principal)


@router.post("/{project}/compare", status_code=202)
async def compare(project: int, body: CompareCommand, principal: User) -> dict:
    await authorize(principal, project, "write")
    mode_preflight(body.mode)
    return await enqueue(project, body, principal)


async def enqueue(project, body, principal):
    try:
        return await run_in_threadpool(
            store().enqueue,
            project,
            principal.email,
            body.model_dump(mode="json"),
            await run_in_threadpool(configuration_identity, settings),
        )
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{project}/runs/{run_id}")
async def run(project: int, run_id: UUID, principal: User) -> dict:
    await authorize(principal, project, "read")
    return await run_in_threadpool(store().run, project, run_id)


@router.post("/{project}/runs/{run_id}/cancel")
async def cancel(project: int, run_id: UUID, principal: User) -> dict:
    await authorize(principal, project, "write")
    record = await run_in_threadpool(store().run, project, run_id)
    return {
        "requested": await run_in_threadpool(
            PostgresJobs(settings.database_url).cancel, project, record["job_id"]
        )
    }


@router.post("/{project}/search")
async def find(project: int, body: Search, principal: User) -> dict:
    await authorize(principal, project, "read")
    try:
        return await search(settings, project, body)
    except InferenceError as exc:
        raise HTTPException(503, exc.code) from exc
