"""One request per screen.

The project workspace made four — the tree, the project record, the shot plan,
and the caller's capabilities — each with its own loading state and its own
chance to disagree with the others. The shot cockpit made three, and the brief
arrived after the verdicts, so the title changed from "Shot 3" to "12B" a moment
after the page had settled.

Four requests for one screen is not only slower. It is four separate opinions
about who you are and what you may do, assembled by the browser, and the one
that arrives last wins.

These endpoints assemble server-side, where the pieces come from one principal
and one point in time. They are read models: no route here writes anything.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from .. import schemas
from ..auth import Principal, current_principal
from ..config import settings
from ..services import comments as comments_service
from ..services import members, projects, shots, structure
from . import analysis as analysis_routes
from . import review as review_routes

log = logging.getLogger(__name__)
router = APIRouter(prefix="/screens", tags=["screens"])


def _me(principal: Principal) -> schemas.Me:
    """Who is asking, from the one place that decides.

    `capabilities()` already reports `signed_in`, so passing it again here was a
    duplicate keyword and a TypeError on every call — and `/me` gets away with
    the same duplication because it builds a dict, where a repeated key is an
    overwrite rather than an error.

    Spread only, so there is one source for every field.
    """
    return schemas.Me(
        **members.capabilities(principal.email),
        email=principal.email,
        demo_project_id=settings.demo_project_id,
    )


@router.get("/project/{project_id}", response_model=schemas.ProjectScreen)
async def project_screen(
    project_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
    scene: int | None = None,
    camera: str | None = None,
    shoot_day: str | None = None,
    assignee: str | None = None,
) -> schemas.ProjectScreen:
    """The workspace, assembled.

    The tree, the plan and the project record are independent reads, so they run
    together rather than in sequence. Three round trips to three different
    stores, waited on once.
    """
    await principal.assert_can_read(project_id)

    tree, plan, found = await asyncio.gather(
        review_routes.tree(
            project_id,
            principal,
            scene=scene,
            camera=camera,
            shoot_day=shoot_day,
            assignee=assignee,
        ),
        structure.for_project(project_id),
        projects.get(project_id),
    )

    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such project.")

    return schemas.ProjectScreen(
        project=_project_dict(found, principal),
        tree=schemas.Tree(**tree),
        plan=schemas.Plan(
            project_id=project_id,
            scenes=[s.as_dict() for s in plan],
            next_scene=max((s.scene for s in plan), default=0) + 1,
        ),
        me=_me(principal),
    )


@router.get("/shot/{project_id}/{scene}/{shot}", response_model=schemas.ShotScreen)
async def shot_screen(
    project_id: int,
    scene: int,
    shot: int,
    principal: Annotated[Principal, Depends(current_principal)],
) -> schemas.ShotScreen:
    """The cockpit, assembled.

    A shot nothing has compared is a normal state, not a failure, so the verdicts
    come back as null rather than as a 404 the page has to catch and reinterpret.
    That reinterpretation is where the previous version put an error message on a
    screen whose only real news was "press compare".
    """
    await principal.assert_can_read(project_id)

    verdicts, brief, notes, present = await asyncio.gather(
        _verdicts_or_none(project_id, scene, shot, principal),
        shots.get(project_id, scene, shot),
        comments_service.for_shot(project_id, scene, shot),
        review_routes.review_service.takes_in_shot(project_id, scene, shot),
    )

    # The judged takes when there are any, the footage itself when there are
    # not. A comparison needs two takes; watching one, analysing it and cutting
    # a range out of it do not. Reading the takes only out of the verdicts is
    # why a freshly uploaded clip had no player, no lanes and no way to be
    # selected — while its proxy sat built and reachable.
    takes = (
        list(verdicts.takes)
        if verdicts and verdicts.takes
        else [schemas.Take(**row) for row in present]
    )

    loaded = await asyncio.gather(
        *(analysis_routes._read(project_id, UUID(take.clip_id)) for take in takes)
    )
    analyses = [schemas.TakeAnalysis(**row) for row in loaded]

    return schemas.ShotScreen(
        verdicts=verdicts,
        brief=schemas.Brief(**brief.as_dict(), is_empty=brief.is_empty),
        takes=takes,
        analyses=analyses,
        comments=[schemas.Comment(**c) for c in notes],
        open_comments=sum(1 for c in notes if not c["resolved"]),
    )


async def _verdicts_or_none(
    project_id: int, scene: int, shot: int, principal: Principal
) -> schemas.Verdicts | None:
    try:
        return schemas.Verdicts(**await review_routes.verdicts(project_id, scene, shot, principal))
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            return None
        raise


def _project_dict(project, principal: Principal) -> schemas.Project:
    """The project record, redacted for a stranger by emptying, never omitting.

    Omitting was the first version and it took the workspace down for every
    signed-out visitor: the page spreads `member_emails`, and spreading undefined
    throws. A response whose *shape* changes with who is asking is one every
    caller has to special-case.
    """
    email = (principal.email or "").lower()
    anonymous = principal.is_anonymous and project.is_public

    return schemas.Project(
        project_id=project.project_id,
        name=project.name,
        owner_email="" if anonymous else project.owner_email,
        member_emails=[] if anonymous else project.member_emails,
        is_public=project.is_public,
        created_at=project.created_at.isoformat(),
        you_are_owner=bool(email and email == project.owner_email.lower()),
        you_can_upload=bool(
            email
            and (
                email == project.owner_email.lower()
                or email in {m.lower() for m in project.member_emails}
                or (members.is_staff(email) and members.is_staff(project.owner_email))
            )
        ),
        state=getattr(project, "state", "active"),
        rev=getattr(project, "rev", 0),
    )
