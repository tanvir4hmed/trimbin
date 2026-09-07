"""Real-footage coverage and explicit human review measurements."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from pydantic import BaseModel

from . import projects
from .analytics import _many


class QualityCounts(BaseModel):
    clips: int = 0
    placed: int = 0
    analysed: int = 0
    findings: int = 0
    confirmed: int = 0
    corrected: int = 0
    dismissed: int = 0
    reviewed: int = 0
    agreement_pct: float | None = None


class ProjectQuality(QualityCounts):
    project_id: int
    name: str


class QualityReport(BaseModel):
    measured_at: datetime
    refresh_seconds: int = 15
    scope: str = "Projects visible to you; real footage only"
    overall: QualityCounts
    projects: list[ProjectQuality]


def counts(row: dict) -> QualityCounts:
    values = {
        key: int(row.get(key, 0) or 0)
        for key in (
            "clips",
            "placed",
            "analysed",
            "findings",
            "confirmed",
            "corrected",
            "dismissed",
        )
    }
    reviewed = values["confirmed"] + values["corrected"] + values["dismissed"]
    return QualityCounts(
        **values,
        reviewed=reviewed,
        agreement_pct=round(100 * values["confirmed"] / reviewed, 1) if reviewed else None,
    )


async def report(email: str = "") -> QualityReport:
    visible = [p for p in await projects.visible_to(email) if p.project_id < 900000]
    ids = [p.project_id for p in visible]
    if not ids:
        return QualityReport(measured_at=datetime.now(UTC), overall=counts({}), projects=[])
    params = {"ids": ids}
    corpus, reviews = await asyncio.gather(
        _many(
            """
            SELECT c.project_id AS project_id, count() AS clips,
                   countIf(p.group_id > 0 AND p.subgroup_id > 0) AS placed,
                   countIf(r.state = 'completed'
                       AND r.covered_until_s >= c.duration_ms / 1000 - 0.05) AS analysed
            FROM (
                SELECT project_id, clip_id, max(duration_ms) AS duration_ms
                FROM clips WHERE project_id IN {ids:Array(UInt32)} AND status='active'
                GROUP BY project_id, clip_id
            ) AS c
            LEFT ANY JOIN current_clip_placement AS p
                ON p.project_id=c.project_id AND p.clip_id=c.clip_id
            LEFT JOIN current_analysis_runs AS r
                ON r.project_id=c.project_id AND r.clip_id=c.clip_id
            LEFT JOIN current_clip_lifecycle AS l
                ON l.project_id=c.project_id AND l.clip_id=c.clip_id
            WHERE l.action != 'deleted'
            GROUP BY c.project_id
        """,
            params,
        ),
        _many(
            """
            SELECT f.project_id AS project_id, count() AS findings,
                   countIf(first_review = 'human_confirmed') AS confirmed,
                   countIf(first_review IN
                       ('human_corrected', 'human_range_adjusted')) AS corrected,
                   countIf(first_review = 'human_dismissed') AS dismissed
            FROM (
                SELECT project_id, clip_id, run_id, finding_id,
                       countIf(action = 'machine_open') AS originals,
                       argMinIf(action, tuple(revision, occurred_at, event_id),
                           startsWith(action, 'human_')) AS first_review
                FROM finding_events
                WHERE project_id IN {ids:Array(UInt32)}
                  AND action != 'human_retracted'
                  AND event_id NOT IN (
                    SELECT retracts_event_id FROM finding_events
                    WHERE project_id IN {ids:Array(UInt32)} AND action='human_retracted'
                  )
                GROUP BY project_id, clip_id, run_id, finding_id
                HAVING originals > 0
            ) AS f
            INNER JOIN current_analysis_runs AS r
                ON r.project_id=f.project_id AND r.clip_id=f.clip_id AND r.run_id=f.run_id
            LEFT JOIN current_clip_lifecycle AS l
                ON l.project_id=f.project_id AND l.clip_id=f.clip_id
            WHERE r.state='completed' AND l.action != 'deleted'
            GROUP BY f.project_id
        """,
            params,
        ),
    )
    by_id = {int(row["project_id"]): dict(row) for row in corpus}
    for row in reviews:
        by_id.setdefault(int(row["project_id"]), {}).update(row)
    rows = [
        ProjectQuality(
            project_id=p.project_id, name=p.name, **counts(by_id.get(p.project_id, {})).model_dump()
        )
        for p in visible
    ]
    total = {
        key: sum(getattr(row, key) for row in rows)
        for key in (
            "clips",
            "placed",
            "analysed",
            "findings",
            "confirmed",
            "corrected",
            "dismissed",
        )
    }
    return QualityReport(measured_at=datetime.now(UTC), overall=counts(total), projects=rows)
