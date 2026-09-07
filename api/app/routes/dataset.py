"""Authorized per-recording evidence export without source media URLs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from ..auth import Principal, require_signed_in
from ..services import dataset

router = APIRouter(prefix="/dataset", tags=["dataset"])


@router.get("/{project_id}/{clip_id}", response_model=dataset.EditorialDatasetRecord)
async def export_clip(
    project_id: int,
    clip_id: UUID,
    response: Response,
    principal: Annotated[Principal, Depends(require_signed_in)],
):
    await principal.assert_can_curate(project_id)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="editorial-evidence-{clip_id}.json"'
    )
    return await dataset.export_clip(project_id, clip_id)
