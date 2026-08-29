"""Asking the panel to judge a setup, and reading what it decided.

Judging is a POST because it spends money and writes rows. Reading is a GET and
open to anyone on a public project, because the whole argument of this system is
that a decision with its reasons attached is worth more than a decision — and an
argument you have to sign in to check is not much of one.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ..auth import Principal, current_principal, require_member
from ..services import decisions as decisions_service
from ..services import review as review_service
from ..services.analytics import client

log = logging.getLogger(__name__)
router = APIRouter(prefix="/review", tags=["review"])


class Override(BaseModel):
    """An editor choosing a different take, and saying why.

    The reason is required by the schema, not merely encouraged. An override
    without one is the exact moment this archive exists to capture, arriving
    empty — it is the only record anywhere of a human editorial judgement, and
    the reason no model can be trained to make these calls today.
    """

    clip_id: UUID
    reason: str = Field(min_length=3, max_length=400)
    # Where the editor actually wants to use, if they narrowed it. Absent means
    # they accepted the range the panel offered.
    in_point_s: float | None = Field(default=None, ge=0)
    out_point_s: float | None = Field(default=None, ge=0)

    @field_validator("reason")
    @classmethod
    def _not_just_whitespace(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 3:
            raise ValueError("Say why, even briefly.")
        return cleaned


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
               c.proxy_uri, c.sprite_uri,
               d.criterion_names, d.criterion_scores,
               d.safe_starts_s, d.safe_ends_s, d.trim_reasons,
               c.duration_ms
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
            # The single span an assembly would use.
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
            # Per axis, never one opaque number. An editor who disagrees needs
            # to see which criterion produced the answer.
            "criteria": dict(zip(r[20], [round(float(s), 3) for s in r[21]], strict=True)),
            # Every usable stretch, not only the longest. A take with a problem
            # in the middle has two, and offering one would discard the other.
            "safe_ranges": [
                {"start_s": float(a), "end_s": float(b)}
                for a, b in zip(r[22], r[23], strict=True)
            ],
            "trim_reasons": list(r[24]),
            "duration_s": round(int(r[25] or 0) / 1000, 2),
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


@router.post("/{project_id}/{group_id}/{subgroup_id}/select", status_code=status.HTTP_201_CREATED)
async def override(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    body: Override,
    principal: Annotated[Principal, Depends(require_member)],
) -> dict:
    """An editor choosing a take, overriding or confirming the panel.

    Written as a new decision rather than an edit to the old one. The panel's
    verdict and the human's are both true things that happened, and collapsing
    them would erase the disagreement — which is the only signal this system has
    about its own accuracy, and the only data in the archive that does not exist
    anywhere else.

    Confirming the panel's choice is recorded too. "The editor agreed" is
    evidence; silence is not, and a system that only writes down disagreements
    cannot tell a good decision from an unexamined one.
    """
    await principal.assert_can_write(project_id)

    verdicts = await _verdicts_for(project_id, group_id, subgroup_id)
    if not verdicts:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This setup has not been judged yet, so there is nothing to override.",
        )

    chosen = str(body.clip_id)
    if chosen not in {v["clip_id"] for v in verdicts}:
        # Not a 404: the setup exists and was judged. The clip simply is not one
        # of its takes, which is a different mistake and worth saying so.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That clip is not one of the takes in this setup.",
        )

    previous = next((v["clip_id"] for v in verdicts if v["outcome"] == "selected"), None)
    agreed = previous == chosen

    rows = rows_for_choice(verdicts, chosen, body)

    await decisions_service.record(
        project_id=project_id,
        group_id=group_id,
        subgroup_id=subgroup_id,
        verdicts=rows,
        # Keyed on the person and the clip so a second look at the same setup
        # replaces nothing — an editor may change their mind twice, and both
        # times happened.
        key=decisions_service.run_hash(
            project_id, group_id, subgroup_id, [body.clip_id]
        ),
        model_id="",
        prompt_version="",
        decided_by="human",
        actor_id=principal.email or "",
    )

    log.info(
        "project %d scene %d setup %d: %s %s take %s",
        project_id, group_id, subgroup_id, principal.email,
        "confirmed" if agreed else "overrode to", chosen[:8],
    )

    return {
        "status": "recorded",
        "agreed_with_panel": agreed,
        "previously_recommended": previous,
        "now_selected": chosen,
    }


def rows_for_choice(verdicts: list[dict], chosen: str, body: Override) -> list[dict]:
    """One row per take, with the editor's choice marked and everything else kept.

    A function rather than inline, so a test can exercise the real construction
    instead of restating it — a restated version drifts, and the drift is
    invisible until the archive holds two shapes of the same event.
    """
    rows = []
    for v in verdicts:
        is_chosen = v["clip_id"] == chosen
        rows.append({
            "clip_id": v["clip_id"],
            "outcome": "selected" if is_chosen else "not_selected",
            # The panel's score is carried forward unchanged. It is a
            # measurement of the take, and a person disagreeing with the
            # conclusion does not change what was measured. Rewriting it to
            # justify the choice would destroy the evidence that makes the
            # disagreement worth keeping.
            "score": v["score"],
            "margin": 0.0,
            "reason": body.reason if is_chosen else "Not chosen by the editor.",
            "reason_code": "selected.clean" if is_chosen else "behind.measurement",
            # The findings stay. An editor who chose a take with a prop
            # continuity problem decided to live with it, which is a different
            # thing from the problem not being there.
            "findings": v["findings"],
            "criterion_names": v["criterion_names"],
            "criterion_scores": v["criterion_scores"],
            "safe_starts_s": v["safe_starts_s"],
            "safe_ends_s": v["safe_ends_s"],
            "trim_reasons": v["trim_reasons"],
            "in_point_s": (
                body.in_point_s if is_chosen and body.in_point_s is not None
                else v["in_point_s"]
            ),
            "out_point_s": (
                body.out_point_s if is_chosen and body.out_point_s is not None
                else v["out_point_s"]
            ),
        })
    return rows


async def _verdicts_for(project_id: int, group_id: int, subgroup_id: int) -> list[dict]:
    """The current verdict per take, whoever made it.

    LIMIT 1 BY clip_id after ordering by time, so an override supersedes the
    panel and a second override supersedes the first — without deleting either.
    """
    ch = await client()
    result = await ch.query(
        """
        SELECT clip_id, outcome, score,
               finding_codes, finding_starts_s, finding_ends_s,
               criterion_names, criterion_scores,
               safe_starts_s, safe_ends_s, trim_reasons,
               in_point_s, out_point_s
        FROM decisions
        WHERE project_id = {p:UInt32} AND group_id = {g:UInt32}
          AND subgroup_id = {s:UInt32}
        ORDER BY clip_id, decided_at DESC
        LIMIT 1 BY clip_id
        """,
        parameters={"p": project_id, "g": group_id, "s": subgroup_id},
    )

    return [
        {
            "clip_id": str(r[0]),
            "outcome": r[1],
            "score": float(r[2]),
            "findings": [
                {"code": c, "start_s": float(a), "end_s": float(b)}
                for c, a, b in zip(r[3], r[4], r[5], strict=True)
            ],
            "criterion_names": list(r[6]),
            "criterion_scores": [float(x) for x in r[7]],
            "safe_starts_s": [float(x) for x in r[8]],
            "safe_ends_s": [float(x) for x in r[9]],
            "trim_reasons": list(r[10]),
            "in_point_s": float(r[11]),
            "out_point_s": float(r[12]),
        }
        for r in result.result_rows
    ]


@router.get("/{project_id}")
async def tree(
    project_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    """Every scene and setup in a project, with enough to draw the navigation.

    One query rather than one per setup. A shoot day is dozens of setups and a
    tree that fetches each node as it opens spends a round trip per click on
    data the first query already had.

    Status is derived here rather than stored, because it is a function of three
    things that each change independently — how many takes arrived, whether the
    panel has run, and whether a person has looked. Storing it would mean three
    places that can forget to update it.
    """
    await principal.assert_can_read(project_id)

    ch = await client()
    result = await ch.query(
        """
        WITH latest AS (
            SELECT group_id, subgroup_id, clip_id,
                   argMax(outcome, decided_at)    AS outcome,
                   argMax(decided_by, decided_at) AS decided_by,
                   argMax(margin, decided_at)     AS margin
            FROM decisions
            WHERE project_id = {p:UInt32}
            GROUP BY group_id, subgroup_id, clip_id
        )
        SELECT
            c.group_id                                       AS scene,
            c.subgroup_id                                    AS setup,
            count()                                          AS takes,
            countIf(c.status = 'failed')                     AS unusable,
            anyIf(c.description, c.description != '')        AS label,
            max(l.outcome = 'selected')                      AS has_verdict,
            maxIf(l.decided_by = 'human', l.outcome = 'selected') AS reviewed,
            maxIf(l.margin, l.outcome = 'selected')           AS margin
        FROM clips AS c
        LEFT JOIN latest AS l
            ON l.group_id = c.group_id
           AND l.subgroup_id = c.subgroup_id
           AND l.clip_id = c.clip_id
        WHERE c.project_id = {p:UInt32}
        GROUP BY c.group_id, c.subgroup_id
        ORDER BY c.group_id, c.subgroup_id
        """,
        parameters={"p": project_id},
    )

    scenes: dict[int, dict] = {}
    for scene, setup, takes, unusable, label, has_verdict, reviewed, margin in result.result_rows:
        node = scenes.setdefault(int(scene), {"scene": int(scene), "setups": []})
        node["setups"].append({
            "setup": int(setup),
            "label": label or "",
            "takes": int(takes),
            "unusable": int(unusable),
            "status": _status(int(takes), bool(has_verdict), bool(reviewed), float(margin)),
            "margin": round(float(margin), 4),
        })

    return {
        "project_id": project_id,
        "scenes": sorted(scenes.values(), key=lambda s: s["scene"]),
    }


# Below this gap between first and second place, the call is close enough that a
# person should look. Mirrors the agents' review_margin; imported rather than
# repeated so the queue and the archive cannot disagree.
def _review_margin() -> float:
    from trimbin_agents.config import settings as agent_settings

    return agent_settings.review_margin


def _status(takes: int, has_verdict: bool, reviewed: bool, margin: float) -> str:
    """What the dot beside a setup means.

    Five states, and the distinction that matters most is between "decided" and
    "confirmed". A verdict nobody has looked at is not the same as one an editor
    agreed with, and a tree that shows them alike hides the only work left.
    """
    if takes < 2:
        return "too_few_takes"
    if not has_verdict:
        return "not_judged"
    if reviewed:
        return "confirmed"
    if margin < _review_margin():
        return "needs_review"
    return "decided"
