"""Independent project film sequences with revision-safe source-range snapshots."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException
from google.cloud import firestore
from pydantic import BaseModel, Field, model_validator

from . import attempts, revisions, stringout, structure
from .analytics import _many
from .jobs import db


class FilmRange(BaseModel):
    id: UUID
    clip_id: UUID
    attempt_id: UUID | None = None
    attempt_revision: int = Field(default=0, ge=0)
    start_s: float = Field(ge=0, allow_inf_nan=False)
    end_s: float = Field(gt=0, allow_inf_nan=False)
    note: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def ordered(self):
        if self.end_s <= self.start_s:
            raise ValueError("Out must be after In.")
        return self


class FilmSave(BaseModel):
    rev: int = Field(ge=0)
    command_id: UUID
    name: str = Field(default="Film sequence", min_length=1, max_length=100)
    ranges: list[FilmRange] = Field(max_length=1000)

    @model_validator(mode="after")
    def unique_rows(self):
        if len({row.id for row in self.ranges}) != len(self.ranges):
            raise ValueError("Each sequence row needs a unique id.")
        return self


class FilmSource(BaseModel):
    clip_id: UUID
    scene: int
    shot: int
    scene_code: str
    shot_code: str
    take_no: int
    duration_s: float
    fps: float
    proxy_uri: str
    sprite_uri: str


class FilmEntry(FilmRange):
    source: FilmSource | None = None
    available: bool = False
    record_start_s: float


class FilmState(BaseModel):
    project_id: int
    name: str = "Film sequence"
    rev: int = 0
    updated_by: str = ""
    updated_at: datetime | None = None
    entries: list[FilmEntry] = Field(default_factory=list)
    duration_s: float = 0


class FilmSources(BaseModel):
    sources: list[FilmSource]
    more: bool


class FilmSourceRequest(BaseModel):
    clip_ids: list[UUID] = Field(max_length=1000)


class FilmVersion(BaseModel):
    rev: int
    name: str
    updated_at: datetime


class FilmHistory(BaseModel):
    versions: list[FilmVersion]


class CoverageOmission(BaseModel):
    scene: int
    shot: int
    scene_code: str
    shot_code: str
    reason: str


class FilmCoverage(BaseModel):
    preview: FilmState
    scene_count: int
    omissions: list[CoverageOmission]


async def coverage(project_id: int) -> FilmCoverage:
    """Snapshot confirmed scene selections without changing editorial state."""
    context, observed = await asyncio.gather(
        stringout.project_context(project_id), stringout.scenes_in(project_id)
    )
    plan = context.plan
    scene_ids = sorted({s.scene for s in plan} | {s for s in observed if s > 0})
    # Bounded fan-out: a production with many scenes must not flood the archive.
    semaphore = asyncio.Semaphore(3)

    async def reel(scene_id):
        async with semaphore:
            return await stringout.scene(project_id, scene_id, context=context)

    reels = await asyncio.gather(*(reel(scene_id) for scene_id in scene_ids))
    ranges = []
    omissions = []
    for scene_id, result in zip(scene_ids, reels, strict=True):
        scene_plan = next((s for s in plan if s.scene == scene_id), None)
        selected_shots = {int(e["shot"]) for e in result["entries"]}
        declared = {s.shot for s in scene_plan.shots} if scene_plan else set()
        missing = declared - selected_shots
        missing |= {int(t["shot"]) for t in result["timeline"] if t["kind"] == "gap"}
        for shot_id in sorted(missing):
            planned_shot = (
                next((s for s in scene_plan.shots if s.shot == shot_id), None)
                if scene_plan
                else None
            )
            omissions.append(
                CoverageOmission(
                    scene=scene_id,
                    shot=shot_id,
                    scene_code=scene_plan.scene_code if scene_plan else str(scene_id),
                    shot_code=planned_shot.slug
                    if planned_shot and planned_shot.slug
                    else str(shot_id),
                    reason="No confirmed playable range",
                )
            )
        for position, entry in enumerate(result["entries"]):
            ranges.append(
                FilmRange(
                    id=uuid5(
                        NAMESPACE_URL,
                        f"trimbin/coverage/{project_id}/{scene_id}/{position}/{entry['clip_id']}",
                    ),
                    clip_id=UUID(entry["clip_id"]),
                    attempt_id=entry.get("attempt_id"),
                    attempt_revision=int(entry.get("attempt_revision", 0)),
                    start_s=entry["start_s"],
                    end_s=entry["end_s"],
                    note=str(entry.get("reason") or "")[:300],
                )
            )
    if len(ranges) > 1000:
        raise HTTPException(
            422,
            "More than 1,000 selected ranges. "
            "Preview individual scenes or create a shorter sequence.",
        )
    available = await sources(project_id, ids=list({r.clip_id for r in ranges}), limit=1000)
    preview = materialize(
        project_id,
        {
            "name": "Confirmed selects",
            "ranges": [r.model_dump(mode="json") for r in ranges],
        },
        available,
    )
    return FilmCoverage(preview=preview, scene_count=len(scene_ids), omissions=omissions)


async def history(project_id: int) -> FilmHistory:
    query = (
        db()
        .collection("film_sequences")
        .document(str(project_id))
        .collection("versions")
        .order_by("rev", direction=firestore.Query.DESCENDING)
        .limit(20)
    )
    return FilmHistory(
        versions=[FilmVersion.model_validate(s.to_dict()) async for s in query.stream()]
    )


async def read_version(project_id: int, revision: int) -> FilmState:
    ref = db().collection("film_sequences").document(str(project_id))
    snap = await ref.collection("versions").document(str(revision)).get()
    if not snap.exists:
        raise HTTPException(404, "No such saved film revision.")
    document = snap.to_dict() or {}
    ids = list({UUID(row["clip_id"]) for row in document.get("ranges", [])})
    return materialize(project_id, document, await sources(project_id, ids=ids, limit=1000))


async def sources(
    project_id: int, *, ids: list[UUID] | None = None, offset: int = 0, limit: int = 100
) -> list[FilmSource]:
    if ids == []:
        return []
    rows = await _many(
        """
        SELECT DISTINCT toString(clip_id) AS clip_id, group_id AS scene, subgroup_id AS shot,
               scene_code, shot_code, take_no, duration_ms / 1000 AS duration_s,
               fps, proxy_uri, sprite_uri
        FROM current_clip_placement
        WHERE project_id={p:UInt32} AND status='active' AND group_id > 0 AND subgroup_id > 0
    """
        + (" AND clip_id IN {ids:Array(UUID)}" if ids is not None else "")
        + """
        ORDER BY group_id, subgroup_id, take_no, clip_id
        LIMIT {limit:UInt32} OFFSET {offset:UInt32}
    """,
        {"p": project_id, "ids": ids or [], "limit": limit, "offset": offset},
    )
    plan = await structure.for_project(project_id)
    scene_codes = {s.scene: s.scene_code for s in plan}
    shot_codes = {(s.scene, h.shot): h.slug for s in plan for h in s.shots}
    for row in rows:
        row["scene_code"] = scene_codes.get(row["scene"]) or row["scene_code"] or str(row["scene"])
        row["shot_code"] = (
            shot_codes.get((row["scene"], row["shot"])) or row["shot_code"] or str(row["shot"])
        )
    return [FilmSource.model_validate(row) for row in rows]


def materialize(project_id: int, document: dict, available: list[FilmSource]) -> FilmState:
    by_id = {s.clip_id: s for s in available}
    entries = []
    position = 0.0
    for raw in document.get("ranges", []):
        item = FilmRange.model_validate(raw)
        source = by_id.get(item.clip_id)
        entries.append(
            FilmEntry(
                **item.model_dump(),
                source=source,
                available=bool(
                    source and source.proxy_uri and item.end_s <= source.duration_s + 0.001
                ),
                record_start_s=position,
            )
        )
        position += item.end_s - item.start_s
    return FilmState(
        project_id=project_id,
        name=document.get("name", "Film sequence"),
        rev=document.get("rev", 0),
        updated_by=document.get("updated_by", ""),
        updated_at=document.get("updated_at"),
        entries=entries,
        duration_s=position,
    )


async def read(project_id: int) -> FilmState:
    snap = await db().collection("film_sequences").document(str(project_id)).get()
    document = snap.to_dict() or {} if snap.exists else {}
    ids = list({UUID(row["clip_id"]) for row in document.get("ranges", [])})
    return materialize(project_id, document, await sources(project_id, ids=ids, limit=1000))


def validate_sources(ranges: list[FilmRange], available: list[FilmSource]) -> None:
    by_id = {source.clip_id: source for source in available}
    for row in ranges:
        source = by_id.get(row.clip_id)
        if not source or not source.proxy_uri:
            raise HTTPException(
                422, "A source is missing, unassigned or belongs to another project."
            )
        if row.end_s > source.duration_s + 0.001:
            raise HTTPException(422, "A selected range extends beyond its source duration.")


async def save(project_id: int, body: FilmSave, actor: str) -> FilmState:
    available = await sources(project_id, ids=list({r.clip_id for r in body.ranges}), limit=1000)
    validate_sources(body.ranges, available)
    for clip_ref, attempt_ref, attempt_rev in {
        (r.clip_id, r.attempt_id, r.attempt_revision)
        for r in body.ranges
        if r.attempt_id or r.attempt_revision
    }:
        await attempts.validate_reference(project_id, clip_ref, attempt_ref, attempt_rev)
    ref = db().collection("film_sequences").document(str(project_id))
    revision_ref = ref.collection("versions").document(str(body.rev + 1))
    payload = {
        "project_id": project_id,
        "name": body.name.strip() or "Film sequence",
        "ranges": [r.model_dump(mode="json") for r in body.ranges],
        "updated_by": actor,
        "updated_at": datetime.now(UTC),
        "command_id": str(body.command_id),
        "rev": body.rev + 1,
    }

    @firestore.async_transactional
    async def commit(transaction):
        # Every immutable version is also a persistent receipt for its command,
        # including a retry arriving after a colleague's subsequent save.
        receipt = await revision_ref.get(transaction=transaction)
        recorded = receipt.to_dict() or {} if receipt.exists else {}
        if (
            recorded.get("command_id") == str(body.command_id)
            and recorded.get("updated_by") == actor
        ):
            if (
                recorded.get("ranges") != payload["ranges"]
                or recorded.get("name") != payload["name"]
            ):
                raise HTTPException(409, "A retry key cannot be reused for a different sequence.")
            return recorded
        snap = await ref.get(transaction=transaction)
        previous = snap.to_dict() or {} if snap.exists else {}
        if (
            previous.get("command_id") == str(body.command_id)
            and previous.get("updated_by") == actor
        ):
            if (
                previous.get("ranges") != payload["ranges"]
                or previous.get("name") != payload["name"]
            ):
                raise HTTPException(409, "A retry key cannot be reused for a different sequence.")
            return previous
        revisions.check(body.rev, int(previous.get("rev", 0)))
        transaction.set(ref, payload)
        transaction.set(revision_ref, payload)
        return payload

    committed = await commit(db().transaction())
    return materialize(project_id, committed, available)
