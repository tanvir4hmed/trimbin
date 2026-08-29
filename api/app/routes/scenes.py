"""The scene, assembled — and the two files that carry it out of here.

A stringout is what an assistant editor hands the editor: every shot of the
scene, in order, one take each, so it can be watched as a scene rather than as a
bin of ninety files. It is the actual deliverable of the job this software does,
and it was the screen the product was missing.

The exports are the other half of the same idea. Notes that cannot reach the
timeline an editor is cutting in become a second place to look, and a second
place to look is a place people stop looking.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from ..auth import Principal, current_principal
from ..services import exports, stringout
from ..services.analytics import client

log = logging.getLogger(__name__)
router = APIRouter(prefix="/scenes", tags=["scenes"])


@router.get("/{project_id}")
async def scenes(
    project_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    """Which scenes this project has."""
    await principal.assert_can_read(project_id)
    return {"project_id": project_id, "scenes": await stringout.scenes_in(project_id)}


@router.get("/{project_id}/{scene_id}")
async def scene(
    project_id: int,
    scene_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict:
    """The scene as it currently stands, shot by shot.

    What the team decided, not what the panel recommended: an editor override is
    the newest decision, and a stringout showing the machine's picks after a
    person changed them would be a report about the machine rather than a view
    of the scene.
    """
    await principal.assert_can_read(project_id)
    return await stringout.scene(project_id, scene_id)


@router.get("/{project_id}/{scene_id}/edl")
async def scene_edl(
    project_id: int,
    scene_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
    fps: float = exports.DEFAULT_FPS,
) -> Response:
    """The stringout as a CMX3600 EDL, with the reasoning in the comments.

    The frame rate is declared by the caller and written into the header,
    because nothing in the archive records what the original was shot at — the
    proxies are normalised on the way in. An EDL cut at 24 for 25fps footage is
    wrong by a frame a second, and it is better for an assistant to read that in
    the file than to discover it in a conform.
    """
    await principal.assert_can_read(project_id)

    built = await stringout.scene(project_id, scene_id)
    text = exports.edl(
        title=f"TRIMBIN P{project_id} SCENE {scene_id}",
        entries=built["entries"],
        fps=fps,
    )
    return Response(
        content=text,
        media_type="text/plain; charset=us-ascii",
        headers={
            "Content-Disposition": (
                f'attachment; filename="p{project_id}_scene{scene_id}.edl"'
            )
        },
    )


@router.get("/{project_id}/{scene_id}/markers.csv")
async def scene_markers(
    project_id: int,
    scene_id: int,
    principal: Annotated[Principal, Depends(current_principal)],
    fps: float = exports.DEFAULT_FPS,
) -> Response:
    """Every finding and every note as timeline markers, in record time.

    Only the takes that are in the stringout. A rejected take's findings are
    real and stay in the archive, but a marker for one placed on a timeline that
    does not contain that take would land on whatever happens to be there, which
    is worse than leaving it out.
    """
    await principal.assert_can_read(project_id)

    built = await stringout.scene(project_id, scene_id)
    findings = await _findings_for_scene(project_id, scene_id)
    notes = await _notes_for_scene(project_id, scene_id)

    text = exports.markers(built["entries"], findings, notes, fps=fps)
    return Response(
        content=text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="p{project_id}_scene{scene_id}_markers.csv"'
            )
        },
    )


async def _findings_for_scene(project_id: int, scene_id: int) -> list[dict]:
    """Every finding on every take of a scene, flattened out of the arrays.

    ARRAY JOIN rather than three parallel lists returned to Python and zipped
    there: the arrays are how the column store reads them quickly, and unrolling
    them is what the database is for.
    """
    ch = await client()
    result = await ch.query(
        """
        SELECT toString(d.clip_id), c.take_no, code, start_s, end_s, severity
        FROM (
            SELECT clip_id, subgroup_id,
                   argMax(finding_codes, decided_at)      AS codes,
                   argMax(finding_starts_s, decided_at)   AS starts,
                   argMax(finding_ends_s, decided_at)     AS ends,
                   argMax(finding_severities, decided_at) AS sevs
            FROM decisions
            WHERE project_id = {p:UInt32} AND group_id = {g:UInt32}
            GROUP BY clip_id, subgroup_id
        ) AS d
        -- LEFT ARRAY JOIN, because severities is empty on every row written
        -- before it was stored and a plain ARRAY JOIN over unequal arrays drops
        -- the whole row. Losing a finding is worse than losing its colour.
        LEFT ARRAY JOIN codes AS code, starts AS start_s, ends AS end_s,
                        arrayResize(sevs, length(codes), '') AS severity
        LEFT JOIN clips AS c ON c.clip_id = d.clip_id AND c.project_id = {p:UInt32}
        ORDER BY d.subgroup_id, c.take_no
        """,
        parameters={"p": project_id, "g": scene_id},
    )
    return [
        {
            "clip_id": r[0],
            "take_no": int(r[1] or 0),
            "code": r[2],
            "start_s": float(r[3]),
            "end_s": float(r[4]),
            "detail": "",
            # What the panel actually said, or nothing.
            #
            # This used to read `code.endswith(".blocking")`, which is a guess
            # dressed as a rule: `continuity.blocking` is a note about where an
            # actor stands, and every one of them went into Resolve as a red
            # marker meaning the take was unusable. Severity is a judgement, and
            # a judgement is either recorded or absent.
            "severity": r[5] or "",
        }
        for r in result.result_rows
    ]


async def _notes_for_scene(project_id: int, scene_id: int) -> list[dict]:
    ch = await client()
    result = await ch.query(
        """
        SELECT toString(clip_id), author, body, at_s, to_s
        FROM (
            SELECT clip_id, comment_id,
                   argMax(author, created_at)      AS author,
                   argMax(body, created_at)        AS body,
                   argMax(at_s, created_at)        AS at_s,
                   argMax(to_s, created_at)        AS to_s,
                   argMax(resolved_by, created_at) AS resolved_by
            FROM comments
            WHERE project_id = {p:UInt32} AND group_id = {g:UInt32}
            GROUP BY clip_id, comment_id
        )
        WHERE resolved_by = ''
        ORDER BY at_s
        """,
        parameters={"p": project_id, "g": scene_id},
    )
    return [
        {
            "clip_id": r[0],
            "author": r[1],
            "body": r[2],
            "at_s": float(r[3]),
            "to_s": float(r[4]),
        }
        for r in result.result_rows
    ]
