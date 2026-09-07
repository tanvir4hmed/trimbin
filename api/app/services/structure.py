"""Scenes and shots a person declares, before any footage exists.

A production is planned before it is shot. The scene list comes from the script
and the shot list from the director; both exist on paper on day one. Discovering
them from slates works and is not the only way anyone wants to work — an editor
setting up a project should be able to lay out scene 12 with shots A to E and
then drop footage into a named place.

Declared structure also gives ingest something to check against. A clip dropped
into shot 12C whose slate reads 15B is in the wrong folder, and that is worth
saying at upload rather than discovering in the cut.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import HTTPException
from google.cloud import firestore

from .jobs import db

log = logging.getLogger(__name__)

COLLECTION = "scenes"

MAX_HEADING = 200
MAX_SLUG = 40


@dataclass
class PlannedShot:
    shot: int
    slug: str = ""
    description: str = ""


@dataclass
class Scene:
    project_id: int
    scene: int
    scene_code: str = ""
    heading: str = ""
    shots: list[PlannedShot] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict:
        return {
            "scene": self.scene,
            "scene_code": self.scene_code or str(self.scene),
            "heading": self.heading,
            "shots": [
                {"shot": s.shot, "slug": s.slug, "description": s.description} for s in self.shots
            ],
        }


def _doc(project_id: int, scene: int):
    return db().collection(COLLECTION).document(f"p{project_id}_s{scene}")


def _clean(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


async def add_scene(project_id: int, scene: int, heading: str, scene_code: str = "") -> Scene:
    return await _edit_scene(
        project_id,
        scene,
        lambda existing: {
            **existing,
            "scene_code": _clean(scene_code, MAX_SLUG) or existing.get("scene_code") or str(scene),
            "heading": _clean(heading, MAX_HEADING),
        },
    )


async def _edit_scene(project_id: int, scene: int, change: Callable[[dict], dict]) -> Scene:
    lock = db().collection("structure_locks").document(str(project_id))

    @firestore.async_transactional
    async def write(transaction):
        lock_snapshot = await lock.get(transaction=transaction)
        version = (lock_snapshot.to_dict() or {}).get("rev", 0)
        allocated = scene
        if not allocated:
            existing_scenes = [
                s.to_dict() or {}
                async for s in db()
                .collection(COLLECTION)
                .where("project_id", "==", project_id)
                .stream(transaction=transaction)
            ]
            allocated = max((int(s["scene"]) for s in existing_scenes), default=0) + 1
            if allocated > 9999:
                raise HTTPException(422, "This project has reached its scene limit.")
        ref = _doc(project_id, allocated)
        snapshot = await ref.get(transaction=transaction)
        existing = snapshot.to_dict() or {} if snapshot.exists else {}
        base = {
            "project_id": project_id,
            "scene": allocated,
            "scene_code": str(allocated),
            "heading": "",
            "shots": [],
            "created_at": datetime.now(UTC),
            **existing,
        }
        changed = change(base)
        transaction.set(ref, changed)
        transaction.set(lock, {"rev": version + 1})
        return changed

    return _from_doc(project_id, await write(db().transaction()))


async def add_shot(project_id: int, scene: int, shot: int, slug: str, description: str) -> Scene:
    """Add or replace one shot in a scene. Creates the scene if it is new."""

    def change(existing):
        shots = [s for s in existing.get("shots", []) if int(s.get("shot", 0)) != shot]
        shots.append(
            {
                "shot": shot,
                "slug": _clean(slug, MAX_SLUG),
                "description": _clean(description, MAX_HEADING),
            }
        )
        return {**existing, "shots": sorted(shots, key=lambda s: int(s["shot"]))}

    return await _edit_scene(project_id, scene, change)


async def remove_shot(project_id: int, scene: int, shot: int) -> Scene:
    return await _edit_scene(
        project_id,
        scene,
        lambda d: {**d, "shots": [s for s in d.get("shots", []) if int(s.get("shot", 0)) != shot]},
    )


async def get(project_id: int, scene: int) -> Scene:
    snapshot = await _doc(project_id, scene).get()
    if not snapshot.exists:
        return Scene(project_id=project_id, scene=scene)
    return _from_doc(project_id, snapshot.to_dict() or {})


async def for_project(project_id: int) -> list[Scene]:
    found: list[Scene] = []
    async for snapshot in (
        db().collection(COLLECTION).where("project_id", "==", project_id).stream()
    ):
        found.append(_from_doc(project_id, snapshot.to_dict() or {}))
    return sorted(found, key=lambda s: s.scene)


def _from_doc(project_id: int, d: dict) -> Scene:
    return Scene(
        project_id=project_id,
        scene=int(d.get("scene", 0)),
        scene_code=d.get("scene_code", "") or str(d.get("scene", 0)),
        heading=d.get("heading", ""),
        shots=[
            PlannedShot(
                shot=int(s.get("shot", 0)),
                slug=s.get("slug", ""),
                description=s.get("description", ""),
            )
            for s in sorted(d.get("shots", []), key=lambda x: int(x.get("shot", 0)))
        ],
        created_at=d.get("created_at") or datetime.now(UTC),
    )


async def next_scene_number(project_id: int) -> int:
    scenes = await for_project(project_id)
    return max((s.scene for s in scenes), default=0) + 1


async def next_shot_number(project_id: int, scene: int) -> int:
    found = await get(project_id, scene)
    return max((s.shot for s in found.shots), default=0) + 1


def _normalise_code(value: str) -> str:
    """Compare production codes without changing what the user sees."""
    return " ".join((value or "").strip().upper().split())


async def ensure_slate_codes(project_id: int, scene_code: str, shot_code: str) -> tuple[int, int]:
    """Resolve or create an explicit slate identity, serializing batch workers.

    Empty or ambiguous codes remain unassigned. Punctuation is significant:
    `12A-PU` must not silently become a different production's `12APU`.
    """
    scene_code = _clean(scene_code, MAX_SLUG)
    shot_code = _clean(shot_code, MAX_SLUG)
    if not scene_code or not shot_code:
        return 0, 0
    lock = db().collection("structure_locks").document(str(project_id))

    @firestore.async_transactional
    async def ensure(transaction):
        lock_snapshot = await lock.get(transaction=transaction)
        version = (lock_snapshot.to_dict() or {}).get("rev", 0)
        documents = [
            snapshot
            async for snapshot in db()
            .collection(COLLECTION)
            .where("project_id", "==", project_id)
            .stream(transaction=transaction)
        ]
        existing = [snapshot.to_dict() or {} for snapshot in documents]
        matches = [
            s
            for s in existing
            if _normalise_code(s.get("scene_code") or str(s["scene"]))
            == _normalise_code(scene_code)
        ]
        if len(matches) > 1:
            return 0, 0
        data = (
            dict(matches[0])
            if matches
            else {
                "project_id": project_id,
                "scene": max((int(s["scene"]) for s in existing), default=0) + 1,
                "scene_code": scene_code,
                "heading": "",
                "shots": [],
                "created_at": datetime.now(UTC),
            }
        )
        shots = list(data.get("shots", []))
        found = [
            s
            for s in shots
            if _normalise_code(s.get("slug") or str(s["shot"])) == _normalise_code(shot_code)
        ]
        if len(found) > 1:
            return 0, 0
        if found:
            return int(data["scene"]), int(found[0]["shot"])
        shot_id = max((int(s["shot"]) for s in shots), default=0) + 1
        if int(data["scene"]) > 9999 or shot_id > 999:
            return 0, 0
        shots.append({"shot": shot_id, "slug": shot_code, "description": ""})
        data["shots"] = shots
        transaction.set(_doc(project_id, int(data["scene"])), data)
        transaction.set(lock, {"rev": version + 1})
        return int(data["scene"]), shot_id

    return await ensure(db().transaction())


async def resolve_codes(project_id: int, scene_code: str, shot_code: str) -> tuple[int, int]:
    """Resolve slate strings to existing internal ids, never inventing structure.

    An empty shot code may resolve only when the matched scene has one declared
    shot.  Anything ambiguous remains zero and is sent to human verification.
    """
    wanted_scene = _normalise_code(scene_code)
    wanted_shot = _normalise_code(shot_code)
    if not wanted_scene:
        return 0, 0

    scenes = await for_project(project_id)
    matches = [
        item
        for item in scenes
        if _normalise_code(item.scene_code or str(item.scene)) == wanted_scene
    ]
    if len(matches) != 1:
        return 0, 0

    scene = matches[0]
    if not wanted_shot:
        return (scene.scene, scene.shots[0].shot) if len(scene.shots) == 1 else (scene.scene, 0)

    shots = [
        item for item in scene.shots if _normalise_code(item.slug or str(item.shot)) == wanted_shot
    ]
    return (scene.scene, shots[0].shot) if len(shots) == 1 else (scene.scene, 0)
