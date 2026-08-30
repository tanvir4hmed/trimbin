"""Laying out a production before the footage arrives.

A scene list comes from the script and a shot list from the director. Both exist
on paper before anything is shot, so an editor setting up a project should be
able to enter them and then upload into a named place.

Declaring nothing is still supported and still works: slates decide, exactly as
before.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..auth import Principal, current_principal, require_signed_in
from ..services import activity, members, structure

log = logging.getLogger(__name__)
router = APIRouter(prefix="/structure", tags=["structure"])


class NewScene(BaseModel):
    scene: int = Field(ge=1, le=9999)
    heading: str = Field(default="", max_length=structure.MAX_HEADING)


class NewShot(BaseModel):
    shot: int = Field(ge=1, le=999)
    slug: str = Field(default="", max_length=structure.MAX_SLUG)
    description: str = Field(default="", max_length=structure.MAX_HEADING)


@router.get("/{project_id}")
async def plan(
    project_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    """The declared scenes and shots, and what to number the next one."""
    await principal.assert_can_read(project_id)
    scenes = await structure.for_project(project_id)
    return {
        "project_id": project_id,
        "scenes": [s.as_dict() for s in scenes],
        "next_scene": max((s.scene for s in scenes), default=0) + 1,
    }


@router.post("/{project_id}/scenes", status_code=status.HTTP_201_CREATED)
async def add_scene(
    project_id: int,
    body: NewScene,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    await principal.assert_can_curate(project_id)
    scene = await structure.add_scene(project_id, body.scene, body.heading)
    await activity.record(
        project_id, principal.email or "", "planned",
        detail=f"scene {body.scene}" + (f" — {body.heading}" if body.heading else ""),
        scene=body.scene,
        actor_role=members.role_of(principal.email),
    )
    return scene.as_dict()


@router.post("/{project_id}/scenes/{scene}/shots", status_code=status.HTTP_201_CREATED)
async def add_shot(
    project_id: int,
    scene: int,
    body: NewShot,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    await principal.assert_can_curate(project_id)
    updated = await structure.add_shot(
        project_id, scene, body.shot, body.slug, body.description
    )
    await activity.record(
        project_id, principal.email or "", "planned",
        detail=body.slug or f"scene {scene} shot {body.shot}",
        scene=scene, shot=body.shot,
        actor_role=members.role_of(principal.email),
    )
    return updated.as_dict()


@router.delete("/{project_id}/scenes/{scene}/shots/{shot}")
async def remove_shot(
    project_id: int,
    scene: int,
    shot: int,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    """Remove a planned shot.

    Only from the plan. Footage already sitting in it is untouched — deleting a
    line from a shot list is not a decision to delete a day's work, and the two
    should never be the same button.
    """
    await principal.assert_can_curate(project_id)

    from ..services.analytics import client

    ch = await client()
    result = await ch.query(
        """
        SELECT count() FROM clips
        WHERE project_id = {p:UInt32} AND group_id = {g:UInt32} AND subgroup_id = {s:UInt32}
        """,
        parameters={"p": project_id, "g": scene, "s": shot},
    )
    held = int(result.result_rows[0][0]) if result.result_rows else 0
    if held:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This shot holds {held} takes. Move or remove them first.",
        )

    updated = await structure.remove_shot(project_id, scene, shot)
    return updated.as_dict()


@router.get("/{project_id}/activity")
async def project_activity(
    project_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
    limit: int = 40,
) -> dict:
    """Who did what on this production, newest first."""
    await principal.assert_can_read(project_id)
    return {
        "project_id": project_id,
        "activity": await activity.for_project(project_id, limit=min(limit, 200)),
    }
