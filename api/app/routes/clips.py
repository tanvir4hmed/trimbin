"""Reversible clip lifecycle commands with creator-aware guest authority."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import Principal, require_signed_in
from ..services import activity, clip_lifecycle, members, projects

router = APIRouter(prefix="/clips", tags=["clips"])


async def _assert_can_remove(principal: Principal, project_id: int, clip_id: UUID) -> dict:
    await principal.assert_can_curate(project_id)
    found = await clip_lifecycle.clip(project_id, clip_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such clip.")
    if (
        projects.open_to_readers(await projects.get(project_id))
        and members.role_of(principal.email) == "guest"
        and found["uploaded_by"].lower() != (principal.email or "").lower()
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Seeded editor footage is protected. You may remove clips you uploaded.",
        )
    return found


@router.delete("/{project_id}/{clip_id}")
async def remove_clip(
    project_id: int,
    clip_id: UUID,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    await _assert_can_remove(principal, project_id, clip_id)
    await clip_lifecycle.record(
        project_id, clip_id, "deleted", principal.email or "", "removed from current project views"
    )
    await activity.record(
        project_id,
        principal.email or "",
        "deleted_clip",
        detail=f"clip {str(clip_id)[:8]} removed (recoverable)",
        actor_role=members.role_of(principal.email),
    )
    return {"status": "deleted", "clip_id": str(clip_id), "recoverable": True}


@router.post("/{project_id}/{clip_id}/restore")
async def restore_clip(
    project_id: int,
    clip_id: UUID,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    await _assert_can_remove(principal, project_id, clip_id)
    await clip_lifecycle.record(
        project_id, clip_id, "restored", principal.email or "", "restored to current project views"
    )
    await activity.record(
        project_id,
        principal.email or "",
        "restored_clip",
        detail=f"clip {str(clip_id)[:8]} restored",
        actor_role=members.role_of(principal.email),
    )
    return {"status": "restored", "clip_id": str(clip_id)}
