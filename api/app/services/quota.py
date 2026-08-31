"""What a guest's own project may hold, and how long it keeps it.

This replaces the sandbox. The sandbox was a separate project with separate
rules, reached by a separate page, and it was wrong for a reason that took a
while to see: it sent a visitor somewhere the real users never go, and then
asked them to judge the thing they had not seen.

So the limits moved to where they belong — onto the project a guest creates, in
the same interface everybody else uses. A guest signs in, makes a project, drops
footage, and works it exactly as an editor here does. What differs is how much
of it they may keep, and that is stated on the form before they start rather
than sprung at the moment of failure.

Several limits rather than one, for the same reason as before. A byte cap does
not stop a hundred small files, a file count does not stop a hundred requests,
and a project cap does not stop one enormous clip. Together they bound the cost
of a visit; separately each is easy to walk around.

None of this is a security control. It is a cost ceiling. Anything that must not
be abused is behind a permission instead.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, status

from . import members, projects
from .analytics import client

log = logging.getLogger(__name__)

# What a signed URL for a guest project will accept. Enough for a minute of
# phone video at a generous bitrate, not enough for a camera original.
MAX_GUEST_BYTES = 400 * 1024 * 1024

# And for the company, the cap that was always here: a long take at high
# bitrate, with room.
MAX_STAFF_BYTES = 8 * 1024**3


async def owner_of(project_id: int) -> str:
    project = await projects.get(project_id)
    return project.owner_email if project else ""


async def limits_for_project(project_id: int) -> members.Limits:
    """The limits that apply inside a project, which follow its owner.

    Not the caller. An editor here invited into a guest's project is still
    working inside a guest's project, and a limit that changed depending on who
    was uploading would be a limit anybody could walk around by asking a friend.
    """
    return members.limits_for(await owner_of(project_id))


async def max_bytes_for(project_id: int) -> int:
    owner = await owner_of(project_id)
    return MAX_STAFF_BYTES if members.is_staff(owner) else MAX_GUEST_BYTES


async def check_room_for(project_id: int, incoming: int) -> None:
    """Refuse an upload that would take a project past what it may hold.

    Checked before a single byte moves and before the job is opened, so a
    refused upload leaves nothing behind to clean up.

    Counted as scenes and takes rather than as files, because those are the
    limits a person was told about. The count is approximate at this moment by
    necessity — which shot a clip belongs to is not known until the slate has
    been read — so this bounds the project's total size and the per-shot cap is
    enforced at ingest, where the answer is actually known.
    """
    limits = await limits_for_project(project_id)
    if members.is_staff(await owner_of(project_id)):
        return

    ceiling = limits.scenes * limits.takes_per_shot * 4  # a few shots per scene
    held = await clips_in(project_id)

    if held + incoming > ceiling:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"This project holds {held} clips and a guest project takes up to "
            f"{ceiling}. Everything here is a real project with real limits — "
            f"{limits.scenes} scenes, {limits.takes_per_shot} takes a shot, "
            f"clips up to {limits.clip_seconds} seconds.",
        )


async def clips_in(project_id: int) -> int:
    ch = await client()
    result = await ch.query(
        "SELECT count() FROM clips WHERE project_id = {p:UInt32}",
        parameters={"p": project_id},
    )
    return int(result.result_rows[0][0]) if result.result_rows else 0


async def takes_in_shot(project_id: int, scene: int, shot: int) -> int:
    ch = await client()
    result = await ch.query(
        """
        SELECT count() FROM current_clip_placement
        WHERE project_id = {p:UInt32} AND group_id = {g:UInt32}
          AND subgroup_id = {s:UInt32} AND status = 'active'
        """,
        parameters={"p": project_id, "g": scene, "s": shot},
    )
    return int(result.result_rows[0][0]) if result.result_rows else 0


def clip_is_too_long(duration_s: float, limits: members.Limits) -> bool:
    """Enforced after measurement, because length cannot be known before it.

    A byte cap on the signed URL bounds what can arrive; only ffmpeg can say
    whether what arrived is sixty seconds or six minutes at a low bitrate. The
    clip is rejected with a reason rather than dropped, so the person sees the
    limit rather than a gap where their footage was.
    """
    return limits.clip_seconds > 0 and duration_s > limits.clip_seconds


async def expired_clips(days: int | None = None) -> list[tuple[int, str]]:
    """Guest footage past its keep-by date.

    A visitor's footage is theirs. Keeping it forever because deleting is work
    would be the wrong default for material somebody uploaded to try something,
    and a week is long enough to come back, show a colleague, and come back
    again.

    Company projects are never swept. Zero retention days means kept, and that
    reads better here than a sentinel because it is what the field means.
    """
    limit = days if days is not None else members.GUEST_LIMITS.retention_days

    guest_ids = await _guest_project_ids()
    if not guest_ids:
        return []

    ch = await client()
    result = await ch.query(
        """
        SELECT project_id, toString(clip_id)
        FROM clips
        WHERE project_id IN {ids:Array(UInt32)}
          AND ingested_at < now() - INTERVAL {d:UInt16} DAY
        """,
        parameters={"ids": guest_ids, "d": limit},
    )
    return [(int(r[0]), str(r[1])) for r in result.result_rows]


async def _guest_project_ids() -> list[int]:
    """Projects owned by somebody who is not on the roster.

    Read from Firestore rather than inferred from an id range. A range would be
    a rule nobody could see in the data, and the first time somebody was added
    to the roster their existing projects would silently start being deleted.
    """
    from .jobs import db

    ids: list[int] = []
    async for snapshot in db().collection(projects.COLLECTION).stream():
        d = snapshot.to_dict() or {}
        if not members.is_staff(d.get("owner_email", "")):
            try:
                ids.append(int(snapshot.id))
            except ValueError:
                continue
    return ids
