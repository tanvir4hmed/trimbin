"""Logical performance candidates; never destructive media cuts."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Response

from .. import schemas
from ..auth import Principal, current_principal, require_signed_in
from ..services import analysis_store, attempts, jobs

router = APIRouter(prefix="/attempts", tags=["attempts"])


@router.post(
    "/{project_id}/{clip_id}/analyse", response_model=schemas.AnalysisQueued, status_code=202
)
async def analyse(
    project_id: int, clip_id: UUID, principal: Annotated[Principal, Depends(require_signed_in)]
):
    await principal.assert_can_curate(project_id)
    clip = await analysis_store.clip_identity(project_id, clip_id)
    if not clip or not clip["proxy_uri"]:
        raise HTTPException(409, "An active recording with a ready proxy is required.")
    current = await jobs.analysis_states(project_id, [str(clip_id)])
    if current.get(str(clip_id), {}).get("state") in {"pending", "queued", "processing"}:
        raise HTTPException(409, "This recording already has queued or running analysis.")
    queued = await jobs.enqueue_analysis(project_id, [{**clip, "clip_id": clip_id}], force=True)
    if not queued:
        raise HTTPException(
            503, "Analysis could not be queued; retry later. Your decisions are unchanged."
        )
    return {"status": "queued", "project_id": project_id, "queued": queued}


@router.get("/{project_id}/{clip_id}", response_model=attempts.AttemptState)
async def read(
    project_id: int,
    clip_id: UUID,
    response: Response,
    principal: Annotated[Principal, Depends(current_principal)],
):
    await principal.assert_can_read(project_id)
    response.headers["Cache-Control"] = "private, no-store"
    result = await attempts.read(project_id, clip_id)
    state = (await jobs.analysis_states(project_id, [str(clip_id)])).get(str(clip_id), {})
    return result.model_copy(
        update={
            "analysis_state": state.get("state", ""),
            "analysis_error": state.get("error", ""),
        }
    )


@router.put("/{project_id}/{clip_id}", response_model=attempts.AttemptState)
async def save(
    project_id: int,
    clip_id: UUID,
    body: attempts.AttemptSave,
    principal: Annotated[Principal, Depends(require_signed_in)],
):
    await principal.assert_can_curate(project_id)
    return await attempts.save(project_id, clip_id, body, principal.email or "")


@router.get("/{project_id}/{clip_id}/history", response_model=attempts.AttemptHistory)
async def history(
    project_id: int, clip_id: UUID, principal: Annotated[Principal, Depends(current_principal)]
):
    await principal.assert_can_read(project_id)
    return await attempts.history(project_id, clip_id)


@router.get("/{project_id}/{clip_id}/history/{revision}", response_model=attempts.AttemptState)
async def version(
    project_id: int,
    clip_id: UUID,
    revision: Annotated[int, Path(ge=0)],
    principal: Annotated[Principal, Depends(current_principal)],
):
    await principal.assert_can_read(project_id)
    return await attempts.read(project_id, clip_id, revision)
