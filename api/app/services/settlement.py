"""Settling where a clip belongs — one command, whichever screen asked.

Two paths resolve a placement: committing an ingest batch through the wizard,
and settling a row in the Placement Inbox afterwards. They are the same
decision, made in two places, and they were written twice.

That is not a tidiness complaint. The QA found that clips committed through the
wizard were queued for full-take analysis and clips settled through the inbox
were not, so whether a take ever got intelligence depended on which screen an
editor happened to use. Both paths later grew the enqueue call — but as two
copies of a sequence that has to stay in step by hand, which is the same bug
waiting for the next person who changes one of them.

So the sequence lives here once: append the placement, record the activity,
queue the analysis. Callers decide *what* was settled; this decides what
settling means.

Idempotent by construction. Placement is append-only, so a repeated settlement
writes another event that resolves to the same current state, and the analysis
queue is asked only for clips that have no analysis yet — a second call finds
none and queues nothing.
"""

from __future__ import annotations

import logging
from uuid import UUID

from . import activity, analysis_store, jobs, members, placements

log = logging.getLogger(__name__)


async def settle(
    *,
    project_id: int,
    clip_id: UUID,
    scene: int,
    shot: int,
    take_no: int,
    actor: str,
    detail: str,
    unassign: bool = False,
    verb: str = "placed",
    queue_analysis_now: bool = True,
) -> int:
    """Settle one clip and return how many analyses were queued.

    `unassign` is a state, not scene zero. Footage nobody can place yet is
    parked in its own read model rather than filed under a scene that does not
    exist — and it is not queued for analysis, because analysing a clip nobody
    has claimed spends the model's budget on a question nobody asked.
    """
    if unassign:
        await placements.unassign(project_id, clip_id, actor, detail, take_no=take_no)
    else:
        await placements.resolve(project_id, clip_id, scene, shot, actor, detail, take_no=take_no)

    await activity.record(
        project_id,
        actor,
        verb,
        detail=detail,
        scene=scene,
        shot=shot,
        actor_role=members.role_of(actor),
    )

    log.info(
        "placement settled: clip %s -> %d/%d by %s%s",
        str(clip_id)[:8],
        scene,
        shot,
        actor or "unknown",
        " (unassigned)" if unassign else "",
    )

    if unassign or not queue_analysis_now:
        # A batch defers queueing until every clip in it is settled and the job
        # is marked verified. A worker that started on the first clip while the
        # job still read unverified would be racing a state the interface has
        # not caught up with.
        return 0
    return await queue_analysis(project_id, [clip_id])


async def queue_analysis(project_id: int, clip_ids: list[UUID]) -> int:
    """Queue full-take analysis for clips that do not have it yet.

    Asked per settlement rather than per batch, and filtered against what the
    archive says is already analysed, so replaying a commit or settling the
    same row twice cannot queue the same clip again.
    """
    if not clip_ids:
        return 0
    wanted = {str(item) for item in clip_ids}
    candidates = await analysis_store.active_clips_without_analysis(project_id)
    target = [row for row in candidates if str(row["clip_id"]) in wanted]
    return await jobs.enqueue_analysis(project_id, target) if target else 0
