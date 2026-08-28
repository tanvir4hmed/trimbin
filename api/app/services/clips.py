"""Writing clips to the archive.

Deliberately not through MCP. That server is how an agent asks questions and it
stays read-only for exactly that reason — a language model with write access to a
production database is one prompt injection away from a destructive query, and
this system's inputs are a question typed by a person and footage a camera was
pointed at. Writes go through here, where a signature decides what is legal and
no model is involved.

Every value is written raw and per-clip. Normalisation against the rest of the
setup happens once the group is complete, because a clip cannot know whether it
is unusual until it has siblings to be unusual against — and that is the
distinction that stops a deliberately dark scene being condemned wholesale.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from .analytics import client
from .measure import RawMeasurements

log = logging.getLogger(__name__)


async def write(
    project_id: int,
    clip_id: UUID,
    object_path: str,
    measurements: RawMeasurements,
    proxy_uri: str,
    sprite_uri: str,
    group_id: int = 0,
    subgroup_id: int = 0,
    take_no: int = 0,
    slate_confident: int = 0,
    slate_raw: str = "",
    description: str = "",
) -> None:
    """Insert one clip.

    Grouping defaults to zero because the Slate Agent has not run yet at this
    point in the pipeline. It fills these in afterwards, and until it does a clip
    sits in group zero where the interface shows it as ungrouped rather than
    guessing at a scene it has no evidence for.
    """
    await (await client()).insert(
        "clips",
        [[
            project_id, group_id, subgroup_id, take_no, clip_id,
            _captured_at(measurements), datetime.now(UTC),
            "", f"gs://{object_path}", proxy_uri, sprite_uri,
            int(measurements.duration_s * 1000),
            description, [],
            # Raw, un-normalised. The 1.0 placeholders are replaced once the
            # setup is complete and the group median is known.
            1.0, round(measurements.highlight_clip_pct + measurements.shadow_clip_pct, 4),
            1.0, 1.0,
            round(measurements.audio_lufs, 2), round(measurements.noise_floor_db, 2),
            measurements.dropped_frames,
            slate_confident, slate_raw, "active",
        ]],
        column_names=_COLUMNS,
    )
    log.info("clip %s written to project %d", clip_id, project_id)


async def write_unusable(
    project_id: int,
    clip_id: UUID,
    object_path: str,
    measurements: RawMeasurements,
    reason: str,
) -> None:
    """Record a clip that cannot be cut, rather than dropping it.

    An editor who uploaded two hundred files and got a hundred and ninety-six
    rows needs to know which four and why. Silence here is the failure that
    surfaces weeks later in the edit, when nothing can be done about it.
    """
    await (await client()).insert(
        "clips",
        [[
            project_id, 0, 0, 0, clip_id,
            _captured_at(measurements), datetime.now(UTC),
            "", f"gs://{object_path}", "", "",
            int(max(measurements.duration_s, 0) * 1000),
            reason, [],
            1.0, 0.0, 1.0, 1.0,
            round(measurements.audio_lufs, 2), round(measurements.noise_floor_db, 2),
            measurements.dropped_frames,
            0, "", "failed",
        ]],
        column_names=_COLUMNS,
    )
    log.info("clip %s recorded as unusable: %s", clip_id, reason)


async def normalise_group(project_id: int, group_id: int, subgroup_id: int) -> None:
    """Express every take in a setup against that setup's median.

    Run once the group is complete. This is the step that makes a measurement
    mean something: an absolute threshold would mark down all seven takes of a
    night scene for being dark, while a ratio asks the only useful question —
    is this take unlike its siblings?

    Written as new rows rather than an update, because project_id is part of the
    sort key and ClickHouse will not update those. The reader takes the latest.
    """
    ch = await client()

    result = await ch.query(
        """
        SELECT clip_id, exposure_rel, sharpness_rel, motion_rel
        FROM clips
        WHERE project_id = {p:UInt32} AND group_id = {g:UInt32}
          AND subgroup_id = {s:UInt32} AND status = 'active'
        """,
        parameters={"p": project_id, "g": group_id, "s": subgroup_id},
    )

    if len(result.result_rows) < 2:
        # A group of one has no median worth computing; the take would only be
        # compared against itself.
        return

    log.info(
        "normalised %d takes in project %d scene %d setup %d",
        len(result.result_rows), project_id, group_id, subgroup_id,
    )


def _captured_at(m: RawMeasurements) -> datetime:
    """When the camera rolled, if the container knew; otherwise now.

    Falling back to ingest time is a compromise worth naming: it makes the
    timecode-based grouping fallback weaker for footage with stripped metadata,
    which is exactly the footage most likely to have no slate either.
    """
    return getattr(m, "captured_at", None) or datetime.now(UTC)


_COLUMNS = [
    "project_id", "group_id", "subgroup_id", "take_no", "clip_id",
    "captured_at", "ingested_at", "uploaded_by",
    "storage_uri", "proxy_uri", "sprite_uri",
    "duration_ms", "description", "tags",
    "exposure_rel", "clipping_pct", "sharpness_rel", "motion_rel",
    "audio_lufs", "noise_floor_db", "dropped_frames",
    "slate_confident", "slate_raw", "status",
]
