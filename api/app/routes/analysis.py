"""Full-take read model and human-correctable finding commands."""

from __future__ import annotations

import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from trimbin_agents.contracts.base import FindingCode

from .. import schemas
from ..auth import Principal, current_principal, require_signed_in
from ..services import (
    activity,
    analysis_store,
    finding_actions,
    jobs,
    members,
    ranges,
    revisions,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/analysis", tags=["analysis"])


class FindingCommand(BaseModel):
    rev: int = Field(ge=0)
    action: Literal["confirm", "dismiss", "correct", "adjust_range"]
    code: FindingCode | None = None
    detail: str | None = Field(default=None, max_length=500)
    severity: Literal["note", "attention", "blocking"] | None = None
    start_s: float | None = Field(default=None, ge=0)
    end_s: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def action_has_its_evidence(self) -> FindingCommand:
        if self.action == "correct" and not any(
            value is not None for value in (self.code, self.detail, self.severity)
        ):
            raise ValueError("correct requires a code, detail, or severity change")
        if self.action == "adjust_range" and (self.start_s is None or self.end_s is None):
            raise ValueError("adjust_range requires start_s and end_s")
        return self


def _identity(row: dict) -> dict:
    return {
        "scene": int(row["group_id"]),
        "shot": int(row["subgroup_id"]),
        "take_no": int(row["take_no"]),
        "duration_s": float(row["duration_s"]),
        "proxy_uri": str(row["proxy_uri"]),
        "sprite_uri": str(row["sprite_uri"]),
        "fps": float(row["fps"]),
        "scene_code": str(row["scene_code"]),
        "shot_code": str(row["shot_code"]),
    }


async def _read(project_id: int, clip_id: UUID) -> dict:
    archive = await analysis_store.read(project_id, clip_id)
    if not archive["clip"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such active clip in this project.")
    operational = await finding_actions.states_for_clip(project_id, clip_id)
    archive = finding_actions.overlay(archive, operational)

    duration = float(archive["clip"]["duration_s"])
    run = archive["run"] or None
    complete = bool(
        run
        and run.get("state") == "completed"
        and float(run.get("covered_until_s", 0.0)) >= max(0.0, duration - 0.05)
    )
    safe, _ = ranges.safe_ranges(duration, archive["findings"]) if complete else ([], [])
    primary = ranges.longest(safe)

    return {
        "project_id": project_id,
        "clip_id": clip_id,
        "clip": _identity(archive["clip"]),
        "run": run,
        "status": run.get("state", "not_started") if run else "not_started",
        "coverage_complete": complete,
        "description": " ".join(
            segment["description"] for segment in archive["segments"] if segment["description"]
        ),
        "segments": archive["segments"],
        "findings": archive["findings"],
        "history": archive["history"],
        "safe_ranges": [{"start_s": range_.start_s, "end_s": range_.end_s} for range_ in safe],
        "primary_usable_range": (
            {"start_s": primary.start_s, "end_s": primary.end_s} if primary else None
        ),
    }


@router.get("/{project_id}/{clip_id}", response_model=schemas.TakeAnalysis)
async def take_analysis(
    project_id: int,
    clip_id: UUID,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    """Everything Phase 2 needs to seek and draw lanes without another query."""
    await principal.assert_can_read(project_id)
    return await _read(project_id, clip_id)


@router.post(
    "/{project_id}/{clip_id}/findings/{finding_id}",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.FindingActionResult,
)
async def act_on_finding(
    project_id: int,
    clip_id: UUID,
    finding_id: UUID,
    body: FindingCommand,
    principal: Annotated[Principal, Depends(require_signed_in)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
) -> dict:
    """Confirm, dismiss, correct, or range-adjust one machine finding."""
    await principal.assert_can_comment(project_id)
    actor = principal.email or ""
    if replayed := await revisions.replay(idempotency_key, actor):
        return replayed

    read_model = await _read(project_id, clip_id)
    current = next(
        (row for row in read_model["findings"] if UUID(str(row["finding_id"])) == finding_id),
        None,
    )
    if current is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "That finding is no longer in the working view. Reload before changing it.",
        )

    duration = float(read_model["clip"]["duration_s"])
    start_s = float(body.start_s) if body.start_s is not None else float(current["start_s"])
    end_s = float(body.end_s) if body.end_s is not None else float(current["end_s"])
    if not 0 <= start_s < end_s <= duration:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"The range must satisfy 0 <= start < end <= {duration:.3f}.",
        )

    archived_action = {
        "confirm": "human_confirmed",
        "dismiss": "human_dismissed",
        "correct": "human_corrected",
        "adjust_range": "human_range_adjusted",
    }[body.action]
    changes = {
        "code": body.code.value if body.code is not None else None,
        "detail": body.detail,
        "severity": body.severity,
        "start_s": start_s if body.action == "adjust_range" else None,
        "end_s": end_s if body.action == "adjust_range" else None,
    }
    committed = await finding_actions.commit(
        project_id=project_id,
        clip_id=clip_id,
        current=current,
        action=archived_action,
        expected_rev=body.rev,
        actor=actor,
        actor_role=members.role_of(actor),
        changes=changes,
    )

    archive_pending = False
    try:
        await finding_actions.deliver(committed.event_id)
    except Exception:
        archive_pending = True
        log.exception("finding event %s remains pending", committed.event_id)

    result = {
        "status": "recorded",
        # Firestore does not serialise Python UUID objects. Keep the remembered
        # command answer JSON-shaped; the response model restores UUID typing.
        "finding_id": str(committed.finding_id),
        "event_id": str(committed.event_id),
        "action": archived_action,
        "rev": committed.rev,
        "archive_pending": archive_pending,
    }
    await revisions.remember(idempotency_key, actor, result)
    await activity.record(
        project_id,
        actor,
        archived_action,
        detail=f"{current['code']} at {start_s:.2f}-{end_s:.2f}",
        scene=int(read_model["clip"]["scene"]),
        shot=int(read_model["clip"]["shot"]),
        actor_role=members.role_of(actor),
    )
    return result


@router.post(
    "/{project_id}/backfill",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=schemas.AnalysisQueued,
)
async def backfill(
    project_id: int,
    principal: Annotated[Principal, Depends(require_signed_in)],
) -> dict:
    """Queue active legacy clips whose current run is absent or failed."""
    await principal.assert_can_curate(project_id)
    clips = await analysis_store.active_clips_without_analysis(project_id)
    queued = await jobs.enqueue_analysis(project_id, clips)
    return {"status": "queued", "project_id": project_id, "queued": queued}
