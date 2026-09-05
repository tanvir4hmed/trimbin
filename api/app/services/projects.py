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

from . import jobs, members

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
    state: str = "active"
    rev: int = 0


class ProjectConflict(RuntimeError):
    def __init__(self, current: int) -> None:
        self.current = current
        super().__init__(f"expected an older revision; current revision is {current}")


def _doc(project_id: int):
    return jobs.db().collection(COLLECTION).document(str(project_id))


async def get(project_id: int, *, include_deleted: bool = False) -> Project | None:
    snapshot = await _doc(project_id).get()
    if not snapshot.exists:
        return None
    d = snapshot.to_dict() or {}
    if d.get("state") == "deleted" and not include_deleted:
        return None
    return Project(
        project_id=project_id,
        name=d.get("name", ""),
        owner_email=d.get("owner_email", ""),
        member_emails=d.get("member_emails", []),
        is_public=d.get("is_public", False),
        created_at=d.get("created_at") or datetime.now(UTC),
        state=d.get("state", "active"),
        rev=int(d.get("rev", 0)),
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
    """Who owns it, regardless of the state it is in.

    Deleted projects included, and that is the point: `PATCH` supports a
    `restore` action and fetches with `include_deleted=True` to serve it, but
    the ownership check in front of it could not see a deleted project and
    answered 403. Restore was unreachable for the one state it exists to undo,
    so deleting was a one-way door — and it takes the public demo project with
    it, which is what a signed-out judge sees.

    This decides *who* may act. Each route still decides whether the project is
    in a state that allows the action: `add_member` fetches without deleted rows
    and still refuses, while `change_project` fetches with them and can restore.
    """
    project = await get(project_id, include_deleted=True)
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

    await _doc(project_id).set(
        {
            "name": name,
            "owner_email": owner_email.lower(),
            "member_emails": [],
            "is_public": is_public,
            "created_at": datetime.now(UTC),
            "state": "active",
            "rev": 0,
        }
    )

    log.info("project %d created by %s", project_id, owner_email)
    return project_id


async def add_member(project_id: int, email: str) -> None:
    await _doc(project_id).update({"member_emails": firestore.ArrayUnion([email.lower()])})


async def for_member(email: str, *, states: set[str] | None = None) -> list[Project]:
    """Everything this person can open.

    Two queries rather than one, because Firestore cannot OR across fields.
    Owned projects and member projects are fetched separately and merged.
    """
    email = email.lower()
    collection = jobs.db().collection(COLLECTION)

    found: dict[int, Project] = {}

    # Fetched including deleted rows, then filtered by `allowed` below. `get`
    # hides deleted projects, which meant asking for them returned nothing at
    # all and the owner had no way to see — or restore — something they had
    # removed.
    async for snapshot in collection.where("owner_email", "==", email).stream():
        found[int(snapshot.id)] = await get(int(snapshot.id), include_deleted=True)  # type: ignore[assignment]

    async for snapshot in collection.where("member_emails", "array_contains", email).stream():
        if int(snapshot.id) not in found:
            found[int(snapshot.id)] = await get(int(snapshot.id), include_deleted=True)  # type: ignore[assignment]

    allowed = states or {"active"}
    return sorted(
        (p for p in found.values() if p is not None and p.state in allowed),
        key=lambda p: p.created_at,
        reverse=True,
    )


async def visible_to(email: str) -> list[Project]:
    """Everything this person can open, not only what they belong to.

    `for_member` answers "whose work is this", and the dashboard was built on it
    — which was wrong for the role most people arrive in. A guest belongs to
    nothing, so they signed in and were shown an empty screen with a queue of
    nought, on a deployment holding three public productions they are explicitly
    allowed to read, comment on and overrule.

    So: membership, plus every public project. The distinction between them does
    not disappear — `you_can_upload` still says which are somebody else's — but
    it stops being the difference between having a product and having a blank
    page.
    """
    mine = await for_member(email)
    seen = {p.project_id for p in mine}

    # Everything a reader is allowed to open, by the same rule the read guard
    # applies. Scanning `is_public` alone missed the team's own productions,
    # which are the ones actually worth showing — and left a guest staring at
    # an empty desk on a deployment full of work.
    public: list[Project] = []
    async for snapshot in jobs.db().collection(COLLECTION).stream():
        try:
            project_id = int(snapshot.id)
        except ValueError:
            continue
        if project_id in seen:
            continue
        found = await get(project_id)
        if open_to_readers(found):
            public.append(found)  # type: ignore[arg-type]

    # Theirs first, then ours. A person opens the thing they are working on, and
    # a dashboard that leads with somebody else's production reads as a
    # directory rather than as a desk.
    return mine + sorted(public, key=lambda p: p.project_id)


def open_to_readers(project: Project | None) -> bool:
    """Whether anyone at all may read this production.

    This used to be one id from config — `demo_project_id`. That id was project
    1, project 1 was deleted, and every signed-out visitor and every guest then
    landed in an empty application. A demo that depends on one row surviving
    forever is not a demo; it is a fuse.

    The rule instead: the team's own active productions are readable by anyone.
    A guest is not given a private sandbox and is not shown a curated fake —
    they see the same work the editors see, which is the thing worth showing,
    and the permission checks elsewhere still decide what they may change.

    A guest's own project stays theirs alone unless they publish it, because
    `is_staff` is false for a guest-owned production.
    """
    if project is None or project.state != "active":
        return False
    return project.is_public or members.is_staff(project.owner_email)


async def change(
    project_id: int,
    *,
    expected_rev: int,
    name: str | None = None,
    state: str | None = None,
) -> Project:
    """Rename or move through archive/trash with optimistic concurrency."""
    ref = _doc(project_id)

    @firestore.async_transactional
    async def apply(transaction) -> None:
        snapshot = await ref.get(transaction=transaction)
        if not snapshot.exists:
            raise KeyError(project_id)
        data = snapshot.to_dict() or {}
        current = int(data.get("rev", 0))
        if current != expected_rev:
            raise ProjectConflict(current)
        update: dict = {"rev": current + 1, "updated_at": datetime.now(UTC)}
        if name is not None:
            update["name"] = name
        if state is not None:
            update["state"] = state
            update[f"{state}_at"] = datetime.now(UTC)
        transaction.update(ref, update)

    await apply(jobs.db().transaction())
    found = await get(project_id, include_deleted=True)
    if found is None:
        raise KeyError(project_id)
    return found
