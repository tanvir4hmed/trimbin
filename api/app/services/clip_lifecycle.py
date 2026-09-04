"""Reversible clip removal without mutating archive rows or deleting bytes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from .analytics import client


async def clip(project_id: int, clip_id: UUID) -> dict | None:
    result = await (await client()).query(
        """
        SELECT uploaded_by, storage_uri, status
        FROM clips
        WHERE project_id = {p:UInt32} AND clip_id = {c:UUID}
        ORDER BY ingested_at DESC
        LIMIT 1
        """,
        parameters={"p": project_id, "c": str(clip_id)},
    )
    if not result.result_rows:
        return None
    row = result.result_rows[0]
    return {"uploaded_by": row[0] or "", "storage_uri": row[1] or "", "status": row[2]}


async def record(project_id: int, clip_id: UUID, action: str, actor: str, detail: str = "") -> None:
    if action not in {"deleted", "restored"}:
        raise ValueError(f"unsupported clip lifecycle action {action!r}")
    await (await client()).insert(
        "clip_lifecycle_events",
        [[project_id, clip_id, uuid4(), datetime.now(UTC), action, actor, detail[:200]]],
        column_names=[
            "project_id",
            "clip_id",
            "event_id",
            "occurred_at",
            "action",
            "actor",
            "detail",
        ],
    )
