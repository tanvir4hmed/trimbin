"""Where the day starts, and who the person asking is.

Two routes. One says what this caller may do, so the interface never draws a
button the API will refuse. The other answers the only question an editor has at
nine in the morning: what should I be doing.

Both span projects. Somebody works on three at once, and a dashboard that makes
them open each one is a dashboard that gets opened once.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from ..auth import Principal, current_principal, require_signed_in
from ..config import settings
from ..services import activity, members, projects
from ..services import dashboard as dashboard_service

log = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard"])


@router.get("/me")
async def me(
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    """Who is asking, and what the API will let them do.

    Told rather than inferred. A page that works out whether to draw the upload
    button by comparing an address against a hard-coded list is a second
    implementation of the permission rules, and the two will disagree — the
    failure being a button that is drawn and then refused, which is worse than
    no button at all.

    Answers for anonymous callers too, and truthfully: read everything, change
    nothing, sign in to take part. That is a better first screen than a redirect.
    """
    return {
        "email": principal.email,
        "signed_in": not principal.is_anonymous,
        **members.capabilities(principal.email),
        "demo_project_id": settings.demo_project_id,
    }


@router.get("/dashboard")
async def dashboard(
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    """The queue, the projects, and what the team did while you were away.

    One assembled answer rather than four calls the page has to stitch. The
    stitching is the same either way; doing it here means the browser waits on
    one round trip instead of four, and the slowest of the four is what a person
    would have waited for.
    """
    # Everything they can open, not only what they belong to. A guest belongs
    # to nothing, and the first version showed them an empty desk on a
    # deployment holding three productions they are explicitly allowed to work.
    mine = await projects.visible_to(principal.email or "")
    ids = [p.project_id for p in mine]
    names = {p.project_id: p.name for p in mine}

    built = await dashboard_service.for_projects(ids, principal.email or "")
    recent = await dashboard_service.recent_decisions(ids)
    happened = await activity.for_projects(ids)
    notes = await dashboard_service.recent_notes(ids)

    cards = []
    for p in mine:
        stats = next(
            (s for s in built["projects"] if s["project_id"] == p.project_id), None
        )
        cards.append({
            "project_id": p.project_id,
            "name": p.name,
            "is_public": p.is_public,
            "you_are_owner": (principal.email or "").lower() == p.owner_email.lower(),
            # Whether this one is theirs to work, which is the difference
            # between their own projects and ours on the same screen. The card
            # fills in a type that promises this field, and a card missing it
            # reads as "false" everywhere it is used.
            "you_can_upload": bool(
                principal.email
                and (
                    principal.email.lower() == p.owner_email.lower()
                    or principal.email.lower() in {m.lower() for m in p.member_emails}
                    or (
                        members.is_staff(principal.email)
                        and members.is_staff(p.owner_email)
                    )
                )
            ),
            "created_at": p.created_at.isoformat(),
            "members": len(p.member_emails) + 1,
            "scenes": stats["scenes"] if stats else 0,
            "shots": stats["shots"] if stats else 0,
            "takes": stats["takes"] if stats else 0,
            "settled": stats["settled"] if stats else 0,
            "waiting": stats["waiting"] if stats else 0,
            # Null rather than zero when the project holds no footage. A project
            # with nothing in it is not a project that is nought per cent done,
            # and a bar drawn at zero says something untrue about it.
            "progress_pct": stats["progress_pct"] if stats else None,
        })

    return {
        "you": principal.email,
        "role": members.role_of(principal.email),
        "queue": [w.as_dict(names) for w in built["queue"]],
        "queue_total": built["queue_total"],
        "totals": built["totals"],
        "projects": sorted(cards, key=lambda c: (-(c["waiting"] or 0), c["name"])),
        "recent": [{**r, "project_name": names.get(r["project_id"], "")} for r in recent],
        "notes": [{**n, "project_name": names.get(n["project_id"], "")} for n in notes],
        "activity": [
            {**a, "project_name": names.get(a["project_id"], "")} for a in happened
        ],
        "limits": members.limits_for(principal.email).as_dict(),
    }
