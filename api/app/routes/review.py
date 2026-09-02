"""One shot: what was decided about it, and everything a person does to it.

A *shot* is one camera position — 12A the wide, 12B her close-up. A *take* is one
attempt at it. That is the vocabulary a script supervisor uses when they draw a
vertical line down the page for each setup, and the vocabulary on the slate the
camera is pointed at. This file used to say "setup" for the same thing, which is
a real word on set for the same object but not the one anybody says afterwards,
and the interface was the poorer for it.

Judging is a POST because it spends money and writes rows. Reading is a GET and
open to anyone on a public project, because the whole argument of this system is
that a decision with its reasons attached is worth more than a decision — and an
argument you have to sign in to check is not much of one.

Overriding needs a name but not a membership. A guest who disagrees with the
panel is producing the single most valuable row in the archive, and refusing it
would be refusing the evidence.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from .. import schemas
from ..auth import Principal, current_principal, require_signed_in
from ..services import (
    activity,
    analysis_store,
    assessment,
    members,
    ranges,
    revisions,
    selections,
    shots,
)
from ..services import comments as comments_service
from ..services import review as review_service
from ..services.analytics import client

log = logging.getLogger(__name__)
router = APIRouter(prefix="/review", tags=["review"])


class Revised(BaseModel):
    """Base for anything that edits a shot.

    `rev` is what the caller was shown. A mismatch is a 409 carrying the current
    state, so the interface can say what changed rather than "try again". Absent
    is accepted: requiring it would break the first request after a deploy for
    every client that had not reloaded, and that costs more than the race it
    prevents on a field nobody edits concurrently.
    """

    rev: int | None = Field(default=None, ge=0)


class Override(Revised):
    """An editor choosing a different take, and saying why.

    The reason is required by the schema, not merely encouraged. An override
    without one is the exact moment this archive exists to capture, arriving
    empty — it is the only record anywhere of a human editorial judgement, and
    the reason no model can be trained to make these calls today.
    """

    # Selection changes the same shot aggregate as circle/assignment/state, so
    # it must prove which revision the editor saw. Unlike older edit routes,
    # omission is not accepted here: two people choosing a take is common.
    rev: int = Field(ge=0)
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


class UndoRequest(Revised):
    """Undo is a new selection and has the same concurrency contract."""

    rev: int = Field(ge=0)


class CoverageSegmentInput(BaseModel):
    segment_id: UUID | None = None
    clip_id: UUID
    source_in_s: float = Field(ge=0)
    source_out_s: float = Field(gt=0)


class CoverageCommand(Revised):
    rev: int = Field(ge=0)
    segments: list[CoverageSegmentInput] = Field(max_length=60)
    reason: str = Field(min_length=3, max_length=400)

    @field_validator("reason")
    @classmethod
    def _coverage_reason(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 3:
            raise ValueError("Say why, even briefly.")
        return cleaned


@router.get("/{project_id}/sources", response_model=list[schemas.SourceClip])
async def project_sources(
    project_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
    q: str = "",
    limit: int = 20,
) -> list[dict]:
    """A bounded source picker for reusing footage without moving its slate placement."""
    await principal.assert_can_read(project_id)
    needle = " ".join(q.split())[:100].lower()
    result = await (await client()).query(
        """
        SELECT toString(clip_id), group_id, subgroup_id, take_no,
               duration_ms / 1000, proxy_uri, sprite_uri, description,
               camera, fps, scene_code, shot_code
        FROM current_clip_placement
        WHERE project_id = {p:UInt32}
          AND ({q:String} = '' OR positionCaseInsensitive(description, {q:String}) > 0
               OR positionCaseInsensitive(scene_code, {q:String}) > 0
               OR positionCaseInsensitive(shot_code, {q:String}) > 0
               OR positionCaseInsensitive(toString(clip_id), {q:String}) > 0)
        ORDER BY group_id, subgroup_id, take_no
        LIMIT {limit:UInt16}
        """,
        parameters={"p": project_id, "q": needle, "limit": min(50, max(1, limit))},
    )
    return [
        {
            "clip_id": str(row[0]),
            "scene": int(row[1]),
            "shot": int(row[2]),
            "take_no": int(row[3]),
            "duration_s": float(row[4]),
            "proxy_uri": row[5] or "",
            "sprite_uri": row[6] or "",
            "description": row[7] or "",
            "camera": row[8] or "",
            "fps": float(row[9] or 0),
            "scene_code": row[10] or "",
            "shot_code": row[11] or "",
        }
        for row in result.result_rows
    ]


def _findings_from(codes, starts, ends, severities) -> list[dict]:
    """Zip the parallel arrays back into objects.

    Parallel arrays are how the column store reads them quickly; this is how an
    interface consumes them. Written once because it is now four arrays in two
    queries, and a fourth added to one of them and not the other is the kind of
    mistake that shows up as a colour rather than as an error.

    `severities` is empty on rows written before it was stored. Zipped as an
    empty string rather than defaulted to a level, because a level nobody chose
    reads exactly like one somebody did.
    """
    severities = list(severities or [])
    return [
        {
            "code": code,
            "start_s": float(start),
            "end_s": float(end),
            "severity": severities[i] if i < len(severities) else "",
        }
        for i, (code, start, end) in enumerate(zip(codes, starts, ends, strict=True))
    ]


@router.get("/{project_id}/pending")
async def pending(
    project_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    """Shots with takes and no verdict yet."""
    await principal.assert_can_read(project_id)
    found = await review_service.pending(project_id)
    return {
        "project_id": project_id,
        "pending": [
            {
                "scene": s.group_id,
                "shot": s.subgroup_id,
                "takes": len(s.clip_ids),
            }
            for s in found
        ],
    }


@router.post("/{project_id}/{group_id}/{subgroup_id}", status_code=status.HTTP_200_OK)
async def judge(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    principal: Annotated[Principal, Depends(require_signed_in)],
    force: bool = False,
) -> dict:
    """Compare every take of one shot and record the verdicts.

    For the editors who own the production. This was open to anyone signed in
    for about an hour, on the reasoning that watching the panel reach the same
    answer twice is a better demonstration than a screenshot — which is true,
    and beside the point: it is a model call on somebody else's footage, paid
    for by them, and it rewrites the verdicts every other reader is looking at.

    A guest gets the demonstration by disagreeing with the answer instead, which
    is the more interesting half anyway.

    Synchronous. A shot is a handful of takes and the fast path answers in
    seconds; queueing it would add a job to poll for an answer that has usually
    already arrived.
    """
    await principal.assert_can_curate(project_id)

    try:
        result = await review_service.judge(project_id, group_id, subgroup_id, force=force)
        await activity.record(
            project_id,
            principal.email or "",
            "compared",
            detail=f"scene {group_id} shot {subgroup_id}",
            scene=group_id,
            shot=subgroup_id,
            quantity=int(result.get("takes", 0)),
            actor_role=members.role_of(principal.email),
        )
        return result
    except review_service.NotReady as exc:
        # 409, not 400. The request is well formed and will succeed later —
        # a 400 would tell the caller to change something they cannot change.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/{project_id}/{group_id}/{subgroup_id}", response_model=schemas.Verdicts)
async def verdicts(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    """What was decided about this shot, and why.

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
               d.finding_severities,
               d.in_point_s, d.out_point_s,
               d.decided_by, d.actor_id, d.model_id, d.prompt_version,
               d.panel_convened, d.decided_at,
               c.proxy_uri, c.sprite_uri,
               d.criterion_names, d.criterion_scores,
               d.safe_starts_s, d.safe_ends_s, d.trim_reasons,
               c.duration_ms, c.camera, c.captured_at,
               c.fps, c.scene_code, c.shot_code
        FROM decisions AS d
        INNER JOIN current_clip_placement AS c
            ON c.clip_id = d.clip_id AND c.project_id = d.project_id
           AND c.group_id = d.group_id AND c.subgroup_id = d.subgroup_id
        WHERE d.project_id = {p:UInt32} AND d.group_id = {g:UInt32}
          AND d.subgroup_id = {s:UInt32}
        ORDER BY d.decided_at DESC, d.score DESC
        LIMIT 1 BY d.clip_id
        """,
        parameters={"p": project_id, "g": group_id, "s": subgroup_id},
    )

    takes = []
    for r in result.result_rows:
        takes.append(
            {
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
                "findings": _findings_from(r[7], r[8], r[9], r[10]),
                # The single span an assembly would use.
                "usable_from_s": round(float(r[11]), 2),
                "usable_to_s": round(float(r[12]), 2),
                "decided_by": r[13],
                "actor": r[14],
                "model_id": r[15],
                "prompt_version": r[16],
                "panel_convened": bool(r[17]),
                "decided_at": r[18].isoformat() if r[18] else None,
                "proxy_uri": r[19],
                "sprite_uri": r[20],
                # Per axis, never one opaque number. An editor who disagrees needs
                # to see which criterion produced the answer.
                "criteria": dict(zip(r[21], [round(float(s), 3) for s in r[22]], strict=True)),
                # Every usable stretch, not only the longest. A take with a problem
                # in the middle has two, and offering one would discard the other.
                "safe_ranges": [
                    {"start_s": float(a), "end_s": float(b)}
                    for a, b in zip(r[23], r[24], strict=True)
                ],
                "trim_reasons": list(r[25]),
                "duration_s": round(int(r[26] or 0) / 1000, 2),
                "camera": r[27] or "",
                "captured_at": r[28].isoformat() if r[28] else None,
                "fps": round(float(r[29] or 0), 3),
                "scene_code": r[30] or "",
                "shot_code": r[31] or "",
            }
        )

    if not takes:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No verdicts for this shot yet",
        )

    complete, working_findings = await analysis_store.working_findings_for_clips(
        project_id,
        [UUID(take["clip_id"]) for take in takes],
    )
    for take in takes:
        if take["clip_id"] not in complete:
            continue
        take["findings"] = working_findings.get(take["clip_id"], [])
        safe, trims = ranges.safe_ranges(float(take["duration_s"]), take["findings"])
        primary = ranges.longest(safe)
        take["safe_ranges"] = [{"start_s": span.start_s, "end_s": span.end_s} for span in safe]
        take["trim_reasons"] = trims
        take["usable_from_s"] = primary.start_s if primary else 0.0
        take["usable_to_s"] = primary.end_s if primary else 0.0

    brief = await shots.get(project_id, group_id, subgroup_id)
    if brief.selection_archive_state == "pending" and brief.selection_event_id:
        try:
            await selections.deliver(brief.selection_event_id)
            brief = await shots.get(project_id, group_id, subgroup_id)
        except Exception:
            log.exception("selection event %s is still pending", brief.selection_event_id)

    # Firestore is the mutable operational answer. ClickHouse normally contains
    # the same event by this point; if its delivery is pending, the screen still
    # shows the choice the person actually saved rather than the previous one.
    if brief.selected_clip_id and any(t["clip_id"] == brief.selected_clip_id for t in takes):
        for take in takes:
            take["outcome"] = (
                "selected" if take["clip_id"] == brief.selected_clip_id else "not_selected"
            )
    chosen = next((t for t in takes if t["outcome"] == "selected"), None)

    return {
        "project_id": project_id,
        "scene": group_id,
        "shot": subgroup_id,
        "takes": sorted(takes, key=lambda t: t["take_no"]),
        "recommended": chosen["clip_id"] if chosen else None,
        # The set's own preference, carried through to the screen where it
        # matters. Never fed to the panel: a model told which take a human liked
        # stops measuring and starts agreeing, and the agreement would then be
        # published as an independent confirmation, which it would not be.
        "circled_take": brief.circled_take,
        "circled_by": brief.circled_by,
        "differs_from_circle": bool(
            brief.circled_take and chosen and brief.circled_take != chosen["take_no"]
        ),
        "assignee": brief.assignee,
        "state": brief.state,
        "rev": brief.rev,
        "selection_archive_state": brief.selection_archive_state,
        "coverage_segments": _coverage_for_screen(brief, takes),
    }


def _coverage_for_screen(brief, takes: list[dict]) -> list[dict]:
    """Current ordered selects, with a lazy one-segment legacy bridge."""
    if brief.coverage_segments:
        return list(brief.coverage_segments)
    chosen = next((take for take in takes if take["outcome"] == "selected"), None)
    if not chosen:
        return []
    start = float(chosen.get("usable_from_s", 0) or 0)
    end = float(chosen.get("usable_to_s", 0) or 0)
    if end <= start:
        end = float(chosen.get("duration_s", 0) or 0)
    return [
        {
            "segment_id": f"legacy-{chosen['clip_id']}",
            "clip_id": chosen["clip_id"],
            "take_no": int(chosen.get("take_no", 0) or 0),
            "source_in_s": start,
            "source_out_s": end,
            "position": 0,
            "reason": chosen.get("reason", "Legacy standing take"),
            "created_by": chosen.get("actor", ""),
        }
    ]


@router.get(
    "/{project_id}/{group_id}/{subgroup_id}/coverage",
    response_model=schemas.ShotCoverage,
)
async def coverage(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    await principal.assert_can_read(project_id)
    brief = await shots.get(project_id, group_id, subgroup_id)
    verdicts_now = await _verdicts_for(project_id, group_id, subgroup_id)
    return {
        "project_id": project_id,
        "scene": group_id,
        "shot": subgroup_id,
        "rev": brief.rev,
        "segments": _coverage_for_screen(brief, verdicts_now),
    }


@router.put(
    "/{project_id}/{group_id}/{subgroup_id}/coverage",
    response_model=schemas.ShotCoverage,
)
async def set_coverage(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    body: CoverageCommand,
    principal: Annotated[Principal, Depends(require_signed_in)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    await principal.assert_can_comment(project_id)
    replayed = await revisions.replay(idempotency_key or "", principal.email or "")
    if replayed is not None:
        return replayed

    takes = await _verdicts_for(project_id, group_id, subgroup_id)
    by_clip = {str(take["clip_id"]): take for take in takes}
    missing_ids = sorted({str(item.clip_id) for item in body.segments} - set(by_clip))
    if missing_ids:
        source_rows = await (await client()).query(
            """
            SELECT toString(clip_id), take_no, duration_ms / 1000
            FROM current_clip_placement
            WHERE project_id = {p:UInt32} AND clip_id IN {clips:Array(UUID)}
            """,
            parameters={"p": project_id, "clips": missing_ids},
        )
        by_clip.update(
            {
                str(row[0]): {
                    "clip_id": str(row[0]),
                    "take_no": int(row[1]),
                    "duration_s": float(row[2]),
                }
                for row in source_rows.result_rows
            }
        )
    prepared: list[dict] = []
    for position, requested in enumerate(body.segments):
        clip_id = str(requested.clip_id)
        take = by_clip.get(clip_id)
        if take is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "A selected clip is not a take of this shot."
            )
        duration = float(take.get("duration_s", 0) or 0)
        if requested.source_out_s <= requested.source_in_s:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Every selection needs a positive range."
            )
        if duration and requested.source_out_s > duration + 0.05:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "A selection ends after its source clip."
            )
        prepared.append(
            {
                "segment_id": str(requested.segment_id or UUID(int=0))
                if requested.segment_id
                else uuid4().hex,
                "clip_id": clip_id,
                "take_no": int(take.get("take_no", 0) or 0),
                "source_in_s": round(requested.source_in_s, 3),
                "source_out_s": round(requested.source_out_s, 3),
                "position": position,
                "reason": body.reason,
                "created_by": principal.email or "",
            }
        )

    committed = await selections.commit_coverage(
        project_id,
        group_id,
        subgroup_id,
        segments=prepared,
        reason=body.reason,
        actor=principal.email or "",
        expected_rev=body.rev,
    )
    try:
        await selections.deliver(committed.event_id)
    except Exception:
        log.exception("coverage saved; event %s remains pending", committed.event_id)
    result = {
        "project_id": project_id,
        "scene": group_id,
        "shot": subgroup_id,
        "rev": committed.rev,
        "segments": prepared,
    }
    await revisions.remember(idempotency_key or "", principal.email or "", result)
    return result


@router.post(
    "/{project_id}/{group_id}/{subgroup_id}/select",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.Recorded,
)
async def override(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    body: Override,
    principal: Annotated[Principal, Depends(require_signed_in)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
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

    Open to anyone signed in, on any project they can read. That is a deliberate
    widening: a guest overruling us produces exactly the row this table was built
    for, and every version of it is kept, attributed, and undoable.
    """
    await principal.assert_can_comment(project_id)

    # A browser retries a POST it never saw the answer to — a dropped
    # connection, a closed laptop — and a second identical override lands in the
    # archive as a separate editorial decision. A replayed key returns the first
    # answer instead of doing the work again.
    replayed = await revisions.replay(idempotency_key or "", principal.email or "")
    if replayed is not None:
        return replayed

    verdicts_now = await _verdicts_for(project_id, group_id, subgroup_id)
    if not verdicts_now:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This shot has not been judged yet, so there is nothing to override.",
        )

    chosen = str(body.clip_id)
    if chosen not in {v["clip_id"] for v in verdicts_now}:
        # Not a 404: the shot exists and was judged. The clip simply is not one
        # of its takes, which is a different mistake and worth saying so.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That clip is not one of the takes in this shot.",
        )

    previous = next((v["clip_id"] for v in verdicts_now if v["outcome"] == "selected"), None)
    agreed = previous == chosen

    rows = rows_for_choice(verdicts_now, chosen, body)

    committed = await selections.commit(
        project_id,
        group_id,
        subgroup_id,
        chosen=chosen,
        fallback_previous=previous,
        reason=body.reason,
        actor=principal.email or "",
        rows=rows,
        expected_rev=body.rev,
    )
    archive_pending = False
    try:
        archive_pending = not await selections.deliver(committed.event_id)
    except Exception:
        archive_pending = True
        log.exception("selection saved; ClickHouse event %s remains pending", committed.event_id)

    log.info(
        "project %d scene %d shot %d: %s %s take %s",
        project_id,
        group_id,
        subgroup_id,
        principal.email,
        "confirmed" if agreed else "overrode to",
        chosen[:8],
    )

    take_no = next((v.get("take_no", 0) for v in verdicts_now if v["clip_id"] == chosen), 0)
    try:
        await activity.record(
            project_id,
            principal.email or "",
            "confirmed" if agreed else "chose",
            detail=body.reason,
            scene=group_id,
            shot=subgroup_id,
            quantity=int(take_no or 0),
            actor_role=members.role_of(principal.email),
        )
    except Exception:
        log.exception("selection activity row failed; selection event remains authoritative")

    result = {
        "status": "recorded",
        "agreed_with_panel": agreed,
        "previously_recommended": previous,
        "now_selected": chosen,
        "rev": committed.rev,
        "archive_pending": archive_pending,
    }
    await revisions.remember(idempotency_key or "", principal.email or "", result)
    return result


