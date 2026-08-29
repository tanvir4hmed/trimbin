"""What people said, anchored to a second of a take.

The archive has always held what was measured and what was decided. It has never
held what anyone *said* — and in every tool an editor already uses, the timecoded
comment is where the day is spent. Frame.io's whole interaction is: pause, type,
the note sticks to that frame.

ClickHouse rather than Firestore, unlike the shot brief. A brief is a thing
somebody edits four times and only the current text matters. A comment is an
event: it happened, at a time, by a person, about a frame, and it stays true
afterwards. It is also the half of the archive that can be asked questions —
"what do editors actually say when they reject a take for continuity" is
answerable from this table and nowhere else.

Nothing is edited and nothing is deleted. Resolving writes a second row, for the
same reason an override does: the disagreement is the data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from .analytics import client

log = logging.getLogger(__name__)

# A comment about the shot rather than about one take. Not null, because the
# column is not Nullable — a second file per column, paid on every read, to
# express something a reserved value says as well.
SHOT_WIDE = UUID("00000000-0000-0000-0000-000000000000")

MAX_BODY = 2000

_COLUMNS = [
    "project_id", "group_id", "subgroup_id", "clip_id",
    "comment_id", "parent_id",
    "author", "author_role", "body",
    "at_s", "to_s",
    "created_at", "resolved_by", "resolved_at",
]


@dataclass(frozen=True)
class Comment:
    comment_id: str
    parent_id: str
    clip_id: str
    author: str
    author_role: str
    body: str
    at_s: float
    to_s: float
    created_at: str
    resolved_by: str

    @property
    def is_resolved(self) -> bool:
        return bool(self.resolved_by)

    @property
    def is_shot_wide(self) -> bool:
        return self.clip_id == str(SHOT_WIDE)

    def as_dict(self) -> dict:
        return {
            "comment_id": self.comment_id,
            "parent_id": None if self.parent_id == str(SHOT_WIDE) else self.parent_id,
            "clip_id": None if self.is_shot_wide else self.clip_id,
            "author": self.author,
            "author_role": self.author_role,
            "body": self.body,
            # Both zero means the note is about the whole take, which is an
            # ordinary thing to say. The interface shows it differently from a
            # note at 0:04, and neither is a missing value.
            "at_s": round(self.at_s, 2),
            "to_s": round(self.to_s, 2),
            "whole_take": self.at_s == 0 and self.to_s == 0,
            "created_at": self.created_at,
            "resolved_by": self.resolved_by,
            "resolved": self.is_resolved,
        }


async def add(
    project_id: int,
    scene: int,
    shot: int,
    body: str,
    author: str,
    author_role: str,
    clip_id: UUID | None = None,
    at_s: float = 0.0,
    to_s: float = 0.0,
    parent_id: UUID | None = None,
) -> dict:
    """Write one comment.

    The span is kept as given rather than widened to the clip. A note that says
    "from here on" is a different note from one about the whole take, and only
    the person typing knows which they meant.
    """
    text = " ".join((body or "").split())[:MAX_BODY]
    if not text:
        raise ValueError("A comment with nothing in it is not a comment.")

    comment_id = uuid4()
    row = [
        project_id, scene, shot, clip_id or SHOT_WIDE,
        comment_id, parent_id or SHOT_WIDE,
        author, author_role, text,
        max(0.0, float(at_s)), max(0.0, float(to_s)),
        datetime.now(UTC), "", datetime.fromtimestamp(0, UTC),
    ]
    await (await client()).insert("comments", [row], column_names=_COLUMNS)
    log.info("comment on %d/%d/%d by %s", project_id, scene, shot, author)

    return {
        "comment_id": str(comment_id),
        "parent_id": str(parent_id) if parent_id else None,
        "clip_id": str(clip_id) if clip_id else None,
        "author": author,
        "author_role": author_role,
        "body": text,
        "at_s": round(float(at_s), 2),
        "to_s": round(float(to_s), 2),
        "whole_take": at_s == 0 and to_s == 0,
        "created_at": datetime.now(UTC).isoformat(),
        "resolved_by": "",
        "resolved": False,
    }


async def resolve(
    project_id: int, scene: int, shot: int, comment_id: UUID, by: str
) -> bool:
    """Mark a comment dealt with by writing it again, resolved.

    ReplacingMergeTree keyed on comment_id collapses the pair on merge and the
    read below takes the newest either way, so the table never carries two live
    versions of one note. An UPDATE would have been a mutation — a rewrite of
    every part it touches, which is the wrong shape for something a person does
    fifty times an afternoon.
    """
    ch = await client()
    result = await ch.query(
        """
        SELECT clip_id, parent_id, author, author_role, body, at_s, to_s, created_at
        FROM comments
        WHERE project_id = {p:UInt32} AND group_id = {g:UInt32}
          AND subgroup_id = {s:UInt32} AND comment_id = {c:UUID}
        ORDER BY created_at DESC
        LIMIT 1
        """,
        parameters={"p": project_id, "g": scene, "s": shot, "c": str(comment_id)},
    )
    if not result.result_rows:
        return False

    clip, parent, author, role, body, at_s, to_s, _created = result.result_rows[0]
    now = datetime.now(UTC)
    await ch.insert(
        "comments",
        [[
            project_id, scene, shot, clip,
            comment_id, parent,
            author, role, body,
            float(at_s), float(to_s),
            now, by, now,
        ]],
        column_names=_COLUMNS,
    )
    return True


async def for_shot(project_id: int, scene: int, shot: int) -> list[dict]:
    """Every comment on one shot, oldest first, replies after their parent.

    Ordered here rather than in SQL. A thread is one level deep, so the sort is
    trivial in Python and the alternative is a self-join that reads the table
    twice to produce the same eight rows.
    """
    ch = await client()
    result = await ch.query(
        """
        SELECT comment_id, parent_id, clip_id, author, author_role, body,
               at_s, to_s, created_at, resolved_by
        FROM comments
        WHERE project_id = {p:UInt32} AND group_id = {g:UInt32}
          AND subgroup_id = {s:UInt32}
        ORDER BY comment_id, created_at DESC
        LIMIT 1 BY comment_id
        """,
        parameters={"p": project_id, "g": scene, "s": shot},
    )

    found = [
        Comment(
            comment_id=str(r[0]),
            parent_id=str(r[1]),
            clip_id=str(r[2]),
            author=r[3],
            author_role=r[4],
            body=r[5],
            at_s=float(r[6]),
            to_s=float(r[7]),
            created_at=r[8].isoformat() if r[8] else "",
            resolved_by=r[9],
        )
        for r in result.result_rows
    ]

    roots = sorted(
        (c for c in found if c.parent_id == str(SHOT_WIDE)),
        key=lambda c: c.created_at,
    )
    replies: dict[str, list[Comment]] = {}
    for c in found:
        if c.parent_id != str(SHOT_WIDE):
            replies.setdefault(c.parent_id, []).append(c)

    ordered: list[dict] = []
    for root in roots:
        ordered.append(root.as_dict())
        for reply in sorted(replies.get(root.comment_id, []), key=lambda c: c.created_at):
            ordered.append({**reply.as_dict(), "is_reply": True})
    return ordered


async def counts_for_project(project_id: int) -> dict[tuple[int, int], dict]:
    """Open and total comment counts per shot, for the tree and the queue.

    One query for a whole project. The tree draws a badge per node and asking
    per node would be a round trip per shot — the exact thing the single tree
    query was written to avoid.
    """
    ch = await client()
    result = await ch.query(
        """
        WITH current AS (
            SELECT group_id, subgroup_id, comment_id,
                   argMax(resolved_by, created_at) AS resolved_by
            FROM comments
            WHERE project_id = {p:UInt32}
            GROUP BY group_id, subgroup_id, comment_id
        )
        SELECT group_id, subgroup_id, count() AS total,
               countIf(resolved_by = '') AS open
        FROM current
        GROUP BY group_id, subgroup_id
        """,
        parameters={"p": project_id},
    )
    return {
        (int(g), int(s)): {"total": int(total), "open": int(open_)}
        for g, s, total, open_ in result.result_rows
    }


async def recent(project_ids: list[int], limit: int = 20) -> list[dict]:
    """The last things said across the projects one person can open.

    For the dashboard. Three editors sharing projects need to see each other's
    notes or they answer the same question twice.
    """
    if not project_ids:
        return []

    ch = await client()
    result = await ch.query(
        """
        SELECT project_id, group_id, subgroup_id, author, body, created_at
        FROM comments
        WHERE project_id IN {ids:Array(UInt32)} AND resolved_by = ''
        ORDER BY created_at DESC
        LIMIT {n:UInt16}
        """,
        parameters={"ids": project_ids, "n": limit},
    )
    return [
        {
            "project_id": int(r[0]),
            "scene": int(r[1]),
            "shot": int(r[2]),
            "author": r[3],
            "body": r[4],
            "created_at": r[5].isoformat() if r[5] else "",
        }
        for r in result.result_rows
    ]
