"""Projects and who belongs to them.

Membership is a list of email addresses on the project document. A small team
needs no permissions matrix, and building one would be work that earns nothing —
the two roles that matter are the person who can set other people's work aside
and everyone else.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from google.cloud import firestore

from ..config import settings
from . import jobs

log = logging.getLogger(__name__)

COLLECTION = "projects"


@dataclass(frozen=True)
class Project:
    project_id: int
    name: str
    owner_email: str
    member_emails: list[str]
    is_public: bool
    created_at: datetime


def _doc(project_id: int):
    return jobs.db().collection(COLLECTION).document(str(project_id))


async def get(project_id: int) -> Project | None:
    snapshot = await _doc(project_id).get()
    if not snapshot.exists:
        return None
    d = snapshot.to_dict() or {}
    return Project(
        project_id=project_id,
        name=d.get("name", ""),
        owner_email=d.get("owner_email", ""),
        member_emails=d.get("member_emails", []),
        is_public=d.get("is_public", False),
        created_at=d.get("created_at") or datetime.now(UTC),
    )


async def is_member(project_id: int, email: str) -> bool:
    project = await get(project_id)
    if project is None:
        return False
    email = email.lower()
    return email == project.owner_email.lower() or email in {
        m.lower() for m in project.member_emails
    }


async def is_owner(project_id: int, email: str) -> bool:
    project = await get(project_id)
    return project is not None and email.lower() == project.owner_email.lower()


async def create(name: str, owner_email: str, is_public: bool = False) -> int:
    """Allocate the next id and write the project.

    Ids are sequential integers rather than uuids because they are the ClickHouse
    partition and sort key, where a random 128-bit value would scatter every
    project's rows across the whole table and defeat the ordering that makes
    project-scoped reads fast.

    Synthetic rows live at and above 900000, so real projects never reach that
    range in any plausible lifetime of this system.
    """
    counter = jobs.db().collection("counters").document("project_id")

    @firestore.async_transactional
    async def allocate(transaction) -> int:
        snapshot = await counter.get(transaction=transaction)
        current = (snapshot.to_dict() or {}).get("value", 0) if snapshot.exists else 0
        nxt = current + 1
        transaction.set(counter, {"value": nxt})
        return nxt

    project_id = await allocate(jobs.db().transaction())

    await _doc(project_id).set({
        "name": name,
        "owner_email": owner_email.lower(),
        "member_emails": [],
        "is_public": is_public,
        "created_at": datetime.now(UTC),
    })

    log.info("project %d created by %s", project_id, owner_email)
    return project_id


async def add_member(project_id: int, email: str) -> None:
    await _doc(project_id).update({
        "member_emails": firestore.ArrayUnion([email.lower()])
    })


async def for_member(email: str) -> list[Project]:
    """Everything this person can open.

    Two queries rather than one, because Firestore cannot OR across fields.
    Owned projects and member projects are fetched separately and merged.
    """
    email = email.lower()
    collection = jobs.db().collection(COLLECTION)

    found: dict[int, Project] = {}

    async for snapshot in collection.where("owner_email", "==", email).stream():
        found[int(snapshot.id)] = await get(int(snapshot.id))  # type: ignore[assignment]

    async for snapshot in collection.where(
        "member_emails", "array_contains", email
    ).stream():
        if int(snapshot.id) not in found:
            found[int(snapshot.id)] = await get(int(snapshot.id))  # type: ignore[assignment]

    return sorted(
        (p for p in found.values() if p is not None),
        key=lambda p: p.created_at,
        reverse=True,
    )


def is_public_project(project_id: int) -> bool:
    """Open to a reader with no account.

    One id, from config. The sandbox that used to be the second one is gone —
    everyone gets the same application now, and a guest works in a project they
    own rather than in a shared scratch space.
    """
    return project_id == settings.demo_project_id
