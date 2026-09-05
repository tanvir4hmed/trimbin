"""The scene, assembled from the takes that were chosen.

This has a name in a cutting room: a **stringout**. It is what an assistant
editor hands the editor — every shot of the scene, in order, one take each, so
the editor can watch it as a scene instead of as a bin of ninety files.

That is the whole reason for it, and it is why this is the screen the product
was missing rather than a nice extra. Trimbin already knows which take of each
shot won and which seconds of it are usable. Not putting them end to end was
leaving the actual deliverable unbuilt.

It is not an edit. Nothing here decides where a cut goes, how long a shot holds,
or which angle the moment belongs to — those are story questions and the system
has no standing to answer them. A stringout is the raw material an editor cuts
*from*, and offering it as a cut would be claiming something untrue.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from . import assessment
from . import comments as comments_service
from . import shots as shots_service
from . import structure as structure_service
from .analytics import client

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Entry:
    """One shot's place in the scene."""

    scene: int
    shot: int
    slug: str
    clip_id: str
    take_no: int
    start_s: float
    end_s: float
    proxy_uri: str
    sprite_uri: str
    reason: str
    decided_by: str
    actor: str
    margin: float
    needs_review: bool
    circled_take: int
    open_comments: int
    fps: float = 0.0
    scene_code: str = ""
    shot_code: str = ""
    segment_id: str = ""
    position: int = 0
    source_filename: str = ""

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end_s - self.start_s)

    def as_dict(self) -> dict:
        return {
            "scene": self.scene,
            "shot": self.shot,
            "slug": self.slug,
            "clip_id": self.clip_id,
            "take_no": self.take_no,
            "start_s": round(self.start_s, 2),
            "end_s": round(self.end_s, 2),
            "duration_s": round(self.duration_s, 2),
            "proxy_uri": self.proxy_uri,
            "sprite_uri": self.sprite_uri,
            "reason": self.reason,
            "decided_by": self.decided_by,
            "actor": self.actor,
            "margin": round(self.margin, 4),
            "needs_review": self.needs_review,
            "circled_take": self.circled_take,
            # A shot where the room circled take 3 and the measurements chose
            # take 1 is the single most interesting row on this screen. It is
            # not an error on either side: the circle knows about performance,
            # which this system deliberately does not judge.
            "differs_from_circle": bool(self.circled_take and self.circled_take != self.take_no),
            "open_comments": self.open_comments,
            "fps": round(self.fps, 3),
            "scene_code": self.scene_code,
            "shot_code": self.shot_code,
            "segment_id": self.segment_id,
            "position": self.position,
            "source_filename": self.source_filename,
        }


