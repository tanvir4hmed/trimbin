"""Where a clip belongs, and who said so.

`clips.group_id` and `clips.subgroup_id` are part of the table's sort key, so
moving a misplaced clip cannot be an ordinary update — it means deleting the row
and reinserting it, a mutation over a partition for something a person does by
clicking a button.

So placement moved off the clip. The clip keeps where it first landed and this
records every proposal and every resolution; moving is an insert.

That is the right shape independently of the constraint. "The slate said 12C,
the folder said 12B, an editor chose 12C on Tuesday" is three facts about one
clip, and a schema that stored only the answer could not say which one you were
reading.

Nothing here moves anything on its own. A disagreement is written as `open` and
waits for a person, because relocating footage on a slate reading is the one
mistake that scatters a shoot day silently and looks like the system working.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from .analytics import client

log = logging.getLogger(__name__)

_COLUMNS = [
    "project_id",
    "clip_id",
    "group_id",
    "subgroup_id",
    "take_no",
    "at",
    "event_id",
    "occurred_at",
    "source",
    "actor",
    "confidence",
    "declared_group",
    "declared_shot",
    "slate_raw",
    "state",
    "detail",
]

# Who decided. Closed, because a free-text source column becomes six spellings
# of "slate" and then nothing can be counted.
SLATE = "slate"
FOLDER = "folder"
TIMECODE = "timecode"
FILENAME = "filename"
HUMAN = "human"

OPEN = "open"
SETTLED = "settled"
IGNORED = "ignored"


@dataclass(frozen=True)
class Placement:
    project_id: int
    clip_id: str
    group_id: int
    subgroup_id: int
    take_no: int
    source: str
    actor: str
    confidence: float
    state: str
    slate_raw: str
    declared_group: int
    declared_shot: int
    detail: str
    decided_at: str | None = None

    def as_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "clip_id": self.clip_id,
            "scene": self.group_id,
            "shot": self.subgroup_id,
            "take_no": self.take_no,
            "source": self.source,
            "actor": self.actor,
            "confidence": round(self.confidence, 3),
            "state": self.state,
            "slate_raw": self.slate_raw,
            "declared_scene": self.declared_group,
            "declared_shot": self.declared_shot,
            "detail": self.detail,
            "decided_at": self.decided_at,
        }


async def record(
    project_id: int,
    clip_id: UUID,
    scene: int,
    shot: int,
    take_no: int,
    source: str,
    *,
    actor: str = "",
    confidence: float = 0.0,
    declared_scene: int = 0,
    declared_shot: int = 0,
    slate_raw: str = "",
    state: str = SETTLED,
    detail: str = "",
) -> None:
    """Append one placement. Never replaces an earlier one."""
    occurred_at = datetime.now(UTC)
    await (await client()).insert(
        "placements",
        [
            [
                project_id,
                clip_id,
                scene,
                shot,
                take_no,
                occurred_at,
                uuid4(),
                occurred_at,
                source,
                actor,
                float(confidence),
                declared_scene,
                declared_shot,
                slate_raw[:200],
                state,
                detail[:200],
            ]
        ],
        column_names=_COLUMNS,
    )
    log.info(
        "placement %s -> %d/%d by %s (%s)",
        str(clip_id)[:8],
        scene,
        shot,
        actor or source,
        state,
    )


async def resolve(
    project_id: int,
    clip_id: UUID,
    scene: int,
    shot: int,
    actor: str,
    detail: str = "",
    *,
    take_no: int = 0,
    state: str = SETTLED,
) -> None:
    """A person settling where a clip belongs.

    Written as a new row on top of the machine's proposal rather than as an
    edit to it. Both happened, and which one an editor is looking at months
    later is exactly the question this table exists to answer.
    """
    await record(
        project_id,
        clip_id,
        scene,
        shot,
        take_no=take_no,
        source=HUMAN,
        actor=actor,
        confidence=1.0,
        state=state,
        detail=detail or "resolved by an editor",
    )


async def unassign(
    project_id: int,
    clip_id: UUID,
    actor: str,
    detail: str = "left unassigned",
    *,
    take_no: int = 0,
) -> None:
    """Park footage outside project structure without inventing Scene 0 / Shot 0."""
    await resolve(
        project_id,
        clip_id,
        0,
        0,
        actor,
        detail,
        take_no=take_no,
        state=IGNORED,
    )


async def unassigned(project_id: int) -> list[dict]:
    """Footage a human deliberately kept outside canonical scene/shot structure."""
    result = await (await client()).query(
        """
        SELECT toString(clip_id), proxy_uri, sprite_uri, slate_uri, duration_ms,
               camera, fps, take_no, actor, detail, decided_at, storage_uri,
               scene_code, shot_code
        FROM current_unassigned_clips
        WHERE project_id = {p:UInt32}
        ORDER BY decided_at DESC
        LIMIT 500
        """,
        parameters={"p": project_id},
    )
    return [
        {
            "clip_id": r[0],
            "proxy_uri": r[1] or "",
            "sprite_uri": r[2] or "",
            "slate_uri": r[3] or "",
            "duration_s": round(int(r[4] or 0) / 1000, 2),
            "camera": r[5] or "",
            "fps": round(float(r[6] or 0), 3),
            "take_no": int(r[7] or 0),
            "actor": r[8] or "",
            "detail": r[9] or "",
            "decided_at": r[10].isoformat() if r[10] else None,
            "filename": (r[11] or "").rsplit("/", 1)[-1],
            "scene_code": r[12] or "",
            "shot_code": r[13] or "",
        }
        for r in result.result_rows
    ]


async def inbox(project_id: int) -> list[dict]:
    """Clips whose placement nobody has agreed with, newest first."""
    ch = await client()
    result = await ch.query(
        """
        SELECT p.clip_id, p.group_id, p.subgroup_id, p.take_no,
               p.source, p.actor, p.confidence, p.state, p.slate_raw,
               p.declared_group, p.declared_shot, p.detail, p.decided_at,
               c.proxy_uri, c.sprite_uri, c.slate_uri, c.duration_ms, c.camera,
               c.storage_uri,
               -- The take these bytes already occupy, if a settled one exists.
               -- Structural, not re-parsed out of `detail`, so the interface
               -- can offer Replace without guessing at free text. Only a
               -- *settled* duplicate counts: two unresolved copies sitting in
               -- the inbox together are not occupying anything yet.
               dup.clip_id, dup.group_id, dup.subgroup_id, dup.take_no
        FROM placement_inbox AS p
        LEFT JOIN clips AS c
            ON c.clip_id = p.clip_id AND c.project_id = p.project_id
        LEFT JOIN current_clip_placement AS dup
            ON dup.project_id = p.project_id
            AND dup.content_hash = c.content_hash
            AND dup.content_hash != ''
            AND dup.clip_id != p.clip_id
            AND dup.group_id > 0 AND dup.subgroup_id > 0
        WHERE p.project_id = {p:UInt32}
        ORDER BY p.decided_at DESC
        LIMIT 1 BY p.clip_id
        LIMIT 500
        """,
        parameters={"p": project_id},
    )

    return [
        {
            "clip_id": str(r[0]),
            "scene": int(r[1]),
            "shot": int(r[2]),
            "take_no": int(r[3]),
            "source": r[4],
            "actor": r[5],
            "confidence": round(float(r[6]), 3),
            "state": r[7],
            "slate_raw": r[8],
            "declared_scene": int(r[9]),
            "declared_shot": int(r[10]),
            "detail": r[11],
            "decided_at": r[12].isoformat() if r[12] else None,
            "proxy_uri": r[13] or "",
            "sprite_uri": r[14] or "",
            "slate_uri": r[15] or "",
            "duration_s": round(int(r[16] or 0) / 1000, 2),
            "camera": r[17] or "",
            # The filename the editor dragged in, recovered from the object
            # path. A uuid tells them nothing about which file to look at.
            "filename": (r[18] or "").rsplit("/", 1)[-1],
            # A LEFT JOIN with no match gives the UUID column's zero value, not
            # NULL — the same sentinel this system already uses elsewhere for
            # "no placement event exists". `duplicate_scene` is the honest
            # signal; it is 0 exactly when the join found nothing.
            "duplicate_of": str(r[19]) if int(r[20]) > 0 else "",
            "duplicate_scene": int(r[20]),
            "duplicate_shot": int(r[21]),
            "duplicate_take": int(r[22]),
        }
        for r in result.result_rows
    ]


async def current(project_id: int) -> dict[str, tuple[int, int]]:
    """Where every clip in a project currently sits.

    This is mainly useful to callers that need a compact map. Operational SQL
    should read `current_clip_placement`, the canonical relation that also
    includes clips without a placement event.
    """
    ch = await client()
    result = await ch.query(
        """
        SELECT toString(clip_id), group_id, subgroup_id
        FROM current_clip_placement
        WHERE project_id = {p:UInt32}
        """,
        parameters={"p": project_id},
    )
    return {r[0]: (int(r[1]), int(r[2])) for r in result.result_rows}


async def duplicates_of(project_id: int, content_hash: str) -> list[str]:
    """Clips already here with the same bytes.

    The same file dragged in twice, whatever it is called. Reported, never
    deleted — an editor who uploaded a file twice on purpose is doing something
    we have no standing to undo.
    """
    if not content_hash:
        return []

    ch = await client()
    result = await ch.query(
        """
        SELECT toString(clip_id) FROM clips
        WHERE project_id = {p:UInt32} AND content_hash = {h:String}
          AND status != 'failed'
        LIMIT 10
        """,
        parameters={"p": project_id, "h": content_hash},
    )
    return [r[0] for r in result.result_rows]


async def settled_duplicate(project_id: int, clip_id: UUID) -> dict | None:
    """The take this clip's bytes are already occupying, if any.

    Reported at ingest as a flag in a job that expires; the inbox needed the
    same fact structurally, not re-parsed out of a detail string, so a
    "Replace" action can act on it. Only a *settled* duplicate counts — a
    second copy still waiting in the inbox itself is not occupying a shot, and
    there is nothing yet to replace.

    Looked up fresh rather than trusted from an earlier listing: the duplicate
    could have been moved, replaced, or unassigned between the inbox being read
    and this clip being resolved, and acting on a stale answer is exactly the
    silent-relocation mistake this whole table exists to prevent.
    """
    ch = await client()
    result = await ch.query(
        """
        SELECT toString(dup.clip_id), dup.group_id, dup.subgroup_id, dup.take_no
        FROM clips AS c
        INNER JOIN current_clip_placement AS dup
            ON dup.project_id = c.project_id
            AND dup.content_hash = c.content_hash
        WHERE c.project_id = {p:UInt32} AND c.clip_id = {id:UUID}
          AND c.content_hash != ''
          AND dup.clip_id != c.clip_id
          AND dup.group_id > 0 AND dup.subgroup_id > 0
        ORDER BY dup.ingested_at DESC
        LIMIT 1
        """,
        parameters={"p": project_id, "id": str(clip_id)},
    )
    if not result.result_rows:
        return None
    row = result.result_rows[0]
    return {
        "clip_id": row[0],
        "scene": int(row[1]),
        "shot": int(row[2]),
        "take_no": int(row[3]),
    }
