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

# Fixed by the vector index on the clips table, which was declared with this
# width. A row of a different length is rejected at insert, so this is not a
# tuning knob — changing it means migrating the index.
EMBEDDING_DIMENSIONS = 768


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
    embedding: list[float] | None = None,
) -> None:
    """Insert one clip.

    Grouping defaults to zero for a clip whose slate could not be read. A clip
    sits in group zero where the interface shows it as ungrouped, rather than
    being guessed into a scene there is no evidence for.

    An absent embedding is written as zeros rather than omitted, because the
    column carries a vector index that needs a vector of the right shape in
    every row. Zeros are distinguishable from a real embedding — nothing else
    has zero magnitude — so a later pass can find and fill them.
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
            embedding or [0.0] * EMBEDDING_DIMENSIONS,
            # The values the ratios above will be computed from, once the setup
            # is complete. Discarding these is what left every clip in the
            # archive carrying a placeholder 1.0 with no way back except
            # decoding the video again.
            round(measurements.mean_luma, 4),
            round(measurements.sharpness, 4),
            round(measurements.motion_mean, 4),
            *_findings_columns(measurements),
        ]],
        column_names=[
            *_COLUMNS, "embedding",
            "exposure_raw", "sharpness_raw", "motion_raw",
            "finding_codes", "finding_starts_s", "finding_ends_s",
        ],
    )
    log.info("clip %s written to project %d", clip_id, project_id)


def _findings_columns(m: RawMeasurements) -> tuple[list[str], list[float], list[float]]:
    """What ffmpeg found, and where.

    Timecoded because editors choose moments inside takes. "Unstable" is useless
    where "unstable 4.2s-7.8s" becomes something the interface can seek to, and
    the difference decides whether a take with a problem is discarded or trimmed.

    Codes come from the taxonomy the prompts and the interface both use, so a
    finding measured by ffmpeg and one observed by a model are the same kind of
    thing to everything downstream.
    """
    codes: list[str] = []
    starts: list[float] = []
    ends: list[float] = []

    for code, spans in (
        ("focus.lost", m.focus_loss_spans),
        ("stability.shake", m.motion_spikes),
        ("frames.frozen", m.freeze_spans),
        ("clip.black", m.black_spans),
    ):
        for span in spans:
            codes.append(code)
            starts.append(round(span.start_s, 2))
            ends.append(round(span.end_s, 2))

    return codes, starts, ends


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


async def normalise_group(project_id: int, group_id: int, subgroup_id: int) -> int:
    """Express every take in a setup against that setup's median.

    This is the step that makes a measurement mean something. An absolute
    threshold marks down all seven takes of a night scene for being dark; a
    ratio asks the only useful question — is this take unlike its siblings?

    Re-runnable, and meant to be re-run. Takes arrive one message at a time and
    out of order, so the median moves as a setup fills: normalising after take
    three and again after take seven gives different and equally correct
    answers. Whichever ran last is the one that saw the most footage.

    Returns how many takes were normalised, so a caller can tell "the group was
    too small" from "nothing happened".
    """
    ch = await client()

    result = await ch.query(
        """
        SELECT clip_id, exposure_raw, sharpness_raw, motion_raw
        FROM clips
        WHERE project_id = {p:UInt32} AND group_id = {g:UInt32}
          AND subgroup_id = {s:UInt32} AND status = 'active'
        ORDER BY clip_id, ingested_at DESC
        LIMIT 1 BY clip_id
        """,
        parameters={"p": project_id, "g": group_id, "s": subgroup_id},
    )

    rows = result.result_rows
    if len(rows) < 2:
        # A group of one has no median worth computing; the take would only be
        # compared against itself and would always sit exactly at 1.0.
        return 0

    # Refuse rather than normalise from nothing.
    #
    # A clip written before the raw columns existed, or by a tool that computed
    # its own ratios and stored only those, carries zeros here. Every median
    # would be zero, every ratio would fall back to 1.0, and the result would be
    # a whole setup silently flattened to "all takes typical" — overwriting
    # correct values with a confident-looking placeholder.
    #
    # This is not hypothetical: it happened to the twelve dataset takes the
    # first time this ran, and the only reason it was visible is that
    # normalised_at had just been added.
    if not any(float(r[1]) or float(r[2]) or float(r[3]) for r in rows):
        log.warning(
            "project %d scene %d setup %d has no raw measurements; "
            "leaving the existing ratios alone",
            project_id, group_id, subgroup_id,
        )
        return 0

    medians = {
        axis: _median([float(r[i]) for r in rows])
        for i, axis in ((1, "exposure"), (2, "sharpness"), (3, "motion"))
    }

    updates = []
    for clip_id, exposure, sharpness, motion in rows:
        updates.append((
            str(clip_id),
            _ratio(float(exposure), medians["exposure"]),
            _ratio(float(sharpness), medians["sharpness"]),
            _ratio(float(motion), medians["motion"]),
        ))

    # ALTER UPDATE rather than re-insert. The sort key is
    # (project_id, group_id, subgroup_id, take_no, clip_id) and none of those
    # change here, so a mutation is legal and a second row per clip would leave
    # every reader responsible for picking the newer one.
    for clip_id, exposure, sharpness, motion in updates:
        await ch.command(
            """
            ALTER TABLE clips UPDATE
                exposure_rel = {e:Float32},
                sharpness_rel = {s:Float32},
                motion_rel = {m:Float32},
                normalised_at = now()
            WHERE project_id = {p:UInt32} AND clip_id = {c:UUID}
            """,
            parameters={
                "e": exposure, "s": sharpness, "m": motion,
                "p": project_id, "c": clip_id,
            },
        )

    log.info(
        "normalised %d takes in project %d scene %d setup %d",
        len(updates), project_id, group_id, subgroup_id,
    )
    return len(updates)


def _median(values: list[float]) -> float:
    """Median, not mean.

    A single ruined take drags a mean far enough to make the rest look unusual —
    which is backwards, since the ruined one is the thing to notice. The median
    is what the group actually looks like.
    """
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _ratio(value: float, median: float) -> float:
    """1.0 at the median. Falls back to 1.0 rather than dividing by zero.

    A median of zero means the whole setup measured zero on that axis — every
    take pitch black, or a still frame throughout. Saying every take is typical
    is honest there: they are identical, and the fault is not one take's.
    """
    if median <= 0:
        return 1.0
    return round(value / median, 4)


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
