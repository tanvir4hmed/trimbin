"""Compatibility presentation of the single canonical frame timeline.

Older shot/scene controls keep their request shape; no second film is saved.
Human notes/selections and the timeline commit share one PostgreSQL transaction.
"""

import asyncio
import math
from datetime import UTC, datetime
from fractions import Fraction
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException

from ..config import settings
from ..evidence.contracts import EditCommand
from ..foundation.repository import Conflict
from ..timeline.contracts import Save, Sequence
from ..timeline.store import TimelineStore
from ..timeline.timing import prepare
from . import attempts, film


def presentation(project, snapshot, available):
    body = snapshot.get("body") or {}
    ranges = []
    for item in body.get("clips", []):
        fps = Fraction(**item["source"]["fps"])
        ranges.append(
            {
                "id": item["id"],
                "clip_id": item["source_id"],
                "start_s": float(Fraction(item["in_frame"]) / fps),
                "end_s": float(Fraction(item["out_frame"]) / fps),
                "note": item.get("note", ""),
                "attempt_revision": 0,
            }
        )
    return film.materialize(
        project,
        {
            "name": body.get("sequence", {}).get("name", "Film"),
            "rev": snapshot["revision"],
            "ranges": ranges,
        },
        available,
    )


async def read(project, revision=None):
    snapshot = await asyncio.to_thread(
        TimelineStore(settings.database_url).read, project, "film", revision
    )
    ids = [UUID(c["source_id"]) for c in (snapshot.get("body") or {}).get("clips", [])]
    available = await film.sources(project, ids=ids, limit=1000)
    return presentation(project, snapshot, available)


async def history(project):
    rows = await asyncio.to_thread(
        TimelineStore(settings.database_url).history, project, "film", 2**63 - 1
    )
    return film.FilmHistory(
        versions=[
            film.FilmVersion(rev=r["revision"], name="Film", updated_at=r["created_at"])
            for r in rows
        ]
    )


async def save(project, body: film.FilmSave, actor):
    def existing_receipt():
        database = TimelineStore(settings.database_url)
        with database.connection() as conn:
            database.authorize_writer(conn, project, actor)
            return database.receipt(
                conn,
                project,
                actor,
                uuid5(body.command_id, "film-compatibility"),
                body.model_dump(mode="json"),
            )

    try:
        replay = await asyncio.to_thread(existing_receipt)
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    if replay:
        return await read(project, replay["revision"])
    for item in body.ranges:
        if item.attempt_id or item.attempt_revision:
            await attempts.validate_reference(
                project, item.clip_id, item.attempt_id, item.attempt_revision
            )
    timings = {}
    for source in {r.clip_id for r in body.ranges}:
        timings[source] = await prepare(settings, project, source, actor)

    def commit():
        database = TimelineStore(settings.database_url)
        with database.connection() as conn:
            store = TimelineStore(settings.database_url, connection=conn)
            store.authorize_writer(conn, project, actor)
            receipt_id = uuid5(body.command_id, "film-compatibility")
            request = body.model_dump(mode="json")
            replay = store.receipt(conn, project, actor, receipt_id, request)
            if replay:
                return replay["revision"]
            prior = store.read(project, "film")
            if prior["revision"] != body.rev:
                raise Conflict("Film timeline changed; reload before saving")
            previous = (prior.get("body") or {}).get("sequence")
            if previous:
                sequence = Sequence.model_validate(previous)
            elif timings:
                first = next(iter(timings.values()))
                sequence = Sequence(
                    name=body.name, fps=first["fps"], width=first["width"], height=first["height"]
                )
            else:
                sequence = Sequence(name=body.name)
            sequence.name = body.name
            clips = []
            previous_clips = {c["id"]: c for c in (prior.get("body") or {}).get("clips", [])}
            for item in body.ranges:
                timing = timings[item.clip_id]
                fps = Fraction(**timing["fps"])
                first = max(0, math.floor(item.start_s * float(fps) + 1e-7))
                last = math.ceil(item.end_s * float(fps) - 1e-7)
                if last > timing["frame_count"] or last <= first:
                    raise ValueError("Source range exceeds verified frames")
                existing = previous_clips.get(str(item.id))
                if (
                    existing
                    and existing["source_id"] == str(item.clip_id)
                    and existing["in_frame"] == first
                    and existing["out_frame"] == last
                ):
                    clips.append(
                        {
                            k: existing[k]
                            for k in (
                                "id",
                                "source_id",
                                "selection_id",
                                "in_frame",
                                "out_frame",
                                "muted",
                                "gain_db",
                                "note",
                            )
                        }
                    )
                    clips[-1]["note"] = item.note
                    continue
                state = store.current(conn, project)
                note_id = uuid5(body.command_id, f"note/{item.id}")
                selection_id = uuid5(body.command_id, f"selection/{item.id}")
                store.edit(
                    project,
                    actor,
                    EditCommand(
                        command_id=note_id,
                        expected_revision=state["revision"],
                        operation="note",
                        note={
                            "source_id": item.clip_id,
                            "start_us": math.floor(Fraction(first, 1) / fps * 1000000),
                            "end_us": math.ceil(Fraction(last, 1) / fps * 1000000),
                            "kind": "moment",
                            "text": item.note or "Human approved film range",
                        },
                    ),
                )
                note_item_id = uuid5(NAMESPACE_URL, f"{project}/{actor}/{note_id}")
                state = store.current(conn, project)
                store.edit(
                    project,
                    actor,
                    EditCommand(
                        command_id=selection_id,
                        expected_revision=state["revision"],
                        operation="select",
                        item_id=note_item_id,
                    ),
                )
                clips.append(
                    {
                        "id": item.id,
                        "source_id": item.clip_id,
                        "selection_id": selection_id,
                        "in_frame": first,
                        "out_frame": last,
                        "note": item.note,
                        "muted": existing.get("muted", False) if existing else False,
                        "gain_db": existing.get("gain_db", 0) if existing else 0,
                    }
                )
            result = store.save(
                project,
                "film",
                actor,
                Save(
                    command_id=body.command_id,
                    expected_revision=body.rev,
                    sequence=sequence,
                    clips=clips,
                ),
            )
            store.remember(conn, project, actor, receipt_id, request, result)
            return result["revision"]

    try:
        revision = await asyncio.to_thread(commit)
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    result = await read(project, revision)
    return result.model_copy(update={"updated_by": actor, "updated_at": datetime.now(UTC)})
