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
        state=SETTLED,
        detail=detail or "resolved by an editor",
    )


async def inbox(project_id: int) -> list[dict]:
    """Clips whose placement nobody has agreed with, newest first."""
    ch = await client()
    result = await ch.query(
        """
        SELECT p.clip_id, p.group_id, p.subgroup_id, p.take_no,
               p.source, p.actor, p.confidence, p.state, p.slate_raw,
               p.declared_group, p.declared_shot, p.detail, p.decided_at,
               c.proxy_uri, c.sprite_uri, c.slate_uri, c.duration_ms, c.camera,
               c.storage_uri
        FROM placement_inbox AS p
        LEFT JOIN clips AS c
            ON c.clip_id = p.clip_id AND c.project_id = p.project_id
        WHERE p.project_id = {p:UInt32}
        ORDER BY p.decided_at DESC
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
