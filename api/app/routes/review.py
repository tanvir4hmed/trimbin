"""Asking the panel to judge a setup, and reading what it decided.

Judging is a POST because it spends money and writes rows. Reading is a GET and
open to anyone on a public project, because the whole argument of this system is
that a decision with its reasons attached is worth more than a decision — and an
argument you have to sign in to check is not much of one.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import Principal, current_principal, require_member
from ..services import review as review_service
from ..services.analytics import client

log = logging.getLogger(__name__)
router = APIRouter(prefix="/review", tags=["review"])


@router.get("/{project_id}/pending")
async def pending(
    project_id: int,
    principal: Annotated[Principal, Depends(require_member)],
) -> dict:
    """Setups with takes and no verdict yet."""
    await principal.assert_can_read(project_id)
    setups = await review_service.pending(project_id)
    return {
        "project_id": project_id,
        "pending": [
            {
                "scene": s.group_id,
                "setup": s.subgroup_id,
                "takes": len(s.clip_ids),
            }
            for s in setups
        ],
    }


@router.post("/{project_id}/{group_id}/{subgroup_id}", status_code=status.HTTP_200_OK)
async def judge(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    principal: Annotated[Principal, Depends(require_member)],
    force: bool = False,
) -> dict:
    """Compare every take of one setup and record the verdicts.

    Synchronous. A setup is a handful of takes and the fast path answers in
    seconds; queueing it would add a job to poll for an answer that has usually
    already arrived. A full panel on a large setup is slower, which is what the
    long request timeout on this service is for.
    """
    await principal.assert_can_write(project_id)

    try:
        return await review_service.judge(project_id, group_id, subgroup_id, force=force)
    except review_service.NotReady as exc:
        # 409, not 400. The request is well formed and will succeed later —
        # a 400 would tell the caller to change something they cannot change.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/{project_id}/{group_id}/{subgroup_id}")
async def verdicts(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    """What was decided about this setup, and why.

    Every take, not only the winner. "Why not that one?" is the question this
    endpoint exists to answer, and it is asked months later by someone who was
    not in the room.
    """
    await principal.assert_can_read(project_id)

    ch = await client()
    result = await ch.query(
        """
        SELECT d.clip_id, c.take_no, d.outcome, d.score, d.margin,
               d.reason, d.reason_code,
               d.finding_codes, d.finding_starts_s, d.finding_ends_s,
               d.in_point_s, d.out_point_s,
               d.decided_by, d.actor_id, d.model_id, d.prompt_version,
               d.panel_convened, d.decided_at,
               c.proxy_uri, c.sprite_uri
        FROM decisions AS d
        LEFT JOIN clips AS c ON c.clip_id = d.clip_id AND c.project_id = d.project_id
        WHERE d.project_id = {p:UInt32} AND d.group_id = {g:UInt32}
          AND d.subgroup_id = {s:UInt32}
        ORDER BY d.decided_at DESC, d.score DESC
        LIMIT 1 BY d.clip_id
        """,
        parameters={"p": project_id, "g": group_id, "s": subgroup_id},
    )

    takes = []
    for r in result.result_rows:
        takes.append({
            "clip_id": str(r[0]),
            "take_no": int(r[1] or 0),
            "outcome": r[2],
            "score": round(float(r[3]), 4),
            "margin": round(float(r[4]), 4),
            "reason": r[5],
            "reason_code": r[6],
            # Zipped back into objects here rather than stored that way. The
            # arrays are how ClickHouse reads them quickly; this is how an
            # interface consumes them.
            "findings": [
                {"code": c, "start_s": float(a), "end_s": float(b)}
                for c, a, b in zip(r[7], r[8], r[9], strict=True)
            ],
            "usable_from_s": round(float(r[10]), 2),
            "usable_to_s": round(float(r[11]), 2),
            "decided_by": r[12],
            "actor": r[13],
            "model_id": r[14],
            "prompt_version": r[15],
            "panel_convened": bool(r[16]),
            "decided_at": r[17].isoformat() if r[17] else None,
            "proxy_uri": r[18],
            "sprite_uri": r[19],
        })

    if not takes:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No verdicts for this setup yet",
        )

    return {
        "project_id": project_id,
        "scene": group_id,
        "setup": subgroup_id,
        "takes": sorted(takes, key=lambda t: t["take_no"]),
        "recommended": next(
            (t["clip_id"] for t in takes if t["outcome"] == "selected"), None
        ),
    }