async def scene(project_id: int, scene_id: int) -> dict:
    """Every shot of one scene, with the take currently standing for it.

    "Currently standing" rather than "the panel chose": an editor override is
    the newest decision and this plays what the team actually decided. A
    stringout that showed the machine's picks after a person changed them would
    be a report about the machine, not the scene.
    """
    ch = await client()
    result = await ch.query(
        """
        WITH latest AS (
            SELECT subgroup_id, clip_id,
                   argMax(outcome, decided_at)     AS outcome,
                   argMax(reason, decided_at)      AS reason,
                   argMax(decided_by, decided_at)  AS decided_by,
                   argMax(actor_id, decided_at)    AS actor,
                   argMax(margin, decided_at)      AS margin,
                   argMax(in_point_s, decided_at)  AS in_point_s,
                   argMax(out_point_s, decided_at) AS out_point_s
            FROM decisions
            WHERE project_id = {p:UInt32} AND group_id = {g:UInt32}
            GROUP BY subgroup_id, clip_id
        )
        SELECT l.subgroup_id, toString(l.clip_id), c.take_no,
               l.in_point_s, l.out_point_s,
               c.proxy_uri, c.sprite_uri,
               l.reason, l.decided_by, l.actor, l.margin,
               c.duration_ms, c.fps, c.scene_code, c.shot_code, c.storage_uri
        FROM latest AS l
        INNER JOIN current_clip_placement AS c
            ON c.clip_id = l.clip_id AND c.project_id = {p:UInt32}
        WHERE l.outcome = 'selected' AND l.decided_by = 'human'
          AND c.group_id = {g:UInt32}
          AND c.subgroup_id = l.subgroup_id
        ORDER BY l.subgroup_id
        """,
        parameters={"p": project_id, "g": scene_id},
    )
    observed_result = await ch.query(
        """
        SELECT subgroup_id, toString(clip_id)
        FROM current_clip_placement
        WHERE project_id = {p:UInt32} AND group_id = {g:UInt32}
        ORDER BY subgroup_id, clip_id
        """,
        parameters={"p": project_id, "g": scene_id},
    )
    observed_by_shot: dict[int, list[str]] = {}
    for row in observed_result.result_rows:
        observed_by_shot.setdefault(int(row[0]), []).append(str(row[1]))
    observed_shots = set(observed_by_shot)

    meta = await shots_service.for_project(project_id)
    plan = await structure_service.for_project(project_id)
    scene_codes = {item.scene: item.scene_code for item in plan}
    shot_codes = {
        (item.scene, planned.shot): planned.slug for item in plan for planned in item.shots
    }
    open_counts = await comments_service.counts_for_project(project_id)
    margin = assessment.review_margin()

    entries: list[Entry] = []
    for r in result.result_rows:
        shot_id = int(r[0])
        duration_s = round(int(r[11] or 0) / 1000, 2)
        start = float(r[3])
        end = float(r[4])
        if end <= start:
            # A verdict recorded before in and out points existed. Playing zero
            # seconds of it would look like the shot is missing; playing all of
            # it is what an assistant would do with a take nobody had trimmed.
            start, end = 0.0, duration_s

        described = meta.get((scene_id, shot_id))
        entries.append(
            Entry(
                scene=scene_id,
                shot=shot_id,
                slug=(described.slug if described else "") or f"{scene_id}{_letter(shot_id)}",
                clip_id=str(r[1]),
                take_no=int(r[2] or 0),
                start_s=start,
                end_s=end,
                proxy_uri=r[5] or "",
                sprite_uri=r[6] or "",
                reason=r[7] or "",
                decided_by=r[8] or "",
                actor=r[9] or "",
                margin=float(r[10]),
                # The same rule the tree and the queue use. This was
                # margin-only, so a scene could report "all settled" while the
                # dashboard listed three of its shots as waiting.
                needs_review=assessment.assess(
                    takes=2,
                    has_verdict=True,
                    confirmed=(r[8] or "") == "human",
                    margin=float(r[10]),
                    circled_take=described.circled_take if described else 0,
                    chosen_take=int(r[2] or 0),
                    state=described.state if described else "",
                    segments=len(described.coverage_segments) if described else 0,
                    decision_fresh=(
                        not described
                        or not described.coverage_segments
                        or bool(described.observed_source_set_hash)
                    ),
                    threshold=margin,
                ).needs_a_person,
                circled_take=described.circled_take if described else 0,
                open_comments=open_counts.get((scene_id, shot_id), {}).get("open", 0),
                fps=float(r[12] or 0),
                scene_code=scene_codes.get(scene_id) or r[13] or "",
                shot_code=(described.slug if described else "")
                or shot_codes.get((scene_id, shot_id))
                or r[14]
                or "",
                source_filename=str(r[15] or "").rsplit("/", 1)[-1],
            )
        )

    # A human-built ordered coverage list supersedes the legacy one-take row
    # for that shot. Placement remains canonical; using a clip here never moves
    # it, and repeated clip ids deliberately produce repeated source ranges.
    covered_shots = {
        shot_id
        for (scene_no, shot_id), shot in meta.items()
        if scene_no == scene_id and shot.coverage_segments
    }
    if covered_shots:
        entries = [entry for entry in entries if entry.shot not in covered_shots]
        clip_ids = sorted(
            {
                str(segment.get("clip_id"))
                for (scene_no, _), shot in meta.items()
                if scene_no == scene_id
                for segment in shot.coverage_segments
                if segment.get("clip_id")
            }
        )
        clip_rows: dict[str, Sequence] = {}
        if clip_ids:
            clips_result = await ch.query(
                """
                SELECT toString(clip_id), take_no, proxy_uri, sprite_uri,
                       duration_ms, fps, scene_code, shot_code, storage_uri
                FROM current_clip_placement
                WHERE project_id = {p:UInt32} AND clip_id IN {clips:Array(UUID)}
                """,
                parameters={"p": project_id, "clips": clip_ids},
            )
            clip_rows = {str(row[0]): row for row in clips_result.result_rows}
        for (scene_no, shot_id), described in meta.items():
            if scene_no != scene_id or not described.coverage_segments:
                continue
            for position, segment in enumerate(described.coverage_segments):
                clip_id = str(segment.get("clip_id") or "")
                row = clip_rows.get(clip_id)
                if row is None:
                    continue
                start = max(0.0, float(segment.get("source_in_s", 0) or 0))
                duration = float(int(row[4] or 0) / 1000)
                end = min(duration, float(segment.get("source_out_s", duration) or duration))
                if end <= start:
                    continue
                decision_fresh = bool(
                    described.observed_source_set_hash
                    and described.observed_source_set_hash
                    == assessment.source_set_hash(observed_by_shot.get(shot_id, []))
                )
                entries.append(
                    Entry(
                        scene=scene_id,
                        shot=shot_id,
                        slug=described.slug or f"{scene_id}{_letter(shot_id)}",
                        clip_id=clip_id,
                        take_no=int(segment.get("take_no") or row[1] or 0),
                        start_s=start,
                        end_s=end,
                        proxy_uri=row[2] or "",
                        sprite_uri=row[3] or "",
                        reason=str(segment.get("reason") or "Human coverage selection"),
                        decided_by="human",
                        actor=str(segment.get("created_by") or ""),
                        margin=0,
                        needs_review=not decision_fresh,
                        circled_take=described.circled_take,
                        open_comments=open_counts.get((scene_id, shot_id), {}).get("open", 0),
                        fps=float(row[5] or 0),
                        scene_code=scene_codes.get(scene_id) or row[6] or "",
                        shot_code=described.slug
                        or shot_codes.get((scene_id, shot_id))
                        or row[7]
                        or "",
                        source_filename=str(row[8] or "").rsplit("/", 1)[-1],
                        segment_id=str(segment.get("segment_id") or ""),
                        position=int(segment.get("position", position)),
                    )
                )

    entries.sort(key=lambda entry: (entry.shot, entry.position))

    measured_rates = sorted({round(e.fps, 3) for e in entries if e.fps > 0})

    timeline = coverage_timeline(scene_id, entries, meta, observed_shots)
    ordered_shots = [item["shot"] for item in timeline]

    stale_shots = {entry.shot for entry in entries if entry.needs_review}
    gap_shots = {int(item["shot"]) for item in timeline if item["kind"] == "gap"}
    return {
        "project_id": project_id,
        "scene": scene_id,
        "entries": [e.as_dict() for e in entries],
        "duration_s": round(sum(e.duration_s for e in entries), 2),
        "shots": len(ordered_shots),
        "unresolved": len(gap_shots | stale_shots),
        "disagreements": sum(1 for e in entries if e.circled_take and e.circled_take != e.take_no),
        "source_fps": measured_rates,
        "export_fps": measured_rates[0] if len(measured_rates) == 1 else 0.0,
        "timeline": timeline,
    }