@router.post(
    "/{project_id}/{group_id}/{subgroup_id}/undo",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.Undone,
)
async def undo(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    body: UndoRequest,
    principal: Annotated[Principal, Depends(require_signed_in)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    """Put back what stood before the last human decision on this shot.

    Undo by writing forward, never by deleting. Three rows now exist: what the
    panel said, what somebody changed it to, and this — a person putting it
    back. All three are true, and an archive whose whole claim is that it
    remembers every decision cannot be the kind of archive that erases one.

    Only human decisions are undone. Rolling back the panel would mean rolling
    back to nothing, and re-running the comparison is what that button is for.

    Anyone who can choose a take can put one back, including a guest — an undo
    they cannot perform would mean a guest whose only mistake was pressing the
    wrong row has no way to correct it, and asking an editor to clean up after
    every visitor is worse than the risk.
    """
    await principal.assert_can_comment(project_id)

    replayed = await revisions.replay(idempotency_key or "", principal.email or "")
    if replayed is not None:
        return replayed

    brief = await shots.get(project_id, group_id, subgroup_id)
    revisions.check(body.rev, brief.rev)

    ch = await client()
    result = await ch.query(
        """
        SELECT clip_id, outcome, decided_by, actor_id, decided_at
        FROM decisions
        WHERE project_id = {p:UInt32} AND group_id = {g:UInt32}
          AND subgroup_id = {s:UInt32} AND outcome = 'selected'
        ORDER BY decided_at DESC
        LIMIT 2
        """,
        parameters={"p": project_id, "g": group_id, "s": subgroup_id},
    )

    newest: Any
    previous_row: Any
    if brief.selected_clip_id and brief.previous_selected_clip_id:
        newest = (UUID(brief.selected_clip_id), "selected", "human", "", None)
        previous_row = (UUID(brief.previous_selected_clip_id), "selected", "human", "", None)
    elif len(result.result_rows) >= 2:
        newest, previous_row = result.result_rows[0], result.result_rows[1]
    else:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Nothing to undo — only one decision has ever been made here.",
        )

    if newest[2] != "human":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The most recent decision here is the panel's. Run the comparison "
            "again rather than undoing it.",
        )

    restore_to = str(previous_row[0])
    verdicts_now = await _verdicts_for(project_id, group_id, subgroup_id)

    rows = rows_for_choice(
        verdicts_now,
        restore_to,
        Override(
            rev=body.rev,
            clip_id=UUID(restore_to),
            reason=(
                f"Undone by {principal.email}: put back the take that stood before the last change."
            ),
        ),
    )

    committed = await selections.commit(
        project_id,
        group_id,
        subgroup_id,
        chosen=restore_to,
        fallback_previous=str(newest[0]),
        reason=(
            f"Undone by {principal.email}: put back the take that stood before the last change."
        ),
        actor=principal.email or "",
        rows=rows,
        expected_rev=body.rev,
    )
    archive_pending = False
    try:
        archive_pending = not await selections.deliver(committed.event_id)
    except Exception:
        archive_pending = True
        log.exception("undo saved; ClickHouse event %s remains pending", committed.event_id)

    log.info(
        "project %d scene %d shot %d: %s undid a change back to %s",
        project_id,
        group_id,
        subgroup_id,
        principal.email,
        restore_to[:8],
    )
    try:
        await activity.record(
            project_id,
            principal.email or "",
            "undid",
            detail=f"scene {group_id} shot {subgroup_id}",
            scene=group_id,
            shot=subgroup_id,
            actor_role=members.role_of(principal.email),
        )
    except Exception:
        log.exception("undo activity row failed; selection event remains authoritative")
    response = {
        "status": "undone",
        "restored": restore_to,
        "undone_from": str(newest[0]),
        "rev": committed.rev,
        "archive_pending": archive_pending,
    }
    await revisions.remember(idempotency_key or "", principal.email or "", response)
    return response


def rows_for_choice(verdicts: list[dict], chosen: str, body: Override) -> list[dict]:
    """One row per take, with the editor's choice marked and everything else kept.

    A function rather than inline, so a test can exercise the real construction
    instead of restating it — a restated version drifts, and the drift is
    invisible until the archive holds two shapes of the same event.
    """
    rows = []
    for v in verdicts:
        is_chosen = v["clip_id"] == chosen
        rows.append(
            {
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
                    body.in_point_s
                    if is_chosen and body.in_point_s is not None
                    else v["in_point_s"]
                ),
                "out_point_s": (
                    body.out_point_s
                    if is_chosen and body.out_point_s is not None
                    else v["out_point_s"]
                ),
            }
        )
    return rows


async def _verdicts_for(project_id: int, group_id: int, subgroup_id: int) -> list[dict]:
    """The current verdict per take, whoever made it.

    LIMIT 1 BY clip_id after ordering by time, so an override supersedes the
    panel and a second override supersedes the first — without deleting either.
    """
    ch = await client()
    result = await ch.query(
        """
        SELECT d.clip_id, d.outcome, d.score,
               finding_codes, finding_starts_s, finding_ends_s,
               finding_severities,
               criterion_names, criterion_scores,
               safe_starts_s, safe_ends_s, trim_reasons,
               in_point_s, out_point_s, c.take_no
        FROM decisions AS d
        INNER JOIN current_clip_placement AS c
            ON c.project_id = d.project_id AND c.clip_id = d.clip_id
           AND c.group_id = d.group_id AND c.subgroup_id = d.subgroup_id
        WHERE d.project_id = {p:UInt32} AND d.group_id = {g:UInt32}
          AND d.subgroup_id = {s:UInt32}
        ORDER BY d.clip_id, d.decided_at DESC
        LIMIT 1 BY d.clip_id
        """,
        parameters={"p": project_id, "g": group_id, "s": subgroup_id},
    )

    return [
        {
            "clip_id": str(r[0]),
            "outcome": r[1],
            "score": float(r[2]),
            "findings": _findings_from(r[3], r[4], r[5], r[6]),
            "criterion_names": list(r[7]),
            "criterion_scores": [float(x) for x in r[8]],
            "safe_starts_s": [float(x) for x in r[9]],
            "safe_ends_s": [float(x) for x in r[10]],
            "trim_reasons": list(r[11]),
            "in_point_s": float(r[12]),
            "out_point_s": float(r[13]),
            "take_no": int(r[14] or 0),
        }
        for r in result.result_rows
    ]


