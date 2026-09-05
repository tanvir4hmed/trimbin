"""Projects: making one, listing them, and saying who else may work in one.

The rule that shapes this file is that everyone gets the same application. A
guest signs in, makes a project, uploads their own footage and works it exactly
as an editor here does — under limits stated on the form before they start.

That replaced a sandbox, which was the wrong idea twice over: it sent a visitor
somewhere the real users never go, and then asked them to judge the thing they
had not seen. One interface, permissions changing what is *possible* and never
what is *visible*.

The other rule that is not thin: a project nobody may read answers 404, never
403. A 403 tells a stranger the project exists, which is enough to enumerate
every project on the system by watching which ids answer differently.
"""

from __future__ import annotations

import logging
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from .. import schemas
from ..auth import Principal, current_principal, require_signed_in
from ..services import dashboard as dashboard_service
from ..services import members, projects

log = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class NewProject(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("A project needs a name.")
        return cleaned


class NewMember(BaseModel):
    email: str = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def _looks_like_an_address(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not _EMAIL.match(cleaned):
            raise ValueError("That is not an email address.")
        return cleaned


class ProjectCommand(BaseModel):
    rev: int = Field(ge=0)
    action: Literal["rename", "archive", "trash", "restore", "delete"]
    name: str = Field(default="", max_length=120)


def _as_dict(project, viewer_email: str | None) -> dict:
    return {
        "project_id": project.project_id,
        "name": project.name,
        "owner_email": project.owner_email,
        "member_emails": project.member_emails,
        "is_public": project.is_public,
        "created_at": project.created_at.isoformat(),
        # Told rather than inferred. A client that works out whether to show the
        # "add member" button by comparing strings will get it wrong the first
        # time an address differs in case.
        "you_are_owner": bool(viewer_email and viewer_email.lower() == project.owner_email.lower()),
        "you_can_upload": bool(
            viewer_email
            and (
                viewer_email.lower() == project.owner_email.lower()
                or viewer_email.lower() in {m.lower() for m in project.member_emails}
                or (members.is_staff(viewer_email) and members.is_staff(project.owner_email))
            )
        ),
        "state": getattr(project, "state", "active"),
        "rev": getattr(project, "rev", 0),
    }


@router.get("", response_model=schemas.ProjectList)
async def mine(
    principal: Annotated[Principal, Depends(current_principal)],
    detail: bool = False,
    state_filter: Literal["active", "archived", "trashed", "deleted"] = "active",
) -> dict:
    """Everything this person can open.

    `detail=true` adds the counts a list screen needs — scenes, shots, takes,
    how far through, how many are waiting. It is one extra query across every
    project rather than one per row, and it is optional because the project
    switcher in the header wants names and nothing else.

    `deleted` is listable by its owner because delete here is a state, not a
    purge — the route has always had a `restore` action and read deleted rows to
    serve it. Without a way to see them, restore was a feature nobody could
    reach, and deleting the demo project meant a signed-out visitor got a 404
    with no way back.
    """
    found = (
        await projects.visible_to(principal.email or "")
        if state_filter == "active"
        else await projects.for_member(principal.email or "", states={state_filter})
    )
    rows = [_as_dict(p, principal.email) for p in found]
    if principal.is_anonymous:
        for row in rows:
            row.update(owner_email="", member_emails=[], you_are_owner=False, you_can_upload=False)

    if detail and found:
        stats = await dashboard_service.for_projects(
            [p.project_id for p in found], principal.email or ""
        )
        by_id = {s["project_id"]: s for s in stats["projects"]}
        for row in rows:
            row.update(by_id.get(row["project_id"], {}))

    return {
        "you": principal.email,
        "role": members.role_of(principal.email),
        "limits": members.limits_for(principal.email).as_dict(),
        "projects": rows,
    }


@router.post("", status_code=status.HTTP_201_CREATED, response_model=schemas.ProjectCreated)
async def create(
    body: NewProject,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    """Name only.

    No scene list, no crew, no shoot dates. Everything else about a production is
    discovered from the footage, and a form that asks for it up front is a form
    someone abandons.

    Anyone signed in may do this, including a guest — that is the whole of how a
    visitor gets a real workspace instead of a demonstration. What bounds the
    cost is the limit on how many, stated on the form rather than discovered
    here.
    """
    limits = members.limits_for(principal.email)
    existing = await projects.for_member(
        principal.email or "", states={"active", "archived", "trashed"}
    )
    owned = [p for p in existing if p.owner_email.lower() == (principal.email or "").lower()]

    if len(owned) >= limits.projects:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"You own {len(owned)} projects, which is the limit for your "
            f"account. Delete one, or ask us to raise it."
            if members.is_staff(principal.email)
            else (
                f"A guest account can own {limits.projects} projects and you "
                f"have {len(owned)}. Everything in them stays for "
                f"{limits.retention_days} days."
            ),
        )

    project_id = await projects.create(name=body.name, owner_email=principal.email or "")
    log.info(
        "project %d created by %s (%s)",
        project_id,
        principal.email,
        members.role_of(principal.email),
    )

    project = await projects.get(project_id)
    if project is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Project creation did not persist."
        )
    return {**_as_dict(project, principal.email), "limits": limits.as_dict()}


@router.get("/{project_id}", response_model=schemas.Project)
async def one(
    project_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    """A single project, readable by members and by anyone on a public one."""
    await principal.assert_can_read(project_id)

    project = await projects.get(project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such project.")

    if project.is_public and principal.is_anonymous:
        # A stranger reading the demo has no business seeing who is on the team.
        # The footage and the reasoning are the public part; the crew list is not.
        #
        # Redacted by emptying the fields, never by omitting them. Omitting them
        # was the first version and it took the workspace down: the page spreads
        # `member_emails` to build the assignee list, `...undefined` throws, and
        # the whole route died as "a client-side exception has occurred" — with
        # nothing in the API logs, because the API had answered 200.
        #
        # A response whose shape changes with who is asking is a response every
        # caller has to special-case, and the one that forgets is the one nobody
        # tests, because it only breaks for signed-out visitors.
        return {
            "project_id": project.project_id,
            "name": project.name,
            "owner_email": "",
            "member_emails": [],
            "is_public": True,
            "created_at": project.created_at.isoformat(),
            "you_are_owner": False,
            "you_can_upload": False,
        }

    return _as_dict(project, principal.email)


@router.patch("/{project_id}", response_model=schemas.Project)
async def change_project(
    project_id: int,
    body: ProjectCommand,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    """Owner-only lifecycle. A guest has full authority over their own project."""
    await principal.assert_is_owner(project_id)
    current = await projects.get(project_id, include_deleted=True)
    if current is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such project.")
    if body.action == "rename" and not body.name.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A project needs a name.")
    next_state = {
        "archive": "archived",
        "trash": "trashed",
        "restore": "active",
        "delete": "deleted",
    }.get(body.action)
    try:
        changed = await projects.change(
            project_id,
            expected_rev=body.rev,
            name=body.name.strip() if body.action == "rename" else None,
            state=next_state,
        )
    except projects.ProjectConflict as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Somebody changed this project. Current revision is {exc.current}.",
        ) from exc
    return _as_dict(changed, principal.email)


@router.post("/{project_id}/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    project_id: int,
    body: NewMember,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    """Only the owner may add people.

    By email, and without an invitation flow: the address is added and whoever
    signs in with it is in. That is a real trade — a typo grants access to
    someone who was never meant to have it — and it is the right one at this
    size, where the alternative is building an invitation system for a team of
    three.
    """
    await principal.assert_is_owner(project_id)

    project = await projects.get(project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such project.")

    if body.email == project.owner_email.lower():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "They already own this project.",
        )
    if body.email in {m.lower() for m in project.member_emails}:
        return {"status": "already_a_member", "email": body.email}

    if project.is_public:
        # Read by strangers. Adding editors to something published would let a
        # member change what every visitor sees. The team's own productions are
        # readable without being published, and those do take members.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A published project does not take members.",
        )

    await projects.add_member(project_id, body.email)
    log.info("project %d: %s added by %s", project_id, body.email, principal.email)
    return {"status": "added", "email": body.email}
