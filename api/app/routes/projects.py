"""Projects: making one, listing yours, and saying who else may work in it.

Deliberately thin. A production has a hundred roles and this has two, because a
permissions matrix is real work for a real product and would earn nothing on a
team of three. Owner adds people and supersedes; member does everything else.

The one rule that is not thin: a project nobody may read answers 404, never 403.
A 403 tells a stranger the project exists, which is enough to enumerate every
project on the system by watching which ids answer differently.
"""

from __future__ import annotations

import logging
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ..auth import Principal, current_principal, require_member
from ..config import settings
from ..services import projects

log = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# A cap on projects per person, so an authenticated visitor cannot fill the
# archive with empty projects. High enough that nobody working normally meets it.
MAX_PROJECTS_PER_PERSON = 25


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
        "you_are_owner": bool(
            viewer_email and viewer_email.lower() == project.owner_email.lower()
        ),
    }


@router.get("")
async def mine(
    principal: Annotated[Principal, Depends(require_member)],
) -> dict:
    """Everything this person can open, for the project switcher."""
    found = await projects.for_member(principal.email or "")
    return {
        "you": principal.email,
        "projects": [_as_dict(p, principal.email) for p in found],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create(
    body: NewProject,
    principal: Annotated[Principal, Depends(require_member)],
) -> dict:
    """Name only.

    No scene list, no crew, no shoot dates. Everything else about a production is
    discovered from the footage, and a form that asks for it up front is a form
    someone abandons.
    """
    existing = await projects.for_member(principal.email or "")
    owned = [p for p in existing if p.owner_email.lower() == (principal.email or "").lower()]
    if len(owned) >= MAX_PROJECTS_PER_PERSON:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"You already own {len(owned)} projects. Ask us to raise the limit.",
        )

    project_id = await projects.create(name=body.name, owner_email=principal.email or "")
    log.info("project %d created by %s", project_id, principal.email)

    project = await projects.get(project_id)
    return _as_dict(project, principal.email) if project else {"project_id": project_id}


@router.get("/{project_id}")
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
        return {
            "project_id": project.project_id,
            "name": project.name,
            "is_public": True,
            "created_at": project.created_at.isoformat(),
        }

    return _as_dict(project, principal.email)


@router.post("/{project_id}/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    project_id: int,
    body: NewMember,
    principal: Annotated[Principal, Depends(require_member)],
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

    if project_id in (settings.demo_project_id, settings.sandbox_project_id):
        # These two are read by strangers and written to by the pipeline. Adding
        # editors to them would let a member change what every visitor sees.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The demo and sandbox projects do not take members.",
        )

    await projects.add_member(project_id, body.email)
    log.info("project %d: %s added by %s", project_id, body.email, principal.email)
    return {"status": "added", "email": body.email}
