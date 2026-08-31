"""The scene, assembled from the takes that were chosen.

This has a name in a cutting room: a **stringout**. It is what an assistant
editor hands the editor — every shot of the scene, in order, one take each, so
the editor can watch it as a scene instead of as a bin of ninety files.

That is the whole reason for it, and it is why this is the screen the product
was missing rather than a nice extra. Trimbin already knows which take of each
shot won and which seconds of it are usable. Not putting them end to end was
leaving the actual deliverable unbuilt.

It is not an edit. Nothing here decides where a cut goes, how long a shot holds,
or which angle the moment belongs to — those are story questions and the system
has no standing to answer them. A stringout is the raw material an editor cuts
*from*, and offering it as a cut would be claiming something untrue.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from . import assessment
from . import comments as comments_service
from . import shots as shots_service
from .analytics import client

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Entry:
    """One shot's place in the scene."""

    scene: int
    shot: int
    slug: str
    clip_id: str
    take_no: int
    start_s: float
    end_s: float
    proxy_uri: str
    sprite_uri: str
    reason: str
    decided_by: str
    actor: str
    margin: float
    needs_review: bool
    circled_take: int
    open_comments: int

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end_s - self.start_s)

    def as_dict(self) -> dict:
        return {
            "scene": self.scene,
            "shot": self.shot,
            "slug": self.slug,
            "clip_id": self.clip_id,
            "take_no": self.take_no,
            "start_s": round(self.start_s, 2),
            "end_s": round(self.end_s, 2),
            "duration_s": round(self.duration_s, 2),
            "proxy_uri": self.proxy_uri,
            "sprite_uri": self.sprite_uri,
            "reason": self.reason,
            "decided_by": self.decided_by,
            "actor": self.actor,
            "margin": round(self.margin, 4),
            "needs_review": self.needs_review,
            "circled_take": self.circled_take,
            # A shot where the room circled take 3 and the measurements chose
            # take 1 is the single most interesting row on this screen. It is
            # not an error on either side: the circle knows about performance,
            # which this system deliberately does not judge.
            "differs_from_circle": bool(
                self.circled_take and self.circled_take != self.take_no
            ),
            "open_comments": self.open_comments,
        }


async def scene(project_id: int, scene_id: int) -> dict:
    """Every shot of one scene, with the take currently standing for it.

    "Currently standing" rather than "the panel chose": an editor override is
    the newest decision and this plays what the team actually decided. A
    stringout that showed the machine's picks after a person changed them would
    be a report about the machine, not the scene.
    """
    ch = await client()
    result = await ch.query(
        """
        WITH latest AS (
            SELECT subgroup_id, clip_id,
                   argMax(outcome, decided_at)     AS outcome,
                   argMax(reason, decided_at)      AS reason,
                   argMax(decided_by, decided_at)  AS decided_by,
                   argMax(actor_id, decided_at)    AS actor,
                   argMax(margin, decided_at)      AS margin,
                   argMax(in_point_s, decided_at)  AS in_point_s,
                   argMax(out_point_s, decided_at) AS out_point_s
            FROM decisions
            WHERE project_id = {p:UInt32} AND group_id = {g:UInt32}
            GROUP BY subgroup_id, clip_id
        )
        SELECT l.subgroup_id, toString(l.clip_id), c.take_no,
               l.in_point_s, l.out_point_s,
               c.proxy_uri, c.sprite_uri,
               l.reason, l.decided_by, l.actor, l.margin,
               c.duration_ms
        FROM latest AS l
        INNER JOIN clips AS c
            ON c.clip_id = l.clip_id AND c.project_id = {p:UInt32}
        WHERE l.outcome = 'selected'
        ORDER BY l.subgroup_id
        """,
        parameters={"p": project_id, "g": scene_id},
    )

    meta = await shots_service.for_project(project_id)
    open_counts = await comments_service.counts_for_project(project_id)
    margin = assessment.review_margin()

    entries: list[Entry] = []
    for r in result.result_rows:
        shot_id = int(r[0])
        duration_s = round(int(r[11] or 0) / 1000, 2)
        start = float(r[3])
        end = float(r[4])
        if end <= start:
            # A verdict recorded before in and out points existed. Playing zero
            # seconds of it would look like the shot is missing; playing all of
            # it is what an assistant would do with a take nobody had trimmed.
            start, end = 0.0, duration_s

        described = meta.get((scene_id, shot_id))
        entries.append(
            Entry(
                scene=scene_id,
                shot=shot_id,
                slug=(described.slug if described else "") or f"{scene_id}{_letter(shot_id)}",
                clip_id=str(r[1]),
                take_no=int(r[2] or 0),
                start_s=start,
                end_s=end,
                proxy_uri=r[5] or "",
                sprite_uri=r[6] or "",
                reason=r[7] or "",
                decided_by=r[8] or "",
                actor=r[9] or "",
                margin=float(r[10]),
                # The same rule the tree and the queue use. This was
                # margin-only, so a scene could report "all settled" while the
                # dashboard listed three of its shots as waiting.
                needs_review=assessment.assess(
                    takes=2,
                    has_verdict=True,
                    confirmed=(r[8] or "") == "human",
                    margin=float(r[10]),
                    circled_take=described.circled_take if described else 0,
                    chosen_take=int(r[2] or 0),
                    state=described.state if described else "",
                    threshold=margin,
                ).needs_a_person,
                circled_take=described.circled_take if described else 0,
                open_comments=open_counts.get((scene_id, shot_id), {}).get("open", 0),
            )
        )

    return {
        "project_id": project_id,
        "scene": scene_id,
        "entries": [e.as_dict() for e in entries],
        "duration_s": round(sum(e.duration_s for e in entries), 2),
        "shots": len(entries),
        # Said plainly rather than left for the reader to count. A scene with
        # three shots still open is not a scene anybody should be watching as
        # if it were finished.
        "unresolved": sum(1 for e in entries if e.needs_review),
        "disagreements": sum(
            1 for e in entries if e.circled_take and e.circled_take != e.take_no
        ),
    }


async def scenes_in(project_id: int) -> list[int]:
    """Which scenes this project has, in order."""
    ch = await client()
    result = await ch.query(
        """
        SELECT DISTINCT group_id FROM clips
        WHERE project_id = {p:UInt32} ORDER BY group_id
        """,
        parameters={"p": project_id},
    )
    return [int(r[0]) for r in result.result_rows]


def _letter(shot_id: int) -> str:
    """A, B, C — the slate's own way of naming a camera setup.

    Only used when nobody has written a slug. A shot with no name at all reads
    as a database row; "12C" reads as a shot, and an editor can find it on the
    board.
    """
    if shot_id <= 0:
        return ""
    letters = ""
    n = shot_id
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters



