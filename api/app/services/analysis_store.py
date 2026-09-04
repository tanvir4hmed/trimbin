"""Append-only persistence and read models for full-take intelligence."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from .analytics import client

RUN_COLUMNS = [
    "event_id",
    "run_id",
    "run_key",
    "project_id",
    "clip_id",
    "state",
    "duration_s",
    "covered_until_s",
    "window_count",
    "segment_count",
    "finding_count",
    "model_id",
    "prompt_version",
    "error",
    "occurred_at",
]

SEGMENT_COLUMNS = [
    "segment_id",
    "run_id",
    "project_id",
    "clip_id",
    "window_index",
    "start_s",
    "end_s",
    "description",
    "transcript",
    "actions",
    "objects",
    "speakers",
    "shot_size",
    "camera_motion",
    "embedding",
    "model_id",
    "prompt_version",
    "occurred_at",
]

MOMENT_COLUMNS = [
    "moment_id",
    "run_id",
    "project_id",
    "clip_id",
    "kind",
    "start_s",
    "end_s",
    "text",
    "evidence_segment_ids",
    "embedding",
    "model_id",
    "prompt_version",
    "occurred_at",
]

FINDING_COLUMNS = [
    "event_id",
    "finding_id",
    "run_id",
    "project_id",
    "clip_id",
    "revision",
    "action",
    "code",
    "detail",
    "severity",
    "start_s",
    "end_s",
    "evidence_segment_ids",
    "sources",
    "supersedes_event_id",
    "actor_id",
    "actor_role",
    "model_id",
    "prompt_version",
    "occurred_at",
]

ZERO_UUID = UUID(int=0)


async def already_completed(project_id: int, run_key: str) -> bool:
    result = await (await client()).query(
        """
        SELECT count()
        FROM analysis_runs
        WHERE project_id = {p:UInt32} AND run_key = {k:String} AND state = 'completed'
        """,
        parameters={"p": project_id, "k": run_key},
    )
    return bool(result.result_rows and result.result_rows[0][0])


async def record_run(
    *,
    run_id: UUID,
    run_key: str,
    project_id: int,
    clip_id: UUID,
    state: str,
    duration_s: float,
    covered_until_s: float = 0.0,
    window_count: int = 0,
    segment_count: int = 0,
    finding_count: int = 0,
    model_id: str = "",
    prompt_version: str = "",
    error: str = "",
) -> UUID:
    event_id = uuid4()
    row = [
        [
            event_id,
            run_id,
            run_key,
            project_id,
            clip_id,
            state,
            float(duration_s),
            float(covered_until_s),
            int(window_count),
            int(segment_count),
            int(finding_count),
            model_id,
            prompt_version,
            error[:1000],
            datetime.now(UTC),
        ]
    ]
    await (await client()).insert("analysis_runs", row, column_names=RUN_COLUMNS)
    return event_id


async def record_segments(segments: list[dict]) -> int:
    if not segments:
        return 0
    now = datetime.now(UTC)
    rows = [
        [
            s["segment_id"],
            s["run_id"],
            s["project_id"],
            s["clip_id"],
            s["window_index"],
            s["start_s"],
            s["end_s"],
            s.get("description", "")[:500],
            s.get("transcript", "")[:3000],
            list(s.get("actions", [])),
            list(s.get("objects", [])),
            list(s.get("speakers", [])),
            s.get("shot_size", "")[:40],
            s.get("camera_motion", "")[:60],
            list(s.get("embedding", [])),
            s.get("model_id", ""),
            s.get("prompt_version", ""),
            now,
        ]
        for s in segments
    ]
    await (await client()).insert("clip_segments", rows, column_names=SEGMENT_COLUMNS)
    return len(rows)


async def record_moments(moments: list[dict]) -> int:
    if not moments:
        return 0
    now = datetime.now(UTC)
    rows = [
        [
            moment["moment_id"],
            moment["run_id"],
            moment["project_id"],
            moment["clip_id"],
            moment["kind"],
            float(moment["start_s"]),
            float(moment["end_s"]),
            str(moment.get("text") or "")[:300],
            list(moment.get("evidence_segment_ids", [])),
            list(moment.get("embedding", [])),
            moment.get("model_id", ""),
            moment.get("prompt_version", ""),
            moment.get("occurred_at") or now,
        ]
        for moment in moments
    ]
    await (await client()).insert("clip_moments", rows, column_names=MOMENT_COLUMNS)
    return len(rows)


async def record_finding_events(events: list[dict]) -> int:
    if not events:
        return 0
    now = datetime.now(UTC)
    rows = [
        [
            e["event_id"],
            e["finding_id"],
            e.get("run_id") or ZERO_UUID,
            e["project_id"],
            e["clip_id"],
            int(e.get("revision", 0)),
            e["action"],
            e["code"],
            e.get("detail", "")[:500],
            e.get("severity", "attention"),
            float(e["start_s"]),
            float(e["end_s"]),
            list(e.get("evidence_segment_ids", [])),
            list(e.get("sources", [])),
            e.get("supersedes_event_id") or ZERO_UUID,
            e.get("actor_id", ""),
            e.get("actor_role", ""),
            e.get("model_id", ""),
            e.get("prompt_version", ""),
            e.get("occurred_at") or now,
        ]
        for e in events
    ]
    await (await client()).insert("finding_events", rows, column_names=FINDING_COLUMNS)
    return len(rows)


async def finding_event_exists(project_id: int, event_id: UUID) -> bool:
    result = await (await client()).query(
        "SELECT count() FROM finding_events WHERE project_id={p:UInt32} AND event_id={e:UUID}",
        parameters={"p": project_id, "e": event_id},
    )
    return bool(result.result_rows and result.result_rows[0][0])


_CLIP_SQL = """
        SELECT group_id, subgroup_id, take_no, duration_ms / 1000 AS duration_s,
               proxy_uri, sprite_uri, fps, scene_code, shot_code
        FROM current_clip_placement
        WHERE project_id={p:UInt32} AND clip_id={c:UUID} AND status='active'
        ORDER BY ingested_at DESC
        LIMIT 1
        """

_RUN_SQL = """
        SELECT run_id, run_key, state, duration_s, covered_until_s, window_count,
               segment_count, finding_count, model_id, prompt_version, error, occurred_at
        FROM current_analysis_runs
        WHERE project_id={p:UInt32} AND clip_id={c:UUID}
        """

_SEGMENT_SQL = """
        SELECT segment_id, run_id, start_s, end_s, description, transcript,
               actions, objects, speakers, shot_size, camera_motion,
               arrayExists(x -> x != 0, embedding) AS has_embedding
        FROM current_clip_segments
        WHERE project_id={p:UInt32} AND clip_id={c:UUID}
        ORDER BY start_s, segment_id
        """

_FINDING_SQL = """
        SELECT clip_id, finding_id, event_id, run_id, revision, action, code, detail,
               severity, start_s, end_s, evidence_segment_ids, sources, actor_id,
               actor_role, occurred_at
        FROM current_findings
        WHERE project_id={p:UInt32} AND clip_id={c:UUID}
        ORDER BY start_s, finding_id
        """

_HISTORY_SQL = """
        SELECT *
        FROM
        (
            SELECT clip_id, finding_id, event_id, run_id, revision, action, code, detail,
                   severity, start_s, end_s, evidence_segment_ids, sources,
                   supersedes_event_id, actor_id, actor_role, occurred_at
            FROM finding_events
            WHERE project_id={p:UInt32} AND clip_id={c:UUID}
            ORDER BY occurred_at DESC, event_id
            LIMIT 1 BY event_id
        )
        ORDER BY finding_id, revision, occurred_at, event_id
        """


async def read(project_id: int, clip_id: UUID) -> dict:
    """One clip's analysis, in one wait rather than five.

    These five statements share their parameters and none reads another's
    result, but they were awaited in a row — five sequential round trips to a
    cloud database per clip. The shot screen runs this once per take, so a
    two-take shot paid ten sequential hops and a six-take shot thirty. It
    measured 1.15s for two takes and grew with the take count.

    Same statements, same parameters, same results; only the waiting is shared.
    """
    ch = await client()
    params = {"p": project_id, "c": clip_id}
    clip_result, run_result, segment_result, finding_result, history_result = await asyncio.gather(
        ch.query(_CLIP_SQL, parameters=params),
        ch.query(_RUN_SQL, parameters=params),
        ch.query(_SEGMENT_SQL, parameters=params),
        ch.query(_FINDING_SQL, parameters=params),
        ch.query(_HISTORY_SQL, parameters=params),
    )
    # clip_result is awaited together with the others above
    clip = {}
    if clip_result.result_rows:
        clip = dict(zip(clip_result.column_names, clip_result.result_rows[0], strict=True))

    # run_result is awaited together with the others above
    run = {}
    if run_result.result_rows:
        run = dict(zip(run_result.column_names, run_result.result_rows[0], strict=True))

    # segment_result is awaited together with the others above
    segments = [
        dict(zip(segment_result.column_names, row, strict=True))
        for row in segment_result.result_rows
    ]

    # finding_result is awaited together with the others above
    findings = [
        dict(zip(finding_result.column_names, row, strict=True))
        for row in finding_result.result_rows
    ]

    # history_result is awaited together with the others above
    history = [
        dict(zip(history_result.column_names, row, strict=True))
        for row in history_result.result_rows
    ]
    return {
        "clip": clip,
        "run": run,
        "segments": segments,
        "findings": findings,
        "history": history,
    }


async def active_clips_without_analysis(project_id: int) -> list[dict]:
    result = await (await client()).query(
        """
        SELECT c.clip_id, c.group_id, c.subgroup_id, c.take_no,
               c.duration_ms / 1000 AS duration_s
        FROM current_clip_placement AS c
        LEFT JOIN current_analysis_runs AS r
          ON r.project_id=c.project_id AND r.clip_id=c.clip_id
        WHERE c.project_id={p:UInt32} AND c.status='active'
          AND (r.clip_id=toUUID('00000000-0000-0000-0000-000000000000')
               OR r.state = 'failed')
        ORDER BY c.ingested_at, c.clip_id
        """,
        parameters={"p": project_id},
    )
    return [dict(zip(result.column_names, row, strict=True)) for row in result.result_rows]


async def raw_findings(project_id: int, clip_id: UUID) -> list[dict]:
    result = await (await client()).query(
        """
        SELECT finding_codes, finding_starts_s, finding_ends_s
        FROM current_clip_placement
        WHERE project_id={p:UInt32} AND clip_id={c:UUID} AND status='active'
        ORDER BY ingested_at DESC
        LIMIT 1
        """,
        parameters={"p": project_id, "c": clip_id},
    )
    if not result.result_rows:
        return []
    codes, starts, ends = result.result_rows[0]
    return [
        {
            "code": str(code),
            "start_s": float(start),
            "end_s": float(end),
            "detail": "Measured during ingest.",
            "severity": "attention",
            "source": "measured",
        }
        for code, start, end in zip(codes, starts, ends, strict=True)
    ]


async def working_findings_for_clips(
    project_id: int,
    clip_ids: list[UUID],
) -> tuple[set[str], dict[str, list[dict]]]:
    """Current full-take findings plus deterministic ingest measurements.

    Once a full run exists, old decision-row findings are a stale snapshot. The
    shot page switches to this working view so a human dismissal actually
    disappears there instead of surviving in the earlier panel verdict.
    """
    if not clip_ids:
        return set(), {}
    ch = await client()
    run_result = await ch.query(
        """
        SELECT clip_id
        FROM current_analysis_runs
        WHERE project_id={p:UInt32} AND clip_id IN {ids:Array(UUID)}
          AND state='completed' AND covered_until_s >= duration_s - 0.05
        """,
        parameters={"p": project_id, "ids": clip_ids},
    )
    complete = {str(row[0]) for row in run_result.result_rows}
    if not complete:
        return set(), {}

    selected = [clip_id for clip_id in clip_ids if str(clip_id) in complete]
    findings: dict[str, list[dict]] = {clip_id: [] for clip_id in complete}
    current_result = await ch.query(
        """
        SELECT clip_id, code, start_s, end_s, detail, severity
        FROM current_findings
        WHERE project_id={p:UInt32} AND clip_id IN {ids:Array(UUID)}
        ORDER BY clip_id, start_s, finding_id
        """,
        parameters={"p": project_id, "ids": selected},
    )
    for clip_id, code, start, end, detail, severity in current_result.result_rows:
        findings[str(clip_id)].append(
            {
                "code": str(code),
                "start_s": float(start),
                "end_s": float(end),
                "detail": str(detail),
                "severity": str(severity),
            }
        )
    return complete, findings