@router.get("/{project_id}", response_model=schemas.Tree)
async def tree(
    project_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
    scene: int | None = None,
    camera: str | None = None,
    shoot_day: str | None = None,
    assignee: str | None = None,
) -> dict:
    """Every scene and shot in a project, with enough to draw the navigation.

    One query rather than one per shot. A shoot day is dozens of shots and a
    tree that fetches each node as it opens spends a round trip per click on
    data the first query already had.

    The filters are the axes a real bin is cut on: scene, camera, shoot day, and
    who is on it. A tree with one axis cannot answer "everything from Tuesday"
    or "everything on the B camera", and both are ordinary Monday questions.

    Status is derived here rather than stored, because it is a function of four
    things that each change independently — how many takes arrived, whether the
    panel has run, whether a person has looked, and whether the room circled a
    different take. Storing it would mean four places that can forget to update.
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
            c.subgroup_id                                    AS shot,
            count()                                          AS takes,
            countIf(c.status = 'failed')                     AS unusable,
            anyIf(c.description, c.description != '')        AS label,
            max(l.outcome = 'selected')                      AS has_verdict,
            maxIf(l.decided_by = 'human', l.outcome = 'selected') AS reviewed,
            maxIf(l.margin, l.outcome = 'selected')          AS margin,
            maxIf(c.take_no, l.outcome = 'selected')         AS chosen_take,
            arrayDistinct(groupArray(c.camera))              AS cameras,
            toString(min(toDate(c.captured_at)))             AS shoot_day,
            anyIf(c.scene_code, c.scene_code != '')          AS scene_code,
            anyIf(c.shot_code, c.shot_code != '')            AS shot_code
        FROM current_clip_placement AS c
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

    described = await shots.for_project(project_id)
    note_counts = await comments_service.counts_for_project(project_id)
    threshold = assessment.review_margin()

    scenes: dict[int, dict] = {}
    cameras_seen: set[str] = set()
    days_seen: set[str] = set()

    for row in result.result_rows:
        (
            scene_id,
            shot_id,
            takes,
            unusable,
            label,
            has_verdict,
            reviewed,
            margin,
            chosen_take,
            cameras,
            day,
            scene_code,
            shot_code,
        ) = row
        scene_id, shot_id = int(scene_id), int(shot_id)

        cams = [c for c in cameras if c]
        cameras_seen.update(cams)
        if day:
            days_seen.add(str(day))

        meta = described.get((scene_id, shot_id))
        circled = meta.circled_take if meta else 0
        notes = note_counts.get((scene_id, shot_id), {"total": 0, "open": 0})

        # Filters applied after the query rather than inside it. A project is
        # dozens of shots, not millions, and pushing four optional predicates
        # into the SQL would produce four branches of a string nobody can read
        # for a saving no one can measure.
        if scene is not None and scene_id != scene:
            continue
        if camera and camera not in cams:
            continue
        if shoot_day and str(day) != shoot_day:
            continue
        if assignee is not None:
            wanted = assignee.strip().lower()
            here = meta.assignee if meta else ""
            if wanted == "unassigned":
                if here:
                    continue
            elif here != wanted:
                continue

        node = scenes.setdefault(
            scene_id,
            {"scene": scene_id, "scene_code": scene_code or "", "shots": []},
        )
        node["shots"].append(
            {
                "shot": shot_id,
                "slug": (meta.slug if meta else "") or shot_code or "",
                "label": label or "",
                "takes": int(takes),
                "unusable": int(unusable),
                "status": _status(
                    int(takes),
                    bool(has_verdict),
                    bool(reviewed),
                    float(margin),
                    circled,
                    int(chosen_take or 0),
                    meta.state if meta else "",
                ),
                "state": meta.state if meta else "",
                "assignee": meta.assignee if meta else "",
                "circled_take": circled,
                "chosen_take": int(chosen_take or 0),
                "differs_from_circle": bool(
                    circled and chosen_take and circled != int(chosen_take)
                ),
                "margin": round(float(margin), 4),
                "cameras": cams,
                "shoot_day": str(day) if day else "",
                "open_notes": notes["open"],
                # How many source ranges a human has chosen for this shot, from
                # the same Firestore coverage the cockpit writes and the scene
                # reel plays. The column used to work this out from comparison
                # status and `chosen_take`, and disagreed with both of them: a
                # one-take shot reports `chosen_take` 1 whether or not anybody
                # chose anything, so the tree said "Everything is decided" beside
                # a cockpit saying a decision was required.
                "segments": len(meta.coverage_segments) if meta else 0,
            }
        )

    return {
        "project_id": project_id,
        "scenes": sorted(scenes.values(), key=lambda s: s["scene"]),
        # The axes this project actually has, so the interface offers filters
        # that will match something rather than a camera dropdown on a
        # single-camera shoot.
        "cameras": sorted(cameras_seen),
        "shoot_days": sorted(days_seen),
        "review_margin": threshold,
    }


def _status(
    takes: int,
    has_verdict: bool,
    reviewed: bool,
    margin: float,
    circled: int = 0,
    chosen: int = 0,
    state: str = "",
) -> str:
    """The dot beside a shot, from the one rule in services/assessment.py."""
    return assessment.assess(
        takes=takes,
        has_verdict=has_verdict,
        confirmed=reviewed,
        margin=margin,
        circled_take=circled,
        chosen_take=chosen,
        state=state,
    ).status


# ---------------------------------------------------------------------------
# What a shot was meant to be, and who is looking after it.
# ---------------------------------------------------------------------------


class ShotBrief(Revised):
    """What a shot was meant to be, as a person types it.

    Every field optional. A production that fills none of this in gets exactly
    what it gets today — a system that needs paperwork before it is useful is a
    system nobody opens on a Friday.

    None of it is invented by us either: this is the lined script and the
    continuity report a script supervisor already writes on every professional
    shoot. We are not asking for a new artefact; we are the first thing that
    reads one that already exists.
    """

    slug: str = Field(default="", max_length=40, description="What the slate says: 12A")
    heading: str = Field(default="", max_length=200, description="INT. APARTMENT - NIGHT")
    action: str = Field(default="", max_length=2000, description="What happens, from the script")
    line: str = Field(default="", max_length=500, description="The dialogue, if there is any")
    notes: str = Field(default="", max_length=1000, description="Continuity: props, wardrobe")
    look: str = Field(default="", max_length=60, description="handheld, locked off, dolly in")


class Circle(Revised):
    """The take the director or DoP marked on the day. Zero clears it."""

    take_no: int = Field(ge=0, le=999)


class Assignment(Revised):
    """Whose shot this is. An empty address unassigns it."""

    assignee: str = Field(default="", max_length=254)


class SetState(Revised):
    state: str = Field(default="")

    @field_validator("state")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in shots.STATES:
            raise ValueError("A shot is unset, needs_review, in_progress, or approved.")
        return value


@router.get("/{project_id}/{group_id}/{subgroup_id}/brief")
async def read_brief(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    """The shot's description and working state. Readable by anyone who can read
    the project."""
    await principal.assert_can_read(project_id)
    shot = await shots.get(project_id, group_id, subgroup_id)
    return {**shot.as_dict(), "is_empty": shot.is_empty}


@router.put("/{project_id}/{group_id}/{subgroup_id}/brief")
async def write_brief(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    body: ShotBrief,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    """Describe a shot, so the panel checks against intent rather than majority.

    Does not re-judge on its own. Comparing takes costs a model call per shot,
    and a description typed one field at a time would spend it on every
    keystroke — the editor presses compare when they are ready.
    """
    await principal.assert_can_curate(project_id)

    shot = await shots.put(
        project_id,
        group_id,
        subgroup_id,
        body.model_dump(exclude={"rev"}),
        author=principal.email or "",
        expected_rev=body.rev,
    )
    await activity.record(
        project_id,
        principal.email or "",
        "described",
        detail=body.slug or f"scene {group_id} shot {subgroup_id}",
        scene=group_id,
        shot=subgroup_id,
        actor_role=members.role_of(principal.email),
    )
    return {
        **shot.as_dict(),
        "is_empty": shot.is_empty,
        "note": (
            "Saved. Run the comparison again for the panel to use it."
            if not shot.is_empty
            else "Cleared."
        ),
    }


@router.put("/{project_id}/{group_id}/{subgroup_id}/circle")
async def circle_take(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    body: Circle,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    """Record which take the room circled.

    An editor's record of what happened on the day, so it is theirs to write. A
    guest inventing a circle on our footage would be inventing evidence — this is
    the one field here that claims something about the world rather than about
    the software.

    It never changes a verdict and is never shown to the panel. Feeding it in
    would be the end of the measurement: a model told which take a human liked
    agrees with the human, and the agreement would then be reported as an
    independent confirmation of a judgement it was handed.

    Kept out on purpose, and used on the way out instead — a shot where the
    circle and the measurements disagree goes to the top of the queue, because
    that is the shot where a person adds the most.
    """
    await principal.assert_can_curate(project_id)
    shot = await shots.circle(
        project_id,
        group_id,
        subgroup_id,
        body.take_no,
        principal.email or "",
        expected_rev=body.rev,
    )
    await activity.record(
        project_id,
        principal.email or "",
        "circled",
        detail=f"take {body.take_no}" if body.take_no else "cleared the circle",
        scene=group_id,
        shot=subgroup_id,
        quantity=body.take_no,
        actor_role=members.role_of(principal.email),
    )
    return {**shot.as_dict(), "is_empty": shot.is_empty}


@router.put("/{project_id}/{group_id}/{subgroup_id}/assignee")
async def assign_shot(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    body: Assignment,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    """Put a name on a shot, or take one off.

    Any editor on the production, to themselves or to somebody else. Restricting
    it to the lead would be how a queue stops moving on a Friday afternoon;
    opening it to guests would let a stranger reassign our work.
    """
    await principal.assert_can_curate(project_id)
    shot = await shots.assign(
        project_id, group_id, subgroup_id, body.assignee, expected_rev=body.rev
    )
    await activity.record(
        project_id,
        principal.email or "",
        "assigned",
        detail=body.assignee or "nobody",
        scene=group_id,
        shot=subgroup_id,
        actor_role=members.role_of(principal.email),
    )
    return {**shot.as_dict(), "is_empty": shot.is_empty}


@router.put("/{project_id}/{group_id}/{subgroup_id}/state")
async def set_shot_state(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    body: SetState,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    """What a person says the state of this work is.

    Alongside the derived status, never replacing it. They answer different
    questions and the tree shows both: derived says how sure the system is, set
    says whether anybody is still working on it.
    """
    await principal.assert_can_curate(project_id)
    shot = await shots.set_state(
        project_id,
        group_id,
        subgroup_id,
        body.state,
        principal.email or "",
        expected_rev=body.rev,
    )
    await activity.record(
        project_id,
        principal.email or "",
        "set_state",
        detail=body.state or "unset",
        scene=group_id,
        shot=subgroup_id,
        actor_role=members.role_of(principal.email),
    )
    return {**shot.as_dict(), "is_empty": shot.is_empty}


# ---------------------------------------------------------------------------
# What people said about it.
# ---------------------------------------------------------------------------


class NewComment(BaseModel):
    body: str = Field(min_length=1, max_length=comments_service.MAX_BODY)
    # Absent means the note is about the shot rather than one take.
    clip_id: UUID | None = None
    at_s: float = Field(default=0.0, ge=0)
    to_s: float = Field(default=0.0, ge=0)
    parent_id: UUID | None = None

    @field_validator("body")
    @classmethod
    def _has_something_in_it(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("A comment with nothing in it is not a comment.")
        return cleaned


@router.get("/{project_id}/{group_id}/{subgroup_id}/comments")
async def read_comments(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    """Every note on this shot, oldest first, replies under their parent."""
    await principal.assert_can_read(project_id)
    found = await comments_service.for_shot(project_id, group_id, subgroup_id)
    return {
        "project_id": project_id,
        "scene": group_id,
        "shot": subgroup_id,
        "comments": found,
        "open": sum(1 for c in found if not c["resolved"]),
    }


@router.post(
    "/{project_id}/{group_id}/{subgroup_id}/comments",
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    body: NewComment,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    """Say something, anchored to a second if you were watching one.

    Anyone signed in, on anything they can read. A note is additive, attributed
    and reversible; the reasons for gating uploads do not apply to it.
    """
    await principal.assert_can_comment(project_id)
    await activity.record(
        project_id,
        principal.email or "",
        "commented",
        detail=body.body,
        scene=group_id,
        shot=subgroup_id,
        actor_role=members.role_of(principal.email),
    )
    try:
        return await comments_service.add(
            project_id=project_id,
            scene=group_id,
            shot=subgroup_id,
            body=body.body,
            author=principal.email or "",
            author_role=members.role_of(principal.email),
            clip_id=body.clip_id,
            at_s=body.at_s,
            to_s=body.to_s,
            parent_id=body.parent_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/{project_id}/{group_id}/{subgroup_id}/comments/{comment_id}/resolve")
async def resolve_comment(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    comment_id: UUID,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    """Mark a note dealt with.

    Written as another row rather than an update, for the same reason an
    override is: what somebody said and the fact that it was answered are two
    events, and only keeping the second loses the first.
    """
    await principal.assert_can_comment(project_id)
    done = await comments_service.resolve(
        project_id, group_id, subgroup_id, comment_id, principal.email or ""
    )
    if not done:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such comment.")
    return {"status": "resolved", "comment_id": str(comment_id)}
