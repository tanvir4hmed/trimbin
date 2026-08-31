"""Who did what, written as it happens.

Every write in this system is attributed somewhere — a decision has an actor, a
comment has an author — but nothing collected them, so no screen could answer
"what happened on this project today". On a team of three sharing three
productions that is the question asked most often.

Recording is best-effort on purpose. An activity row failing must never fail the
action it describes: an editor whose override was refused because a log write
timed out would rightly conclude the product is broken.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from .analytics import client

log = logging.getLogger(__name__)

_COLUMNS = [
    "project_id", "group_id", "subgroup_id",
    "at", "actor", "actor_role", "verb", "detail", "quantity",
]

# What a row can say. Closed, so the feed can be read at a glance and counted.
VERBS = (
    "uploaded",
    "compared",
    "chose",
    "confirmed",
    "undid",
    "commented",
    "described",
    "circled",
    "assigned",
    "set_state",
    "planned",
)


async def record(
    project_id: int,
    actor: str,
    verb: str,
    detail: str = "",
    scene: int = 0,
    shot: int = 0,
    quantity: int = 0,
    actor_role: str = "",
) -> None:
    if verb not in VERBS:
        log.warning("unknown activity verb %r, not recorded", verb)
        return

    try:
        await (await client()).insert(
            "activity",
            [[
                project_id, scene, shot,
                datetime.now(UTC), actor or "system", actor_role,
                verb, detail[:200], max(0, int(quantity)),
            ]],
            column_names=_COLUMNS,
        )
    except Exception:
        # Never the reason an action fails.
        log.exception("could not record activity: %s %s", actor, verb)


async def for_project(project_id: int, limit: int = 40) -> list[dict]:
    ch = await client()
    result = await ch.query(
        """
        SELECT at, actor, actor_role, verb, detail, quantity, group_id, subgroup_id
        FROM activity
        WHERE project_id = {p:UInt32}
        ORDER BY at DESC
        LIMIT {n:UInt16}
        """,
        parameters={"p": project_id, "n": limit},
    )
    return [_row(project_id, r) for r in result.result_rows]


async def for_projects(project_ids: list[int], limit: int = 25) -> list[dict]:
    if not project_ids:
        return []
    ch = await client()
    result = await ch.query(
        """
        SELECT at, actor, actor_role, verb, detail, quantity, group_id, subgroup_id,
               project_id
        FROM activity
        WHERE project_id IN {ids:Array(UInt32)}
        ORDER BY at DESC
        LIMIT {n:UInt16}
        """,
        parameters={"ids": project_ids, "n": limit},
    )
    return [_row(int(r[8]), r) for r in result.result_rows]


def _row(project_id: int, r) -> dict:
    return {
        "project_id": project_id,
        "at": r[0].isoformat() if r[0] else None,
        "actor": r[1],
        "actor_role": r[2],
        "verb": r[3],
        "detail": r[4],
        "quantity": int(r[5]),
        "scene": int(r[6]),
        "shot": int(r[7]),
    }