def coverage_timeline(
    scene_id: int,
    entries: list[Entry],
    meta: dict,
    observed_shots: set[int] | None = None,
) -> list[dict]:
    """Confirmed takes in shot order; every planned or observed omission is a gap."""
    planned = sorted(
        (shot for (scene_no, _), shot in meta.items() if scene_no == scene_id),
        key=lambda shot: shot.shot,
    )
    entries_by_shot: dict[int, list[Entry]] = {}
    for entry in entries:
        entries_by_shot.setdefault(entry.shot, []).append(entry)
    ordered_shots = sorted(
        set(entries_by_shot) | {shot.shot for shot in planned} | (observed_shots or set())
    )
    timeline = []
    for shot_id in ordered_shots:
        shot_entries = sorted(entries_by_shot.get(shot_id, []), key=lambda item: item.position)
        head = shot_entries[0] if shot_entries else None
        described = meta.get((scene_id, shot_id))
        timeline.append(
            {
                "kind": "selected" if head else "gap",
                "scene": scene_id,
                "shot": shot_id,
                "slug": (described.slug if described else "") or f"{scene_id}{_letter(shot_id)}",
                "duration_s": sum(item.duration_s for item in shot_entries),
                "entry": head.as_dict() if head else None,
                "entries": [item.as_dict() for item in shot_entries],
            }
        )

    return timeline


async def scenes_in(project_id: int) -> list[int]:
    """Which scenes this project has, in order."""
    ch = await client()
    result = await ch.query(
        """
        SELECT DISTINCT group_id FROM current_clip_placement
        WHERE project_id = {p:UInt32} ORDER BY group_id
        """,
        parameters={"p": project_id},
    )
    return [int(r[0]) for r in result.result_rows]


def _letter(shot_id: int) -> str:
    """A, B, C — the slate's own way of naming a camera setup.

    Only used when nobody has written a slug. A shot with no name at all reads
    as a database row; "12C" reads as a shot, and an editor can find it on the
    board.
    """
    if shot_id <= 0:
        return ""
    letters = ""
    n = shot_id
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters
