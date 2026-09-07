"""Film preview is separate from per-shot selections and scene coverage."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from ..auth import Principal, current_principal, require_signed_in
from ..services import film

router = APIRouter(prefix="/film", tags=["film"])


@router.get("/{project_id}/coverage", response_model=film.FilmCoverage)
async def coverage(
    project_id: int,
    response: Response,
    principal: Annotated[Principal, Depends(current_principal)],
):
    await principal.assert_can_read(project_id)
    response.headers["Cache-Control"] = "private, no-store"
    return await film.coverage(project_id)


@router.get("/{project_id}/history", response_model=film.FilmHistory)
async def history(project_id: int, principal: Annotated[Principal, Depends(current_principal)]):
    await principal.assert_can_read(project_id)
    return await film.history(project_id)


@router.get("/{project_id}/history/{revision}", response_model=film.FilmState)
async def version(
    project_id: int, revision: int, principal: Annotated[Principal, Depends(current_principal)]
):
    await principal.assert_can_read(project_id)
    result = await film.read_version(project_id, revision)
    return result.model_copy(update={"updated_by": ""}) if principal.is_anonymous else result


@router.get("/{project_id}", response_model=film.FilmState)
async def read(
    project_id: int, response: Response, principal: Annotated[Principal, Depends(current_principal)]
):
    await principal.assert_can_read(project_id)
    response.headers["Cache-Control"] = "private, no-store"
    result = await film.read(project_id)
    return result.model_copy(update={"updated_by": ""}) if principal.is_anonymous else result


@router.post("/{project_id}/sources", response_model=film.FilmSources)
async def resolve_sources(
    project_id: int,
    body: film.FilmSourceRequest,
    principal: Annotated[Principal, Depends(current_principal)],
):
    await principal.assert_can_read(project_id)
    rows = await film.sources(project_id, ids=list(set(body.clip_ids)), limit=1000)
    return film.FilmSources(sources=rows, more=False)


@router.put("/{project_id}", response_model=film.FilmState)
async def save(
    project_id: int,
    body: film.FilmSave,
    principal: Annotated[Principal, Depends(require_signed_in)],
):
    await principal.assert_can_curate(project_id)
    return await film.save(project_id, body, principal.email or "")


@router.get("/{project_id}/sources", response_model=film.FilmSources)
async def sources(
    project_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
    offset: Annotated[int, Query(ge=0)] = 0,
):
    await principal.assert_can_read(project_id)
    rows = await film.sources(project_id, offset=offset, limit=101)
    return film.FilmSources(sources=rows[:100], more=len(rows) > 100)
