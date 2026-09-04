"""What should I be doing — answered once, across everything.

The screen an editor opens in the morning and leaves open. It exists because the
product's central claim is only true if somebody can see it: *most of the footage
needs nobody, and here is the small part that needs you.* Said on a landing page
that is marketing. Said as a list of eleven shots with the closest call at the
top, it is the thing itself.

Everything here spans projects. A person works on three at once and a queue that
makes them check each one is a queue that gets checked once.

One query for the whole picture, then one Firestore read for the human layer on
top. The alternative — a request per project card — is the same page over a
worse network, and the archive is exactly the kind of database that answers this
shape in one pass.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from . import assessment
from . import comments as comments_service
from . import shots as shots_service
from .analytics import client

log = logging.getLogger(__name__)

# How many shots the queue offers before it stops being a queue and starts being
# a list. A person works through the top of it; the rest is reachable from the
# project itself.
QUEUE_LIMIT = 25


@dataclass(frozen=True)
class Waiting:
    """One shot that wants a person, and the reason it wants one."""

    project_id: int
    scene: int
    shot: int
    slug: str
    takes: int
    margin: float
    reason: str
    assignee: str
    state: str
    circled_take: int
    chosen_take: int
    open_comments: int

    def as_dict(self, project_names: dict[int, str]) -> dict:
        return {
            "project_id": self.project_id,
            "project_name": project_names.get(self.project_id, f"Project {self.project_id}"),
            "scene": self.scene,
            "shot": self.shot,
            "slug": self.slug,
            "takes": self.takes,
            "margin": round(self.margin, 4),
            "reason": self.reason,
            "assignee": self.assignee,
            "state": self.state,
            "circled_take": self.circled_take,
            "chosen_take": self.chosen_take,
            "open_comments": self.open_comments,
        }


def _assembled(waiting: list[Waiting], projects: list[dict], viewer: str) -> dict:
    """The answer, built in one place.

    There used to be two returns here writing the shape by hand: the real one
    and a short-circuit for somebody with no projects. They drifted — the empty
    one carried `recent` and `notes`, which this function does not produce, and
    omitted `queue_total`, which it does. Deleting every project turned Home and
    Review into a 500 with `KeyError: 'queue_total'`, on the one screen a new
    person sees first.

    One construction, so the empty case cannot have a different shape from the
    full one again.
    """
    return {
        "queue": waiting[:QUEUE_LIMIT],
        "queue_total": len(waiting),
        "projects": projects,
        "totals": {
            "waiting": len(waiting),
            "yours": sum(1 for w in waiting if w.assignee == viewer),
            "unassigned": sum(1 for w in waiting if not w.assignee),
            "projects": len([p for p in projects if p["shots"]]),
        },
    }


async def for_projects(project_ids: list[int], viewer: str) -> dict:
    """The whole morning, for one person.

    `viewer` decides only what is sorted to the top, never what is visible. A
    queue that hides other people's work would let three editors each believe
    the scene is nearly done.
    """
    if not project_ids:
        # No database call to make, but the same answer shape as if there were.
        return _assembled([], [], viewer)

    rows = await _shot_rows(project_ids)
    meta = await shots_service.for_projects(project_ids)
    margin_threshold = assessment.review_margin()

    waiting: list[Waiting] = []
    per_project: dict[int, dict] = {
        pid: {"shots": 0, "settled": 0, "waiting": 0, "scenes": set(), "takes": 0}
        for pid in project_ids
    }

    for row in rows:
        pid = row["project_id"]
        bucket = per_project.setdefault(
            pid, {"shots": 0, "settled": 0, "waiting": 0, "scenes": set(), "takes": 0}
        )
        bucket["shots"] += 1
        bucket["takes"] += row["takes"]
        bucket["scenes"].add(row["scene"])

        described = meta.get((pid, row["scene"], row["shot"]))
        circled = described.circled_take if described else 0
        state = described.state if described else ""
        assignee = described.assignee if described else ""
        slug = (described.slug if described else "") or row["shot_code"]

        reason = assessment.assess(
            takes=row["takes"],
            has_verdict=row["has_verdict"],
            confirmed=row["confirmed"],
            margin=row["margin"],
            circled_take=circled,
            chosen_take=row["chosen_take"],
            state=state,
            # The source ranges a human has chosen, from the same Firestore
            # coverage the cockpit writes and the scene reel plays.
            segments=len(described.coverage_segments) if described else 0,
            decision_fresh=(
                not described
                or not described.coverage_segments
                or (
                    bool(described.observed_source_set_hash)
                    and described.observed_source_set_hash
                    == assessment.source_set_hash(row["clip_ids"])
                )
            ),
            threshold=margin_threshold,
        ).waiting_reason

        if reason is None:
            bucket["settled"] += 1
            continue

        bucket["waiting"] += 1
        waiting.append(
            Waiting(
                project_id=pid,
                scene=row["scene"],
                shot=row["shot"],
                slug=slug,
                takes=row["takes"],
                margin=row["margin"],
                reason=reason,
                assignee=assignee,
                state=state,
                circled_take=circled,
                chosen_take=row["chosen_take"],
                open_comments=0,
            )
        )

    viewer = (viewer or "").lower()
    waiting.sort(key=lambda w: _queue_rank(w, viewer))

    projects = [
        {
            "project_id": pid,
            "shots": data["shots"],
            "scenes": len(data["scenes"]),
            "takes": data["takes"],
            "settled": data["settled"],
            "waiting": data["waiting"],
            # Null, not zero, when there is nothing to be a fraction of. A
            # project with no footage is not a project that is 0% done, and a
            # progress bar drawn at zero says something untrue about it.
            "progress_pct": (
                round(100 * data["settled"] / data["shots"], 1) if data["shots"] else None
            ),
        }
        for pid, data in per_project.items()
    ]

    return _assembled(waiting, projects, viewer)


async def recent_decisions(project_ids: list[int], limit: int = 12) -> list[dict]:
    """What the team did while you were away.

    Human decisions first and separately labelled. "Maya overruled 12B" is news;
    "the panel decided 4A" is the system working, and mixing them evenly buries
    the half that somebody might need to argue with.
    """
    if not project_ids:
        return []

    ch = await client()
    result = await ch.query(
        """
        SELECT d.project_id, d.group_id, d.subgroup_id,
               c.take_no, d.decided_by, d.actor_id, d.reason, d.decided_at,
               d.margin
        FROM decisions AS d
        LEFT JOIN current_clip_placement AS c
            ON c.clip_id = d.clip_id AND c.project_id = d.project_id
        WHERE d.project_id IN {ids:Array(UInt32)} AND d.outcome = 'selected'
        ORDER BY d.decided_at DESC
        LIMIT {n:UInt16}
        """,
        parameters={"ids": project_ids, "n": limit},
    )

    return [
        {
            "project_id": int(r[0]),
            "scene": int(r[1]),
            "shot": int(r[2]),
            "take_no": int(r[3] or 0),
            "decided_by": r[4],
            "actor": r[5],
            "reason": r[6],
            "decided_at": r[7].isoformat() if r[7] else None,
            "margin": round(float(r[8]), 4),
        }
        for r in result.result_rows
    ]


async def recent_notes(project_ids: list[int], limit: int = 8) -> list[dict]:
    return await comments_service.recent(project_ids, limit=limit)


async def _shot_rows(project_ids: list[int]) -> list[dict]:
    """Every shot across every project, with what is known about its verdict.

    The same derivation as the project tree, widened to several projects. It is
    one query rather than N because that is the entire reason for putting this
    in a column store: a hundred projects and eighty thousand shots is the same
    scan shape as one project and eight.
    """
    ch = await client()
    result = await ch.query(
        """
        WITH latest AS (
            SELECT project_id, group_id, subgroup_id, clip_id,
                   argMax(outcome, decided_at)    AS outcome,
                   argMax(decided_by, decided_at) AS decided_by,
                   argMax(margin, decided_at)     AS margin
            FROM decisions
            WHERE project_id IN {ids:Array(UInt32)}
            GROUP BY project_id, group_id, subgroup_id, clip_id
        )
        SELECT
            c.project_id,
            c.group_id,
            c.subgroup_id,
            count()                                               AS takes,
            max(
                l.clip_id != toUUID('00000000-0000-0000-0000-000000000000')
                AND l.outcome = 'selected'
            ) AS has_verdict,
            maxIf(
                l.decided_by = 'human',
                l.clip_id != toUUID('00000000-0000-0000-0000-000000000000')
                AND l.outcome = 'selected'
            ) AS confirmed,
            maxIf(
                l.margin,
                l.clip_id != toUUID('00000000-0000-0000-0000-000000000000')
                AND l.outcome = 'selected'
            ) AS margin,
            maxIf(
                c.take_no,
                l.clip_id != toUUID('00000000-0000-0000-0000-000000000000')
                AND l.outcome = 'selected'
            ) AS chosen_take,
            anyIf(c.shot_code, c.shot_code != '')                 AS shot_code,
            arraySort(groupArray(toString(c.clip_id)))            AS clip_ids
        FROM current_clip_placement AS c
        LEFT JOIN latest AS l
            ON l.project_id = c.project_id
           AND l.group_id = c.group_id
           AND l.subgroup_id = c.subgroup_id
           AND l.clip_id = c.clip_id
        WHERE c.project_id IN {ids:Array(UInt32)} AND c.status = 'active'
        GROUP BY c.project_id, c.group_id, c.subgroup_id
        ORDER BY c.project_id, c.group_id, c.subgroup_id
        """,
        parameters={"ids": project_ids},
    )

    return [
        {
            "project_id": int(r[0]),
            "scene": int(r[1]),
            "shot": int(r[2]),
            "takes": int(r[3]),
            "has_verdict": bool(r[4]),
            "confirmed": bool(r[5]),
            "margin": float(r[6]),
            "chosen_take": int(r[7] or 0),
            "shot_code": r[8] or "",
            "clip_ids": [str(item) for item in r[9]],
        }
        for r in result.result_rows
    ]


def _queue_rank(item: Waiting, viewer: str) -> tuple:
    """Yours first, then unassigned, then closest call.

    Assignment sorts above urgency on purpose. A queue that puts the tightest
    margin at the top regardless of whose shot it is sends two editors to the
    same row, which is the failure assignment was added to prevent.
    """
    mine = 0 if item.assignee == viewer else (1 if not item.assignee else 2)
    urgency = {
        "not compared yet": 0,
    }.get(item.reason, 1)
    if item.reason.startswith("director circled"):
        urgency = 0
    return (mine, urgency, item.margin, item.project_id, item.scene, item.shot)
