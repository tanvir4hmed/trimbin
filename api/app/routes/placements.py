"""The Placement Inbox: clips whose home nobody has agreed with.

Ingest already noticed the disagreements — a clip sent to 12C whose slate reads
15B, a file whose bytes are already here under another name — and had nowhere to
put them except a warning in a log and a flag on a job that expires.

This is where they wait. Every action is explicit and every one is an append:
Move writes a new placement, Keep here writes agreement, Leave unassigned parks
it. Nothing is deleted and nothing moves on its own.

That last part is the whole design. Relocating footage on a slate reading is the
one mistake in this system that scatters a shoot day silently and looks exactly
like the software working.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .. import schemas
from ..auth import Principal, current_principal, require_signed_in
from ..services import activity, members, placements

log = logging.getLogger(__name__)
router = APIRouter(prefix="/placements", tags=["placements"])


class Resolution(BaseModel):
    """What an editor decided about one misplaced clip.

    `move` and `keep` differ only in which numbers they carry, and both are
    written the same way — as a new placement by a named person. An editor
    agreeing with the machine is evidence, and a system that records only
    disagreements cannot tell a checked decision from an unexamined one.
    """

    action: str = Field(pattern="^(move|keep|unassign)$")
    scene: int = Field(default=0, ge=0)
    shot: int = Field(default=0, ge=0)
    note: str = Field(default="", max_length=200)


@router.get("/{project_id}", response_model=schemas.PlacementInbox)
async def inbox(
    project_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    """Everything waiting on a person, with the evidence to decide on.

    The slate frame comes back with each row. An editor working out whether the
    board or the reader was wrong has to see the board — a confidence score is
    not a substitute for looking at it.
    """
    await principal.assert_can_read(project_id)
    waiting = await placements.inbox(project_id)
    return {
        "project_id": project_id,
        "waiting": waiting,
        "count": len(waiting),
    }


@router.post(
    "/{project_id}/{clip_id}",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.PlacementResolved,
)
async def resolve(
    project_id: int,
    clip_id: UUID,
    body: Resolution,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    """Settle one clip.

    For the editors who own the production. A guest may read the inbox and
    comment on any shot; moving footage between shots is a change to where
    somebody else's material lives.
    """
    await principal.assert_can_curate(project_id)

    if body.action == "move":
        if not body.scene:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Say which scene to move it to.",
            )
        scene, shot = body.scene, body.shot
        detail = body.note or f"moved to scene {scene} shot {shot}"

    elif body.action == "keep":
        # Where it already is, agreed with. The numbers come from the current
        # placement rather than from the request, so "keep" cannot quietly
        # become a move because a stale page sent old ones.
        waiting = {w["clip_id"]: w for w in await placements.inbox(project_id)}
        row = waiting.get(str(clip_id))
        if row is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "That clip is not waiting on anybody — somebody has already settled it.",
            )
        scene, shot = row["scene"], row["shot"]
        detail = body.note or "kept where it was sent"

    else:
        # Parked. Group zero is where the interface shows a clip as ungrouped,
        # which is honest for footage nobody can place yet and better than
        # guessing it into a scene there is no evidence for.
        scene, shot = 0, 0
        detail = body.note or "left unassigned"

    await placements.resolve(project_id, clip_id, scene, shot, principal.email or "", detail)
    await activity.record(
        project_id,
        principal.email or "",
        "placed",
        detail=detail,
        scene=scene,
        shot=shot,
        actor_role=members.role_of(principal.email),
    )

    log.info(
        "placement settled: clip %s -> %d/%d by %s",
        str(clip_id)[:8],
        scene,
        shot,
        principal.email,
    )
    return {"status": "settled", "scene": scene, "shot": shot, "detail": detail}
