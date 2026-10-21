"""Canonical saved timeline routes; no model call is needed for editing."""

import asyncio
from fractions import Fraction
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Path, Query
from starlette.concurrency import run_in_threadpool

from ..config import settings
from ..evidence.contracts import EvidenceError
from ..foundation.repository import Conflict
from ..timeline.contracts import Save, Sequence, source_frame
from ..timeline.store import TimelineStore
from ..timeline.timing import prepare
from .media_library import User, authorize

router = APIRouter(prefix="/timelines", tags=["timelines"])
Key = Annotated[str, Path(pattern=r"^(film|scene-[A-Za-z0-9_-]{1,64})$")]
scan_slots = asyncio.Semaphore(2)


def store():
    return TimelineStore(settings.database_url)


@router.post("/{project}/sources/{source_id}/timing")
async def timing(project: int, source_id: UUID, principal: User) -> dict:
    await authorize(principal, project, "write")
    async with scan_slots:
        try:
            return await prepare(settings, project, source_id, principal.email)
        except (ValueError, KeyError, TypeError) as exc:
            raise EvidenceError("source_timing_unavailable") from exc


@router.get("/{project}/{sequence_id}")
async def read(
    project: int,
    sequence_id: Key,
    principal: User,
    revision: Annotated[int | None, Query(ge=1)] = None,
) -> dict:
    await authorize(principal, project, "read")
    db = store()
    snapshot = await run_in_threadpool(db.read, project, sequence_id, revision)
    return await run_in_threadpool(db.availability, project, snapshot, settings)


@router.get("/{project}/{sequence_id}/history")
async def history(
    project: int,
    sequence_id: Key,
    principal: User,
    before: Annotated[int, Query(ge=1)] = 9223372036854775807,
) -> dict:
    await authorize(principal, project, "read")
    return {"versions": await run_in_threadpool(store().history, project, sequence_id, before)}


@router.post("/{project}/{sequence_id}/revisions")
async def save(project: int, sequence_id: Key, body: Save, principal: User) -> dict:
    await authorize(principal, project, "write")
    try:
        return await run_in_threadpool(store().save, project, sequence_id, principal.email, body)
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{project}/{sequence_id}/selections")
async def selections(project: int, sequence_id: Key, principal: User) -> dict:
    await authorize(principal, project, "read")

    def build():
        db = store()
        snapshot = db.snapshot(project)
        clips, missing = [], []
        with db.connection() as conn:
            for selected in snapshot["selections"]:
                key = f"{selected['source_id']}/{selected['sha256']}"
                timing = conn.execute(
                    "SELECT body FROM state_documents WHERE project_id=%s "
                    "AND kind='source_timing' AND document_id=%s",
                    (project, key),
                ).fetchone()
                if not timing:
                    missing.append(selected["source_id"])
                    continue
                source = timing["body"]
                fps = Fraction(**source["fps"])
                start = Fraction(selected["start_us"], 1000000) * fps
                end = Fraction(selected["end_us"], 1000000) * fps
                clips.append(
                    {
                        "id": str(uuid4()),
                        "source_id": selected["source_id"],
                        "selection_id": selected["selection_id"],
                        "in_frame": start.numerator // start.denominator,
                        "out_frame": min(
                            source["frame_count"], -(-end.numerator // end.denominator)
                        ),
                        "muted": False,
                        "gain_db": 0,
                        "note": selected["text"][:300],
                    }
                )
        if missing:
            return {
                "clips": [],
                "requires_timing": sorted(set(missing)),
                "evidence_revision": snapshot["revision"],
            }
        return {
            "clips": clips,
            "requires_timing": [],
            "evidence_revision": snapshot["revision"],
            "rounding": "Evidence microseconds expand outward to source frame boundaries.",
        }

    return await run_in_threadpool(build)


@router.get("/{project}/{sequence_id}/frames/{frame}")
async def frame_map(
    project: int,
    sequence_id: Key,
    frame: int,
    principal: User,
    revision: Annotated[int, Query(ge=1)],
) -> dict:
    await authorize(principal, project, "read")
    snapshot = await run_in_threadpool(store().read, project, sequence_id, revision)
    body = snapshot["body"]
    for clip in body["clips"]:
        if clip["start_frame"] <= frame < clip["start_frame"] + clip["duration_frames"]:
            index = source_frame(
                clip, Sequence.model_validate(body["sequence"]), frame - clip["start_frame"]
            )
            return {
                "revision": revision,
                "occurrence_id": clip["id"],
                "source_id": clip["source_id"],
                "source_frame": index,
                "source_fps": clip["source"]["fps"],
            }
    raise EvidenceError("timeline_frame_not_found")
